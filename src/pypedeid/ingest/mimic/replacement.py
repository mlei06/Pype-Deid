"""Map MIMIC placeholder descriptions to entity types and synthetic replacement strings."""

from __future__ import annotations

import logging
import random
import re
from datetime import date, timedelta
from typing import TYPE_CHECKING

from pypedeid.ingest.mimic.faker_providers import get_faker, getrandformat

if TYPE_CHECKING:
    from pypedeid.ingest.mimic.profile import NoteProfile
from pypedeid.ingest.mimic.names import generate_name

logger = logging.getLogger(__name__)

_MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]

_FULL_DATE_RE = re.compile(r"\b\d{4}-\d{1,2}-\d{1,2}\b")
_MONTH_DAY_RE = re.compile(r"^\d{1,2}-\d{1,2}$")
_MONTH_YEAR_RE = re.compile(r"^\d{1,2}/\d{4}$")
_NUMERIC_DATE_RE = re.compile(r"^\d[\d/.-]*\d$")  # safe catch-all: only digits/separators


def get_placeholder_entity(placeholder: str) -> str:
    """Normalize bracket content to a coarse entity label."""
    p = placeholder.strip().lower()

    # Names — specific before generic
    if "first" in p and "name" in p:
        return "first name"
    if "last" in p and "name" in p:
        return "last name"
    if "first" in p:
        return "first name"
    if "last" in p:
        return "last name"

    # Contact
    if "phone" in p or "fax" in p or "telephone" in p:
        return "phone number"
    if "pager" in p:
        return "pager number"
    if "e-mail" in p or "email" in p:
        return "e-mail"
    if "url" in p:
        return "url"
    if "social security" in p:
        return "social security number"

    # IDs — specific before "number" / "id" catch-alls
    if "md number" in p or "medical license" in p:
        return "medical license number"
    if "job number" in p:
        return "job id"
    if "medical record number" in p or "mrn" in p:
        return "medical record number"
    if "unit number" in p:
        return "unit number"
    if "serial number" in p:
        return "serial number"
    if "clip number" in p:
        return "clip number"
    if "numeric identifier" in p:
        return "numeric id"

    # Hospital / institutional — specific before "hospital" and "location"
    if "hospital ward" in p:
        return "hospital ward"
    if "hospital unit" in p:
        return "hospital unit"
    if "hospital" in p:
        return "hospital"
    if "university" in p or "college" in p:
        return "university"
    if "company" in p:
        return "company"

    # Geography
    if "apartment address" in p:
        return "apartment address"
    if "street address" in p:
        return "street address"
    if "po box" in p:
        return "po box"
    if "location" in p:
        return "location"
    if "country" in p:
        return "country"
    if "state" in p:
        return "state"

    # Dates — specific patterns before generic
    if "date range" in p:
        return "date range"
    if "month (only)" in p:
        return "month only"
    if "month/day/year" in p:
        return "full date"
    if "month/day" in p:
        return "month day"
    if "month/year" in p:
        return "month year"
    if "month day" in p:
        return "month day alpha"
    if "day month" in p:
        return "day month alpha"
    if "month year" in p:
        return "month year alpha"
    if "year month" in p:
        return "year month alpha"
    if any(m in p for m in (mn.lower() for mn in _MONTH_NAMES)):
        if re.search(r"\b\d{4}\b", p):
            return "month year"
        return "month only"
    if _FULL_DATE_RE.match(p):
        return "full date"
    if _MONTH_DAY_RE.match(p):
        return "month day"
    if _MONTH_YEAR_RE.match(p):
        return "month year"

    # Age
    if "age" in p and "90" in p:
        return "age over 90"
    if "age" in p:
        return "age"
    if p.isdigit() and len(p) <= 2:
        return "age"

    # Year
    if "year" in p:
        return "year"
    if p.isdigit() and len(p) == 4 and p[:2] in ("19", "20", "21", "22"):
        return "year"

    # Name (generic — after all specific checks)
    if "name" in p:
        return "full name"

    # Provider info
    if "dictator info" in p:
        return "dictator info"
    if "attending info" in p:
        return "attending info"
    if "cc contact info" in p:
        return "cc contact info"

    # Holiday
    if "holiday" in p:
        return "holiday"

    # Remaining numeric IDs
    if p.isdigit() and len(p) > 2:
        return "numeric id"
    if "number" in p or "id" in p:
        return "numeric id"

    # Numeric-only pattern with separators → treat as date
    if _NUMERIC_DATE_RE.match(p):
        return "full date"

    if p == "" or p == " ":
        return "blank"

    return "other"


