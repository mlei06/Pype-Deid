"""Faker providers and random date-format options for MIMIC placeholder replacement."""

from __future__ import annotations

import random
from typing import Any

from faker import Faker
from faker.providers import BaseProvider


class DateExtraProvider(BaseProvider):
    def full_date(
        self,
        pattern: str = "%Y-%m-%d",
        seperator: str = "-",
        leadingzeroes: bool = False,
    ) -> str:
        date = self.generator.date(pattern=pattern)
        if not leadingzeroes:
            dateparts = date.split("-")
            for i, part in enumerate(dateparts):
                if part and part[0] == "0":
                    dateparts[i] = part[1:]
            date = seperator.join(dateparts)
        return date

    def month_day(
        self,
        pattern: str = "%m-%d",
        seperator: str = "-",
        leadingzeroes: bool = False,
    ) -> str:
        date = self.generator.date(pattern=pattern)
        if not leadingzeroes:
            dateparts = date.split("-")
            for i, part in enumerate(dateparts):
                if part and part[0] == "0":
                    dateparts[i] = part[1:]
            date = seperator.join(dateparts)
        return date

    def month_year(
        self,
        pattern: str = "%m-%Y",
        seperator: str = "-",
        leadingzeroes: bool = False,
    ) -> str:
        date = self.generator.date(pattern=pattern)
        if not leadingzeroes:
            dateparts = date.split("-")
            for i, part in enumerate(dateparts):
                if part and part[0] == "0":
                    dateparts[i] = part[1:]
            date = seperator.join(dateparts)
        return date

    def month_day_alpha(self, abrv: bool = False, leadingzeroes: bool = False) -> str:
        month = self.generator.month_name()[:3] if abrv else self.generator.month_name()
        day = self.generator.day_of_month()
        if not leadingzeroes and day and day[0] == "0":
            day = day[1:]
        return f"{month} {day}"

    def month_year_alpha(self, abrv: bool = False, leadingzeroes: bool = False) -> str:
        del leadingzeroes  # unused; signature kept for API compatibility
        month = self.generator.month_name()[:3] if abrv else self.generator.month_name()
        year = self.generator.year()
        return f"{month} {year}"

    def day_month_alpha(self, abrv: bool = False, leadingzeroes: bool = False) -> str:
        month = self.generator.month_name()[:3] if abrv else self.generator.month_name()
        day = self.generator.day_of_month()
        if not leadingzeroes and day and day[0] == "0":
            day = day[1:]
        return f"{day} {month}"

    def year_month_alpha(self, abrv: bool = False, leadingzeroes: bool = False) -> str:
        del leadingzeroes
        month = self.generator.month_name()[:3] if abrv else self.generator.month_name()
        year = self.generator.year()
        return f"{year} {month}"


class UniversityExtraProvider(BaseProvider):
    def university_name(self) -> str:
        g = self.generator
        name_styles = [
            lambda: f"{g.last_name()} University",
            lambda: f"University of {g.city()}",
            lambda: f"{g.city()} State University",
            lambda: f"{g.last_name()} College",
            lambda: f"{g.state()} Institute of Technology",
            lambda: f'{g.last_name()} School of {random.choice(["Engineering", "Medicine", "Business", "Arts"])}',
            lambda: f"{random.choice(['North', 'South', 'East', 'West'])} {g.last_name()} University",
            lambda: f"{g.first_name()} {g.last_name()} University",
        ]
        return random.choice(name_styles)()


