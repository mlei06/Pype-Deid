"""Tests for regex_ner + whitelist and list upload API."""

from __future__ import annotations

import io

from pypedeid.domain import AnnotatedDocument, Document
from pypedeid.pipes.combinators import Pipeline
from pypedeid.pipes.regex_ner import (
    BUILTIN_REGEX_PATTERNS,
    RegexLabelSettings,
    RegexNerConfig,
    RegexNerPipe,
)
from pypedeid.pipes.whitelist import WhitelistConfig, WhitelistPipe, WhitelistLabelConfig


def _no_builtin_regex_config() -> RegexNerConfig:
    """Return a config with all built-in regex labels disabled."""
    return RegexNerConfig(
        labels={label: RegexLabelSettings(enabled=False) for label in BUILTIN_REGEX_PATTERNS},
    )


def _doc(text: str) -> AnnotatedDocument:
    return AnnotatedDocument(document=Document(id="test-doc", text=text), spans=[])


def _chained_detectors(config_r: RegexNerConfig | None, config_w: WhitelistConfig | None):
    return Pipeline(pipes=[
        RegexNerPipe(config_r),
        WhitelistPipe(config_w),
    ])


def test_builtin_patterns_match_phone_and_date() -> None:
    pipe = _chained_detectors(RegexNerConfig(), WhitelistConfig())
    out = pipe.forward(_doc("Call 555-123-4567 on 12/25/2024."))
    labels = {s.label for s in out.spans}
    assert "PHONE" in labels
    assert "DATE" in labels


def test_label_disabled_via_settings() -> None:
    cfg = RegexNerConfig(
        labels={"PHONE": RegexLabelSettings(enabled=False)}
    )
    pipe = _chained_detectors(cfg, WhitelistConfig())
    out = pipe.forward(_doc("Call 555-123-4567."))
    assert not any(s.label == "PHONE" for s in out.spans)


def test_list_terms_hospital() -> None:
    pipe = _chained_detectors(
        _no_builtin_regex_config(),
        WhitelistConfig(
            labels={
                "HOSPITAL": WhitelistLabelConfig(
                    terms=["Toronto General Hospital"],
                ),
            }
        ),
    )
    out = pipe.forward(_doc("Admitted to Toronto General Hospital today."))
    assert any(s.label == "HOSPITAL" for s in out.spans)


def test_ner_builtins_endpoint(client) -> None:
    r = client.get("/pipelines/ner/builtins")
    assert r.status_code == 200
    body = r.json()
    assert "DATE" in body["regex_labels"]
    assert body["whitelist_labels"] == []


def test_whitelist_parse_lists_endpoint(client) -> None:
    csv_body = "term\nAlpha Clinic\nBeta Clinic\n"
    files = [
        ("files", ("sites.csv", io.BytesIO(csv_body.encode("utf-8")), "text/csv")),
    ]
    r = client.post("/pipelines/whitelist/parse-lists", files=files, data={"labels": "HOSPITAL"})
    assert r.status_code == 200, r.text
    res = r.json()["results"][0]
    assert res["label"] == "HOSPITAL"
    assert res["count"] == 2
    assert "Alpha Clinic" in res["terms"]


def test_builtin_regex_disabled_lists_only_labels() -> None:
    pipe = _chained_detectors(
        _no_builtin_regex_config(),
        WhitelistConfig(
            labels={
                "HOSPITAL": WhitelistLabelConfig(
                    terms=["Toronto General Hospital"],
                ),
            },
        ),
    )
    out = pipe.forward(_doc("Patient at Toronto General Hospital."))
    assert any(s.label == "HOSPITAL" for s in out.spans)


def _labels_for(text: str, label: str) -> list[str]:
    """Return the matched substrings for a single label in ``text``."""
    pipe = RegexNerPipe(RegexNerConfig())
    out = pipe.forward(_doc(text))
    return [text[s.start : s.end] for s in out.spans if s.label == label]


# ---------------------------------------------------------------------------
# New label patterns
# ---------------------------------------------------------------------------


def test_age_patterns() -> None:
    cases = [
        "Patient is age 67.",
        "Aged 88 at admission.",
        "Presents as a 55-year-old female.",
        "55 years old male.",
        "65 y/o with chest pain.",
        "Age: 90.",
    ]
    for text in cases:
        assert _labels_for(text, "AGE"), f"AGE missed in: {text!r}"