def get_replaced_text(
    entity: str,
    randformat: dict | None = None,
    profile: NoteProfile | None = None,
) -> tuple[str, str] | None:
    """Return ``(surface_text, brat_entity_type)`` or ``None`` if unsupported.

    ``profile`` provides within-note consistency for names, dates, age, and MRN.
    ``randformat`` controls date/hospital formatting; defaults to :func:`getrandformat`.
    """
    fake = get_faker()
    if randformat is None:
        randformat = getrandformat()

    # ------------------------------------------------------------------ names
    if entity == "first name":
        name = profile.patient_first if profile else fake.first_name()
        return (name, "NAME")
    if entity == "last name":
        name = profile.patient_last if profile else fake.last_name()
        return (name, "NAME")
    if entity == "full name":
        name = profile.patient_name if profile else generate_name()
        return (name, "NAME")
    if entity in ("dictator info", "attending info", "cc contact info"):
        name = profile.attending_name if profile else generate_name()
        return (name, "NAME")

    # ------------------------------------------------------------------ dates
    def _admit_offset(days: int = 0) -> date:
        base = profile.admit_date if profile else fake.date_between("-5y", "today")
        return base + timedelta(days=days)

    if entity == "full date":
        d = _admit_offset(random.randint(-7, 30))
        fmt = str(randformat.get("fulldateformats", "%Y-%m-%d"))
        sep = str(randformat.get("dateseperators", "-"))
        lz = bool(randformat.get("leadingzeroes", False))
        parts = d.strftime(fmt).split("-")
        if not lz:
            parts = [p.lstrip("0") or "0" for p in parts]
        return (sep.join(parts), "DATE")

    if entity == "month day":
        d = _admit_offset(random.randint(-7, 30))
        sep = str(randformat.get("dateseperators", "-"))
        lz = bool(randformat.get("leadingzeroes", False))
        m = str(d.month) if not lz else f"{d.month:02d}"
        day = str(d.day) if not lz else f"{d.day:02d}"
        return (f"{m}{sep}{day}", "DATE")

    if entity == "month year":
        d = _admit_offset(random.randint(-30, 60))
        sep = str(randformat.get("dateseperators", "-"))
        lz = bool(randformat.get("leadingzeroes", False))
        m = str(d.month) if not lz else f"{d.month:02d}"
        return (f"{m}{sep}{d.year}", "DATE")

    if entity == "month day alpha":
        d = _admit_offset(random.randint(-7, 30))
        abrv = bool(randformat.get("abrv", False))
        month = _MONTH_NAMES[d.month - 1][:3] if abrv else _MONTH_NAMES[d.month - 1]
        return (f"{month} {d.day}", "DATE")

    if entity == "month year alpha":
        d = _admit_offset(random.randint(-30, 60))
        abrv = bool(randformat.get("abrv", False))
        month = _MONTH_NAMES[d.month - 1][:3] if abrv else _MONTH_NAMES[d.month - 1]
        return (f"{month} {d.year}", "DATE")

    if entity == "day month alpha":
        d = _admit_offset(random.randint(-7, 30))
        abrv = bool(randformat.get("abrv", False))
        month = _MONTH_NAMES[d.month - 1][:3] if abrv else _MONTH_NAMES[d.month - 1]
        return (f"{d.day} {month}", "DATE")

    if entity == "year month alpha":
        d = _admit_offset(random.randint(-30, 60))
        abrv = bool(randformat.get("abrv", False))
        month = _MONTH_NAMES[d.month - 1][:3] if abrv else _MONTH_NAMES[d.month - 1]
        return (f"{d.year} {month}", "DATE")

    if entity == "date range":
        start = _admit_offset(random.randint(-3, 3))
        end = start + timedelta(days=random.randint(1, 30))
        fmt = str(randformat.get("date_range_fmt", "iso"))
        if fmt == "slash":
            return (f"{start.month}/{start.day} - {end.month}/{end.day}", "DATE")
        if fmt == "alpha":
            sm = _MONTH_NAMES[start.month - 1]
            em = _MONTH_NAMES[end.month - 1]
            return (f"{sm} {start.day} to {em} {end.day}", "DATE")
        # iso
        return (f"{start.strftime('%Y-%m-%d')} to {end.strftime('%Y-%m-%d')}", "DATE")

    if entity == "month only":
        d = _admit_offset(random.randint(-30, 30))
        abrv = bool(randformat.get("abrv", False))
        month = _MONTH_NAMES[d.month - 1][:3] if abrv else _MONTH_NAMES[d.month - 1]
        return (month, "DATE")

    if "year" in entity:
        d = _admit_offset(random.randint(-365, 365))
        return (str(d.year), "DATE")

    if entity == "holiday":
        return (
            random.choice([
                "Christmas", "Thanksgiving", "New Year's Day", "Independence Day",
                "Labor Day", "Memorial Day", "Easter",
            ]),
            "DATE",
        )

    # ------------------------------------------------------------------ hospital
    if entity == "hospital":
        return (fake.hospital_namev2(), "HOSPITAL")
    if entity == "hospital ward":
        return (fake.hospital_ward(abrv=bool(randformat.get("abrv", False))), "LOCATION")
    if entity == "hospital unit":
        return (fake.hospital_unit(abrv=bool(randformat.get("abrv", False))), "LOCATION")
    if entity == "university":
        return (fake.university_name(), "ORGANIZATION")

    # ------------------------------------------------------------------ phone
    if entity == "phone number":
        area = str(fake.random_number(digits=3)).zfill(3)
        prefix = str(fake.random_number(digits=3)).zfill(3)
        line = str(fake.random_number(digits=4)).zfill(4)
        if random.random() < 0.5:
            return (f"({area}) {prefix}-{line}", "PHONE")
        return (f"{area}-{prefix}-{line}", "PHONE")
    if entity == "pager number":
        return (f"P{str(fake.random_number(digits=6)).zfill(6)}", "PHONE")

    # ------------------------------------------------------------------ IDs
    if entity == "medical license number":
        return (str(fake.random_number(digits=random.randint(6, 8))), "ID")
    if entity == "job id":
        return (str(fake.random_number(digits=random.randint(4, 6))), "ID")
    if entity == "numeric id":
        return (str(fake.random_number(digits=random.randint(4, 6))), "ID")
    if entity == "unit number":
        return (f"UNIT{str(fake.random_number(digits=4)).zfill(4)}", "ID")
    if entity == "serial number":
        return (f"SN{str(fake.random_number(digits=10)).zfill(10)}", "ID")
    if entity == "clip number":
        return (f"CLIP{str(fake.random_number(digits=6)).zfill(6)}", "ID")
    if entity == "social security number":
        return (fake.ssn(), "ID")
    if entity == "medical record number":
        mrn = profile.mrn if profile else f"MRN{str(fake.random_number(digits=8)).zfill(8)}"
        return (mrn, "ID")

    # ------------------------------------------------------------------ contact
    if entity == "e-mail":
        return (fake.email(), "ID")
    if entity == "url":
        return (fake.url(), "ID")

    # ------------------------------------------------------------------ age
    if entity == "age over 90":
        return (str(random.randint(90, 110)), "AGE")
    if entity == "age":
        age = profile.age if profile else max(1, min(89, int(random.gauss(62, 18))))
        return (str(age), "AGE")

    # ------------------------------------------------------------------ geography
    if entity == "street address":
        return (f"{fake.building_number()} {fake.street_name()}", "LOCATION")
    if entity == "apartment address":
        apt = f"Apt {random.randint(1, 999)}"
        return (f"{fake.building_number()} {fake.street_name()}, {apt}", "LOCATION")
    if entity == "location":
        return (fake.street_address(), "LOCATION")
    if entity == "po box":
        return (f"PO Box {str(fake.random_number(digits=5)).zfill(5)}", "LOCATION")
    if entity == "country":
        return (fake.country(), "LOCATION")
    if entity == "state":
        return (fake.state(), "LOCATION")

    # ------------------------------------------------------------------ org
    if entity == "company":
        return (fake.company(), "ORGANIZATION")

    if entity == "blank":
        return ("", "BLANK")

    logger.debug("no replacement template for entity %r", entity)
    return None