class HospitalExtraProvider(BaseProvider):
    def __init__(self, generator: Any) -> None:
        super().__init__(generator)
        self.suffixes = [
            ("Hospital", 30),
            ("Clinic", 25),
            ("Medical", 20),
            ("Center", 15),
            ("Medical Center", 10),
            ("Health", 10),
            ("Health System", 8),
            ("Care Center", 8),
            ("Health Institute", 5),
            ("hosp", 5),
            ("Med", 5),
        ]

    def hospital_namev2(self) -> str:
        base_names = [
            "Anderson",
            "Bennett",
            "Crawford",
            "Davidson",
            "Ellis",
            "Foster",
            "Garcia",
            "Harrison",
            "Jackson",
            "Klein",
            "Lawson",
            "Mason",
            "Nguyen",
            "Owens",
            "Patel",
            "Quinn",
            "Reynolds",
            "Sullivan",
            "Thompson",
            "Underwood",
            "Vasquez",
            "Walker",
            "Young",
            "Zimmerman",
            "St. Mary",
            "St. Joseph",
            "St. Luke",
            "St. Andrew",
            "St. Anne",
            "St. Francis",
            "St. John",
            "St. George",
            "St. Elizabeth",
            "St. Nicholas",
            "St. Michael",
            "St. David",
            "St. Teresa",
            "St. Peter",
            "St. Catherine",
            "Springfield",
            "Brookside",
            "Rivertown",
            "Lakeside",
            "Cedar Hill",
            "Oakridge",
            "Westfield",
            "Greenwood",
            "Maple Valley",
            "Hillcrest",
            "Clearwater",
            "Ironwood",
            "Rockford",
            "Brighton",
            "Charleston",
            "Redwood",
            "Foxborough",
            "Newport",
            "Ashford",
            "Lexington",
            "Riverbend",
            "Silver Lake",
            "Hope",
            "Mercy",
            "Grace",
            "Unity",
            "Covenant",
            "Trinity",
            "Legacy",
            "Summit",
            "Harmony",
            "Pioneer",
            "Foundation",
            "Vanguard",
            "Renewal",
            "Noble",
            "Guardian",
            "Solace",
            "Integrity",
            "Resilience",
            "Evergreen",
            "BrightPath",
            "Wellbridge",
            "Medora",
            "CarePoint",
            "Healcrest",
            "Truvida",
            "Vitalis",
            "Optira",
            "NovaCare",
            "VivaHealth",
            "Altruva",
            "Clearpath",
            "Alevia",
            "Harmona",
            "Neurovia",
        ]
        suffixes = [
            "Medical",
            "Center",
            "Health",
            "Clinic",
            "Memorial",
            "Children's Hospital",
            "Health Center",
            "Hospital",
            "hosp",
            "",
        ]
        name = random.choice(base_names)
        suffix = random.choice(suffixes)
        return f"{name} {suffix}".strip()

    def hospital_ward(
        self,
        abrv: bool | None = None,
        lower: bool | None = None,
        suffixlower: bool | None = None,
    ) -> str:
        if abrv is None:
            abrv = random.choice([True, False])
        if lower is None:
            lower = random.choice([True, False])
        if suffixlower is None:
            suffixlower = random.choice([True, False])
        wards = [
            ("Medical", "Med"),
            ("Surgical", "Surg"),
            ("Pediatric", "Peds"),
            ("Maternity", "MAT"),
            ("General", "Gen"),
            ("Rehabilitation", "Rehab"),
            ("Oncology", "Onc"),
            ("Orthopedic", "Ortho"),
            ("Psychiatric", "Psych"),
            ("Geriatric", "Geri"),
            ("Neurology", "Neuro"),
            ("Gastroenterology", "GI"),
            ("Urology", "Uro"),
            ("Obstetrics", "OB"),
            ("Gynecology", "Gyn"),
        ]
        suffixes = ["Ward", "Unit", "Floor", "department"]
        ward = random.choice(wards)
        ward = ward[1] if abrv else ward[0]
        if lower:
            ward = ward.lower()
        if random.random() < 0.5:
            suffix = random.choice(suffixes)
            if not lower and suffixlower:
                suffix = suffix.lower()
            return f"{ward} {suffix}"
        return ward

    def hospital_unit(
        self,
        abrv: bool | None = None,
        lower: bool | None = None,
        suffixlower: bool | None = None,
    ) -> str:
        if abrv is None:
            abrv = random.choice([True, False])
        if lower is None:
            lower = random.choice([True, False])
        if suffixlower is None:
            suffixlower = False if lower else random.choice([True, False])
        hospital_units = [
            ("Intensive Care", "ICU"),
            ("Coronary Care", "CCU"),
            ("Neonatal Intensive Care", "NICU"),
            ("Emergency", "ED"),
            ("Dialysis", "Dial"),
            ("Burn", "Burn"),
            ("Cardiac Care", "Card"),
            ("Step-Down", "SDU"),
            ("Post-Anesthesia Care", "PACU"),
            ("Cardiology", "Card"),
            ("Stroke", "Stroke"),
            ("Surgical Intensive Care", "SICU"),
            ("Pediatric Intensive Care", "PICU"),
        ]
        suffixes = ["Unit", "Department"]
        unit = random.choice(hospital_units)
        unit = unit[1] if abrv else unit[0]
        if lower:
            unit = unit.lower()
        if not abrv and random.random() < 0.5:
            suffix = random.choice(suffixes)
            if not lower and suffixlower:
                suffix = suffix.lower()
            return f"{unit} {suffix}"
        return unit


def getrandformat() -> dict[str, Any]:
    return {
        "fulldateformats": random.choice(["%Y-%m-%d", "%m-%d-%Y"]),
        "dateseperators": random.choice(["-", "-", "/", "/", "."]),
        "leadingzeroes": random.choice([True, False]),
        "abrv": random.choice([True, False]),
        "hospital_prefix": random.choice([True, False]),
        "hospital_suffix": random.choice([True, False]),
        "date_range_fmt": random.choice(["iso", "iso", "slash", "alpha"]),
    }


_fake_with_providers: Faker | None = None


def get_faker() -> Faker:
    global _fake_with_providers
    if _fake_with_providers is None:
        f = Faker()
        f.add_provider(DateExtraProvider)
        f.add_provider(UniversityExtraProvider)
        f.add_provider(HospitalExtraProvider)
        _fake_with_providers = f
    return _fake_with_providers