def test_organization_patterns() -> None:
    """Hospitals, clinics, and corporations all collapse into ORGANIZATION."""
    cases = [
        # Hospitals / clinics
        "Admitted to Toronto General Hospital today.",
        "Transferred to Mount Sinai Medical Center.",
        "Seen at Mayo Clinic last week.",
        "Visit at Memorial Sloan Kettering Cancer Center.",
        "Referred to St. Jude Children's Hospital.",
        # Corporate / academic
        "Drug supplied by Pfizer Inc.",
        "Medication from Johnson & Johnson Pharmaceuticals.",
        "Studied at Harvard University.",
        "Works at Acme Health Solutions.",
    ]
    for text in cases:
        assert _labels_for(text, "ORGANIZATION"), f"ORGANIZATION missed in: {text!r}"


def test_url_patterns() -> None:
    text = "See https://example.com/foo and www.clinic.org/page for details."
    matches = _labels_for(text, "URL")
    assert any("https://example.com/foo" in m for m in matches)
    assert any("www.clinic.org/page" in m for m in matches)


def test_ip_address_patterns() -> None:
    text = "Server at 192.168.1.42 and gateway 10.0.0.1."
    matches = _labels_for(text, "IP_ADDRESS")
    assert "192.168.1.42" in matches
    assert "10.0.0.1" in matches


def test_fax_folds_into_phone() -> None:
    """Fax-keyword phone numbers emit ``PHONE`` (FAX collapsed into PHONE)."""
    cases = [
        "Fax: 555-987-6543",
        "facsimile #555.123.4567",
        "fax number (212) 555-0100",
    ]
    for text in cases:
        assert _labels_for(text, "PHONE"), f"PHONE missed in: {text!r}"


def test_id_consolidates_keyword_anchored_identifiers() -> None:
    """MRN, account, license, DEA, NPI, VIN, plate, serial, UDI, OHIP, SIN
    all collapse into ``ID`` because regex alone cannot reliably tell them
    apart and surrogate handling is identical for all of them."""
    cases = [
        "MRN: 1234567",
        "Issued License #ABC12345 last year.",
        "DEA AB1234567 on file.",
        "NPI 1234567890 verified.",
        "VIN 1HGCM82633A123456 issued.",
        "License plate ABC-123 cited.",
        "Pacemaker serial number SN-9981A.",
        "UDI: 0123456789ABC.",
        "Account #555000123 was billed.",
        "acct: 9988-7766",
        "OHIP 1234567890",
        "SIN 123-456-789",
    ]
    for text in cases:
        assert _labels_for(text, "ID"), f"ID missed in: {text!r}"


def test_postal_code_consolidates_us_and_canada() -> None:
    """ZIP_CODE_US and POSTAL_CODE_CA are now both ``POSTAL_CODE``."""
    # Canadian postal code (full match)
    assert _labels_for("Toronto, ON M5V 3A8.", "POSTAL_CODE") == ["M5V 3A8"]
    # US zip after state name (state captured but narrowed out of the entity)
    assert _labels_for("Patient lives in California 94025.", "POSTAL_CODE") == ["94025"]
    assert _labels_for("Springfield, Illinois 62704.", "POSTAL_CODE") == ["62704"]


def test_date_time_patterns() -> None:
    assert _labels_for("Admitted 2024-01-15T14:30:00Z.", "DATE_TIME")
    assert _labels_for("Arrived at 14:30.", "DATE_TIME")
    assert _labels_for("Procedure started at 2:30 pm.", "DATE_TIME")


# ---------------------------------------------------------------------------
# Improved existing patterns
# ---------------------------------------------------------------------------


def test_email_obfuscated_forms() -> None:
    matches = _labels_for("Contact john [at] example [dot] com today.", "EMAIL")
    assert matches, "obfuscated [at]/[dot] EMAIL not detected"


def test_phone_international_prefix() -> None:
    assert _labels_for("Call +1 555 123 4567 anytime.", "PHONE")
    assert _labels_for("Call +44 20 7946 0958 from London.", "PHONE")


def test_date_iso_year_range_and_decade() -> None:
    assert _labels_for("Treated 2010-2024 in clinic.", "DATE")
    assert _labels_for("Symptoms began in the 1990s.", "DATE")


def test_address_po_box() -> None:
    assert _labels_for("Mail to P.O. Box 1234 in town.", "ADDRESS")


def _spans_intersect(a, b) -> bool:
    return a.start < b.end and b.start < a.end


