"""Regex-only PHI detection with built-in clinical patterns per label.

Design notes:

* Label surface is intentionally narrow (~12 labels). Sub-types like ``MRN``,
  ``DEA``, ``OHIP`` etc. all collapse into ``ID`` because regex alone cannot
  reliably tell them apart — the keyword *is* the disambiguator, and for
  redaction/surrogate purposes they're treated identically. Specialized labels
  belong to ML detectors that have semantic signal, not to regex.
* Keyword-anchored alternatives narrow the emitted span to the entity itself
  via uniquely-named ``entity_*`` capture groups. This keeps the keyword (e.g.
  ``"Phone "``, ``"MRN: "``, ``"Illinois "``) out of the span so redaction
  output stays correct: ``"Phone 4086569015"`` → ``"Phone [PHONE]"`` rather
  than ``"[PHONE]"``. ``forward()`` extracts the first matched ``entity_*``
  group's offsets; when no such group is present the full match is used.
* Bare-digit fallbacks (``\\b\\d{6,10}\\b`` for IDs, the 9/11-digit OCR phone
  variants) have been removed — they were responsible for the bulk of false
  positives on lab values, lot numbers, and dosing. Numeric IDs now require
  keyword context.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field

from pypedeid.domain import AnnotatedDocument, EntitySpan
from pypedeid.pipes.base import ConfigurablePipe
from pypedeid.pipes.detector_label_mapping import (
    accumulate_spans,
    apply_detector_label_mapping,
    effective_detector_labels,
)
from pypedeid.pipes.span_merge import merge_longest_non_overlapping
from pypedeid.pipes.ui_schema import field_ui

# ---------------------------------------------------------------------------
# US state names (for zip-code context matching)
# ---------------------------------------------------------------------------

_US_STATES = (
    "Alabama|Alaska|Arizona|Arkansas|California|Colorado|Connecticut|Delaware|"
    "Florida|Georgia|Hawaii|Idaho|Illinois|Indiana|Iowa|Kansas|Kentucky|"
    "Louisiana|Maine|Maryland|Massachusetts|Michigan|Minnesota|Mississippi|"
    "Missouri|Montana|Nebraska|Nevada|New Hampshire|New Jersey|New Mexico|"
    "New York|North Carolina|North Dakota|Ohio|Oklahoma|Oregon|Pennsylvania|"
    "Rhode Island|South Carolina|South Dakota|Tennessee|Texas|Utah|Vermont|"
    "Virginia|Washington|West Virginia|Wisconsin|Wyoming|"
    "District of Columbia|Puerto Rico"
)

_MONTH = (
    "Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    "Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?"
)

_SEASON = r"winter|spring|summer|autumn|fall"

_ORDINAL = r"(?:st|nd|rd|th)"

_STREET_SUFFIX = (
    "Street|St|Avenue|Ave|Boulevard|Blvd|Drive|Dr|Road|Rd|"
    "Lane|Ln|Court|Ct|Place|Pl|Circle|Cir|Way|"
    "Highway|Hwy|Parkway|Pkwy|Terrace|Ter|Trail|Trl|"
    "Square|Sq|Plaza|Plz|Crescent|Cres|Alley|Aly|Loop|Row"
)

# Hospital/clinic + corporate/academic keywords folded into one ORGANIZATION list.
_ORG_KEYWORD = (
    # Hospital / clinic
    r"Hospitals?|Medical\s+Center|Medical\s+Centre|Medical\s+Group|"
    r"Health\s+System|Health\s+Center|Health\s+Centre|"
    r"Healthcare|Health\s+Care|Cancer\s+Center|Cancer\s+Centre|"
    r"Children's\s+Hospital|Memorial\s+Hospital|"
    r"Clinic|Polyclinic|Infirmary|Sanitarium|Sanatorium|"
    r"Urgent\s+Care|Surgery\s+Center|"
    # Corporate / academic
    r"Inc\.?|LLC|L\.L\.C\.|Corp\.?|Corporation|Co\.|Company|"
    r"Foundation|Ltd\.?|Limited|Group|Associates|Partners|"
    r"Pharmaceuticals?|Pharma|Laboratories|Labs?\.?|Industries|"
    r"Holdings|Enterprises|Solutions|Systems|Technologies|"
    r"University|College|Institute|Academy|Society|Association"
)

# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

# EMAIL: standard mailbox + obfuscated [at]/(at)/[dot]/(dot) forms. Full match
# is the entity in every alternative.
_EMAIL = (
    r"\b[A-Za-z0-9._%+\-]+\s?@\s?[A-Za-z0-9][A-Za-z0-9\-\.]*\.[A-Za-z]{2,24}\b"
    r"|\b[A-Za-z0-9._%+\-]+\s*(?:\[at\]|\(at\))\s*"
    r"[A-Za-z0-9][A-Za-z0-9\-\.]*\s*(?:\[dot\]|\(dot\)|\.)\s*[A-Za-z]{2,24}\b"
)

# PHONE: separator-required raw forms + keyword-anchored. Folds the legacy
# ``FAX`` label in (fax keyword is just one of the trigger words). The
# 9-digit / 11-digit "OCR" variants from the previous pack are dropped — they
# were a major false-positive source.
_PHONE = (
    # International: +1 555 123 4567, +44 20 7946 0958
    r"\+\d{1,3}[-.\s]?\(?\d{1,4}\)?[-.\s]?\d{1,4}[-.\s]?\d{1,9}"
    # (XXX) XXX-XXXX
    r"|\(\d{3}\)\s*\d{3}[-.\s]?\d{4}"
    # XXX-XXX-XXXX / XXX.XXX.XXXX / XXX XXX XXXX (separator required)
    r"|\b\d{3}[-.\s]\d{3}[-.\s]\d{4}\b"
    # Keyword + digits — narrowed to digits only. The keyword set absorbs the
    # legacy FAX trigger words so faxes still detect; consumers that need to
    # distinguish fax from phone can layer a dedicated detector.
    r"|(?:phone|tel|telephone|mobile|cell|cellular|pager|beeper|fax|facsimile|"
    r"home\s+phone|work\s+phone|office\s+phone)\s*"
    r"(?:number|num|no|#)?\s*[:#\-]?\s*"
    r"(?P<entity_phone>\(?\+?\d[\d\s\-\.\(\)]{6,18}\d)"
    r"(?:\s*(?:x|ex|ext|extension)\.?\s*\(?\d+\)?)?"
)

# DATE: numeric/named/ranges + keyword-anchored year (narrowed).
_DATE = (
    # Numeric formats
    r"\b\d{1,2}[\-\/\.]\d{1,2}[\-\/\.]\d{2,4}\b"
    r"|\b\d{4}[\-\/\.]\d{1,2}[\-\/\.]\d{1,2}\b"
    r"|\b\d{1,2}[\-\/]\d{4}\b"
    r"|\b\d{4}[\-\/]\d{1,2}\b"
    # Numeric ranges
    r"|\b\d{1,2}\/\d{1,2}\-\d{1,2}\/\d{1,2}(?:\/\d{2,4})?\b"
    r"|\b\d{1,2}\/\d{1,2}\/\d{2,4}\-\d{1,2}\/\d{1,2}\/\d{2,4}\b"
    # Named months
    r"|\b(?:" + _MONTH + r")\.?\s+\d{1,2}(?:" + _ORDINAL + r")?\s*[\,\s]+\d{2,4}\b"
    r"|\b\d{1,2}(?:" + _ORDINAL + r")?\s+(?:of\s+)?(?:" + _MONTH + r")\.?\s*[\,\s]+\d{2,4}\b"
    r"|\b(?:" + _MONTH + r")\.?\s+\d{1,2}(?:" + _ORDINAL + r")?\b"
    r"|\b\d{1,2}(?:" + _ORDINAL + r")?\s+(?:of\s+)?(?:" + _MONTH + r")\b"
    r"|\b(?:" + _MONTH + r")\.?\s*(?:of\s+)?\d{4}\b"
    r"|\b(?:" + _MONTH + r")\.?\s*\'\d{2}\b"
    # Named ranges
    r"|\b(?:" + _MONTH + r")\.?\s+\d{1,2}\s*(?:\-|to|through)\s*\d{1,2}\s*[\,\s]+\d{2,4}\b"
    r"|\b\d{1,2}\s*(?:\-|to|through)\s*\d{1,2}\s+(?:" + _MONTH + r")\.?\s*[\,\s]+\d{2,4}\b"
    # Season + year
    r"|\b(?:" + _SEASON + r")\s*(?:of\s+)?\d{2,4}\b"
    # Decades
    r"|\b(?:19|20)\d0s\b"
    r"|\bthe\s+\d0s\b"
    r"|\'\d{2}s\b"
    # Year ranges
    r"|\b(?:19|20)\d{2}\s*(?:\-|to|through|until)\s*(?:19|20)\d{2}\b"
    # Holidays
    r"|\b(?:Christmas|Thanksgiving|Easter|Hanukkah|Rosh Hashanah|Ramadan|"
    r"New Year(?:'s)?(?:\s+Day)?|Independence Day|Memorial Day|"
    r"Victoria Day|Canada Day|Labour Day|Labor Day|Veterans Day|"
    r"Mother's Day|Father's Day|Valentine's Day)\b"
    # Year with medical-event context — narrowed so "since [DATE]" reads cleanly
    r"|\b(?:since|from|in|year|during|until|before|after|by|circa)\s+"
    r"(?P<entity_date_year>\d{4})\b"
)

# DATE_TIME: ISO 8601 timestamps + bare time-of-day. Full match in all branches.
_DATE_TIME = (
    r"\b\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?"
    r"(?:\s*Z|\s*[+-]\d{2}:?\d{2})?\b"
    r"|\b(?:[01]?\d|2[0-3]):[0-5]\d(?::[0-5]\d)?(?:\s*[ap]\.?\s*m\.?)?\b"
    r"|\b\d{1,2}\s*[ap]\.?\s*m\.?\b"
)

# AGE: explicit age phrases. Keyword-anchored "age N" narrows to N. The legacy
# ``\d{1,3}\s*[ymf]o?\b`` shorthand is dropped — it fired on "5 m", "5 f"
# (units) far too often. Callers who need "55M/55F" gender-shorthand can layer
# a dedicated detector.
_AGE = (
    # "age 55" / "aged 55" → narrowed to "55"
    r"\b(?:age[ds]?|aged)\s*(?:is|of|=|:)?\s*(?P<entity_age_kw>\d{1,3})\b"
    # 55-year-old / 55 years old / 55 y/o (full match)
    r"|\b\d{1,3}\s*[\-]?\s*year[\s\-]*old\b"
    r"|\b\d{1,3}\s*(?:years?|yrs?)[\s\.\-]*old\b"
    r"|\b\d{1,3}\s*y[\s\.\/]\s*o\.?\b"
)

# ID: every keyword-anchored identifier (medical record, account, license,
# certificate, DEA, NPI, VIN, license plate, device serial, UDI, OHIP, SIN,
# patient/subject/study/enrollment IDs). Each alternative narrows to its own
# uniquely-named entity_* group so the keyword is dropped from the span.
_ID = (
    # Medical record / chart / patient / case / EMPI
    r"\b(?:mrn|medical\s+record(?:\s+(?:number|num|no|#))?|"
    r"hospital\s+(?:number|num|no|#)|chart\s+(?:number|num|no|#)?|"
    r"case\s+(?:number|num|no|#)|empi)\s*"
    r"(?:number|num|no|#)?\s*[:#\-]?\s*"
    r"(?P<entity_mrn>[A-Za-z]?\d[\dA-Za-z\-\/]{2,})\b"
    # Patient/subject/study identifiers
    r"|\b(?:patient|subject|study|enrollment)\s+"
    r"(?:id|identifier|number|#)\s*[:#\-]?\s*"
    r"(?P<entity_subject_id>[A-Z0-9][A-Z0-9\-]{2,})\b"
    # Generic ID prefixes (HCN, HRN, UPI, generic ID:)
    r"|\b(?:ID|HCN|HRN|UPI)[\s:#]+(?P<entity_generic_id>[A-Z0-9][\dA-Z\-]{2,})\b"
    # Account
    r"|\b(?:account|acct|acc)\s*(?:number|num|no|#)?\s*[:#\-]?\s*"
    r"(?P<entity_account>\d[\dA-Z\-]{3,})\b"
    # License plate — listed before the generic ``license`` alternative so
    # ``License plate ABC1234`` doesn't match as ``license <plate>``.
    r"|\b(?:license\s+plate|plate\s+number|plate\s+#|tag\s+number)\s*"
    r"[:#\-]?\s*(?P<entity_plate>[A-Z0-9][A-Z0-9\-]{1,7}[A-Z0-9])\b"
    # DEA: 2 letters + 7 digits — also before generic license.
    r"|\bDEA\s*(?:number|num|no|#)?\s*[:#\-]?\s*"
    r"(?P<entity_dea>[A-Z]{2}\d{7})\b"
    # NPI: 10 digits
    r"|\bNPI\s*(?:number|num|no|#)?\s*[:#\-]?\s*"
    r"(?P<entity_npi>\d{10})\b"
    # VIN: 17 chars, no I/O/Q
    r"|\b(?:VIN|vehicle\s+identification\s+number)\s*"
    r"(?:number|num|no|#)?\s*[:#\-]?\s*"
    r"(?P<entity_vin>[A-HJ-NPR-Z0-9]{17})\b"
    # License / certificate (generic — last among license-like alternatives).
    r"|\b(?:licen[cs]e|lic\.?|certificate|cert\.?)\s*"
    r"(?:number|num|no|#)?\s*[:#\-]?\s*"
    r"(?P<entity_license>[A-Z0-9][\dA-Z\-]{3,})\b"
    # Device / model serial
    r"|\b(?:device\s+(?:id|number|serial|#)|serial\s+(?:number|num|no|#)|"
    r"s\/n|s\.n\.|model\s+(?:number|num|no|#))\s*[:#\-]?\s*"
    r"(?P<entity_serial>[A-Z0-9][A-Z0-9\-]{3,})\b"
    # UDI (medical device unique identifier)
    r"|\bUDI[\s:#\-]+(?P<entity_udi>[\dA-Z\(\)\+\-]{8,})\b"
    # OHIP (Ontario health card): 4-3-3 digits + optional 2-letter version.
    # Keyword-anchored only — the bare-digit form collided with phone numbers.
    r"|\bOHIP[\s:#\-]+"
    r"(?P<entity_ohip>\d{4}[- \/]?\d{3}[- \/]?\d{3}(?:[- \/]?[A-Z]{2})?)\b"
    # SIN (Canadian social insurance number) — keyword-anchored.
    r"|\bSIN[\s:#\-]+"
    r"(?P<entity_sin>\d{3}[- \/]?\d{3}[- \/]?\d{3})\b"
)

# SSN: distinctive shape (XXX-XX-XXXX with consistent separator). Kept as its
# own label because the surrogate strategy (mask, hash, faker) is specific.
_SSN = r"\b\d{3}([- /]?)\d{2}\1\d{4}\b"

# URL: scheme-prefixed + bare www.
_URL = (
    r"\bhttps?:\/\/[^\s<>\"\)\]]+"
    r"|\b(?:ftp|ftps|file):\/\/[^\s<>\"\)\]]+"
    r"|\bwww\.[a-zA-Z0-9][a-zA-Z0-9\-]*(?:\.[a-zA-Z0-9\-]+)+(?:\/[^\s<>\"\)\]]*)?"
)

# IP_ADDRESS: octet-validated IPv4 + uncompressed IPv6.
_IP_ADDRESS = (
    r"\b(?:25[0-5]|2[0-4]\d|1\d{2}|[1-9]?\d)"
    r"(?:\.(?:25[0-5]|2[0-4]\d|1\d{2}|[1-9]?\d)){3}\b"
    r"|\b(?:[a-fA-F0-9]{1,4}:){7}[a-fA-F0-9]{1,4}\b"
)

# ORGANIZATION: capitalized words ending in a hospital/corporate/academic
# keyword. Folds the legacy ``HOSPITAL`` label in — regex cannot reliably
# distinguish a hospital from a foundation, and downstream consumers usually
# treat both as ``ORGANIZATION``.
_ORGANIZATION = (
    r"\b(?:(?-i:[A-Z])[A-Za-z'\.\-]+\s+){1,4}"
    r"(?-i:" + _ORG_KEYWORD + r")\b"
)

# POSTAL_CODE: Canadian postal code (full match) + US zip after a state name
# (narrowed to drop the captured state).
_POSTAL_CODE = (
    r"\b[a-zA-Z]\d[a-zA-Z][ \-]?\d[a-zA-Z]\d\b"
    r"|\b(?:" + _US_STATES + r")\s*[,.]?\s*"
    r"(?P<entity_zip>\d{5}(?:-\d{4})?)\b"
)

# ADDRESS: street with common suffix + optional unit, plus PO Box.
_ADDRESS = (
    r"\b\d+\s+(?:[A-Za-z\.\']+\s+)?(?:[A-Za-z\.\']+\s+)?"
    r"(?:" + _STREET_SUFFIX + r")\.?"
    r"(?:\s*[,.]?\s*(?:apt|suite|ste|unit|bldg|building|fl|floor|rm|room)\.?\s*#?\s*[\w]+)?\b"
    r"|\bP\.?\s*O\.?\s*Box\s+\d+\b"
)


_CLINICAL_PHI_PATTERNS: dict[str, str] = {
    "DATE": _DATE,
    "DATE_TIME": _DATE_TIME,
    "AGE": _AGE,
    "PHONE": _PHONE,
    "EMAIL": _EMAIL,
    "ID": _ID,
    "SSN": _SSN,
    "URL": _URL,
    "IP_ADDRESS": _IP_ADDRESS,
    "ORGANIZATION": _ORGANIZATION,
    "POSTAL_CODE": _POSTAL_CODE,
    "ADDRESS": _ADDRESS,
}

# Register the built-in packs now that the pattern dict is defined. This is a
# one-shot side-effect import; ``packs._register_builtin_packs()`` reads
# ``_CLINICAL_PHI_PATTERNS`` above.
from pypedeid.pipes.regex_ner.packs import (  # noqa: E402
    _register_builtin_packs,
    get_pattern_pack,
)

_register_builtin_packs()

# Backward-compat alias: legacy callers import ``BUILTIN_REGEX_PATTERNS`` from
# this module (and via ``pypedeid.pipes.regex_ner``). Always points at the
# default (``clinical_phi``) pack's patterns.
BUILTIN_REGEX_PATTERNS: dict[str, str] = dict(_CLINICAL_PHI_PATTERNS)


class RegexLabelSettings(BaseModel):
    """Per-label settings for the regex NER detector."""

    enabled: bool = True
    remap: str | None = None
    custom_pattern: str | None = None


class RegexNerConfig(BaseModel):
    """Configuration for :class:`RegexNerPipe`."""

    model_config = ConfigDict(
        json_schema_extra={
            "description": (
                "Per-label regex patterns for rule-based PHI detection. "
                "Chain with ``whitelist`` for dictionary phrase matching."
            )
        }
    )

    source_name: str = Field(
        default="regex_ner",
        json_schema_extra=field_ui(
            ui_group="General",
            ui_order=1,
            ui_widget="text",
            ui_advanced=True,
        ),
    )

    pattern_pack: str = Field(
        default="clinical_phi",
        description=(
            "Name of the registered regex pattern pack to use. "
            "Built-ins: 'clinical_phi' (default), 'generic_pii'."
        ),
        json_schema_extra=field_ui(
            ui_group="General",
            ui_order=2,
            ui_widget="text",
            ui_advanced=True,
        ),
    )

    labels: dict[str, RegexLabelSettings] = Field(
        default_factory=dict,
        title="Labels",
        description=(
            "Configure each detection label: toggle on/off, "
            "view or override regex patterns, and remap output labels."
        ),
        json_schema_extra=field_ui(
            ui_group="Labels",
            ui_order=2,
            ui_widget="unified_label",
            ui_allow_custom_labels=True,
        ),
    )

    skip_overlapping: bool = Field(
        default=False,
        description="Drop new spans that overlap any existing span in the document.",
        json_schema_extra=field_ui(
            ui_group="General",
            ui_order=99,
            ui_widget="switch",
        ),
    )

    dedupe_internal_overlaps: bool = Field(
        default=True,
        description=(
            "Reconcile this pipe's own matches before they are added to the "
            "document so it never emits duplicate or overlapping spans with "
            "itself. Runs after label remap using a longest-match-wins greedy "
            "merge — within a single rule-based pipe a longer match is by "
            "construction the more specific one. Cross-pipe label conflicts "
            "are still settled by ``resolve_spans`` downstream. Disable only "
            "if you need the raw, unfiltered match set."
        ),
        json_schema_extra=field_ui(
            ui_group="General",
            ui_order=100,
            ui_widget="switch",
            ui_advanced=True,
        ),
    )

    @property
    def label_mapping(self) -> dict[str, str | None]:
        """Derived label mapping for the DetectorWithLabelMapping protocol."""
        mapping: dict[str, str | None] = {}
        for label, s in self.labels.items():
            if not s.enabled:
                mapping[label] = None
            elif s.remap:
                mapping[label] = s.remap
        return mapping


def builtin_regex_label_names(pack_name: str = "clinical_phi") -> list[str]:
    """Return the labels contributed by *pack_name* (default: clinical_phi)."""
    return get_pattern_pack(pack_name).labels()


def default_base_labels() -> list[str]:
    """Default label space for the regex_ner detector (clinical_phi pack)."""
    return get_pattern_pack("clinical_phi").labels()


class _ResolvedRegex:
    __slots__ = ("label", "compiled", "entity_groups")

    def __init__(self, label: str, compiled: re.Pattern[str]) -> None:
        self.label = label
        self.compiled = compiled
        # Pre-compute the indexes of all ``entity_*`` named groups so the hot
        # path doesn't iterate the full groupindex per match.
        self.entity_groups: tuple[int, ...] = tuple(
            idx for name, idx in compiled.groupindex.items()
            if name.startswith("entity_")
        )


def _resolve_regex(config: RegexNerConfig) -> list[_ResolvedRegex]:
    pack = get_pattern_pack(config.pattern_pack)
    label_keys = set(pack.patterns) | set(config.labels)

    out: list[_ResolvedRegex] = []
    for label in sorted(label_keys):
        settings = config.labels.get(label, RegexLabelSettings())
        if not settings.enabled:
            continue
        pat = settings.custom_pattern or pack.patterns.get(label)
        if not pat:
            continue
        out.append(_ResolvedRegex(label, re.compile(pat, re.IGNORECASE)))
    return out


def _entity_span(m: re.Match[str], entity_groups: tuple[int, ...]) -> tuple[int, int]:
    """Return the narrowed entity span if any ``entity_*`` group matched.

    Each pattern alternative that needs to drop a leading keyword declares a
    uniquely-named ``entity_*`` capture group. Only one such group can match
    per regex match (the alternatives are disjoint), so the first non-``None``
    one wins. Patterns without ``entity_*`` groups fall through to the full
    match span.
    """
    for idx in entity_groups:
        s, e = m.span(idx)
        if s != -1:
            return s, e
    return m.span()


class RegexNerPipe(ConfigurablePipe):
    """Detector: regex patterns only."""

    def __init__(self, config: RegexNerConfig | None = None) -> None:
        self._config = config or RegexNerConfig()
        self._resolved = _resolve_regex(self._config)

    @property
    def base_labels(self) -> set[str]:
        return {r.label for r in self._resolved}

    @property
    def label_mapping(self) -> dict[str, str | None]:
        return dict(self._config.label_mapping)

    @property
    def labels(self) -> set[str]:
        return effective_detector_labels(self.base_labels, self._config.label_mapping)

    def forward(self, doc: AnnotatedDocument) -> AnnotatedDocument:
        text = doc.document.text
        found: list[EntitySpan] = []
        for r in self._resolved:
            for m in r.compiled.finditer(text):
                start, end = _entity_span(m, r.entity_groups)
                if start >= end:
                    continue
                found.append(
                    EntitySpan(
                        start=start,
                        end=end,
                        label=r.label,
                        confidence=1.0,
                        source=self._config.source_name,
                    )
                )
        found = apply_detector_label_mapping(found, self._config.label_mapping)

        # Reconcile *after* remap. Two distinct base labels can collapse to the
        # same output label at the same range, and patterns can match nested
        # ranges (e.g. a year inside a date range). Longest-first wins.
        if self._config.dedupe_internal_overlaps and found:
            found = merge_longest_non_overlapping([found])
        else:
            found.sort(key=lambda s: (s.start, s.end, s.label))

        return accumulate_spans(doc, found, skip_overlapping=self._config.skip_overlapping)
