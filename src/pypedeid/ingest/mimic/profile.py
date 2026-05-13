"""Per-note synthetic identity for within-note PHI consistency."""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date


@dataclass
class NoteProfile:
    """Holds consistent synthetic identities for one clinical note."""

    patient_first: str
    patient_last: str
    attending_first: str
    attending_last: str
    admit_date: date
    mrn: str
    age: int

    @property
    def patient_name(self) -> str:
        return f"{self.patient_first} {self.patient_last}"

    @property
    def attending_name(self) -> str:
        return f"{self.attending_first} {self.attending_last}"


def make_note_profile(admit_date: date | None = None) -> NoteProfile:
    """Generate a synthetic identity profile for a single note.

    If admit_date is provided (e.g. from CHARTDATE column), generated dates
    will be anchored to it for temporal coherence.
    """
    from pypedeid.ingest.mimic.faker_providers import get_faker

    fake = get_faker()

    if admit_date is None:
        admit_date = fake.date_between(start_date="-5y", end_date="today")

    # Clinical inpatient population skews adult; Gaussian(62, 18) clamped 1–89
    age = max(1, min(89, int(random.gauss(62, 18))))

    return NoteProfile(
        patient_first=fake.first_name(),
        patient_last=fake.last_name(),
        attending_first=fake.first_name(),
        attending_last=fake.last_name(),
        admit_date=admit_date,
        mrn=f"MRN{str(fake.random_number(digits=8)).zfill(8)}",
        age=age,
    )