def test_no_duplicate_id_spans_after_remap_collision() -> None:
    """An ``ID`` remap target plus the native ``ID`` match at the same range
    must not produce two ``ID`` spans at the same offsets."""
    # The fax-keyword PHONE branch + the bare digits PHONE branch can both
    # match identical ranges; dedupe should collapse them.
    cfg = RegexNerConfig()
    pipe = RegexNerPipe(cfg)
    out = pipe.forward(_doc("Fax: 555-987-6543"))
    phone_spans = [s for s in out.spans if s.label == "PHONE"]
    keys = {(s.start, s.end) for s in phone_spans}
    assert len(keys) == len(phone_spans), f"duplicate PHONE spans: {phone_spans}"


def test_no_internal_self_overlap_across_labels() -> None:
    """The pipe's own matches must be non-overlapping after reconciliation."""
    pipe = RegexNerPipe(RegexNerConfig())
    out = pipe.forward(
        _doc(
            "Patient MRN: 1234567 admitted 04/27/1985. "
            "Email john@example.com phone 555-123-4567."
        )
    )
    spans = list(out.spans)
    for i, a in enumerate(spans):
        for b in spans[i + 1 :]:
            assert not _spans_intersect(a, b), (
                f"self-overlap in regex_ner output: {a} ↔ {b}"
            )


def test_organization_avoids_bare_keyword() -> None:
    """The organization-keyword alone shouldn't match without a proper-noun
    prefix (lower-case ``the hospital``, ``the clinic`` are not entities)."""
    pipe = RegexNerPipe(RegexNerConfig())
    out = pipe.forward(_doc("Discharged from the hospital today."))
    org_spans = [s for s in out.spans if s.label == "ORGANIZATION"]
    assert all(text not in {"hospital", "the hospital"} for text in
               [out.document.text[s.start:s.end].lower() for s in org_spans])


# ---------------------------------------------------------------------------
# Boundary narrowing — keyword-anchored patterns must not capture the keyword
# ---------------------------------------------------------------------------


def test_phone_keyword_is_not_captured() -> None:
    """``Phone 4086569015`` must emit only the digits, not the keyword."""
    cases = {
        "Phone 4086569015": "4086569015",
        "Phone: 408-656-9015": "408-656-9015",
        "phone number is 408-656-9015": "408-656-9015",
        "Tel 555.123.4567": "555.123.4567",
        "mobile 555-1234": "555-1234",
        "Fax: 555-987-6543": "555-987-6543",
    }
    for text, expected in cases.items():
        spans = _labels_for(text, "PHONE")
        assert spans == [expected], f"{text!r} → {spans!r}, expected [{expected!r}]"


def test_id_keyword_is_not_captured() -> None:
    """Keyword-anchored ID patterns must emit only the identifier."""
    cases = {
        "MRN: 1234567": "1234567",
        "Account #: 998877": "998877",
        "DEA AB1234567": "AB1234567",
        "NPI 1234567890": "1234567890",
        "License plate ABC1234": "ABC1234",
        "OHIP 1234567890": "1234567890",
        "SIN 123-456-789": "123-456-789",
    }
    for text, expected in cases.items():
        spans = _labels_for(text, "ID")
        assert expected in spans, f"{text!r} → {spans!r}, expected {expected!r}"


def test_age_keyword_is_not_captured() -> None:
    """``age 55`` should emit just ``55``."""
    spans = _labels_for("Patient age 55 admitted today.", "AGE")
    assert spans == ["55"]
    spans = _labels_for("aged 88 at admission", "AGE")
    assert spans == ["88"]
    # Non-keyword forms still emit the full natural phrase.
    assert _labels_for("55-year-old female", "AGE") == ["55-year-old"]


def test_date_year_context_is_not_captured() -> None:
    """``since 2020`` should emit just ``2020`` rather than the full phrase."""
    spans = _labels_for("Patient since 2020 with diabetes.", "DATE")
    assert spans == ["2020"]


def test_postal_code_state_is_not_captured() -> None:
    """``Illinois 62704`` should emit just the zip."""
    spans = _labels_for("Springfield, Illinois 62704.", "POSTAL_CODE")
    assert spans == ["62704"]


# ---------------------------------------------------------------------------
# False-positive sanity — patterns we deliberately removed
# ---------------------------------------------------------------------------


def test_bare_digits_no_longer_match_id() -> None:
    """Bare 6-10 digit clusters should no longer fire as ID (was a major FP)."""
    for text in ["lab value 1234567", "lot 12345678", "score 9876543"]:
        assert not _labels_for(text, "ID"), f"unexpected ID match in {text!r}"


def test_unit_shorthand_does_not_match_age() -> None:
    """``5 m``/``5 f`` (units) should not match AGE."""
    for text in ["5 m", "5 f", "5 ml", "5 mg"]:
        assert not _labels_for(text, "AGE"), f"unexpected AGE match in {text!r}"
