"""Per-label surrogate replacement strategies backed by Faker."""

from __future__ import annotations

import random

from faker import Faker

from pypedeid.pipes.surrogate.packs import get_surrogate_pack


def _default_label_to_strategy() -> dict[str, str]:
    """Read the active surrogate pack from settings (falls back to ``clinical_phi``)."""
    try:
        from pypedeid.config import get_settings

        return dict(get_surrogate_pack(get_settings().surrogate_pack_name).label_to_strategy)
    except KeyError:
        return dict(get_surrogate_pack("clinical_phi").label_to_strategy)


class SurrogateGenerator:
    """Generate consistent fake replacements within a document scope.

    Same ``(label, original_text)`` pair always produces the same surrogate
    for the lifetime of this generator (or until :meth:`reset` is called).

    *label_to_strategy* is the ``label → strategy`` map from a surrogate pack.
    When unset, resolves to the pack named by ``Settings.surrogate_pack_name``.
    """

    def __init__(
        self,
        seed: int | None = None,
        *,
        consistency: bool = True,
        label_to_strategy: dict[str, str] | None = None,
    ) -> None:
        self._faker = Faker()
        if seed is not None:
            self._faker.seed_instance(seed)
            random.seed(seed)
        self._consistency = consistency
        self._label_to_strategy = (
            dict(label_to_strategy)
            if label_to_strategy is not None
            else _default_label_to_strategy()
        )
        self._map: dict[tuple[str, str], str] = {}

    def replace(self, label: str, original_text: str) -> str:
        """Return a surrogate for *label* and *original_text*."""
        if self._consistency:
            key = (label.upper(), original_text)
            cached = self._map.get(key)
            if cached is not None:
                return cached
            result = self._generate(label, original_text)
            self._map[key] = result
            return result
        return self._generate(label, original_text)

    def reset(self) -> None:
        """Clear the consistency map (call between documents)."""
        self._map.clear()

    # ------------------------------------------------------------------
    # Label dispatch — strategy names come from SURROGATE_STRATEGIES
    # ------------------------------------------------------------------

    def _generate(self, label: str, original_text: str) -> str:
        strategy = self._label_to_strategy.get(label.upper())
        if strategy == "Name":
            return self._gen_name(original_text)
        if strategy == "Date":
            return self._gen_date(original_text)
        if strategy == "Phone":
            return self._faker.phone_number()
        if strategy == "Email":
            return self._faker.email()
        if strategy == "ID":
            return self._gen_id(original_text)
        if strategy == "Address":
            return self._faker.street_address()
        if strategy == "Postal Code":
            return self._faker.postalcode()
        if strategy == "Organization":
            return self._faker.company()
        if strategy == "Age":
            return str(random.randint(20, 89))
        if strategy == "Country":
            return self._faker.country()
        if strategy == "State":
            return self._faker.state()
        if strategy == "URL":
            return self._faker.url()
        return "*" * len(original_text)

    def _gen_name(self, original: str) -> str:
        parts = original.split()
        if len(parts) >= 2:
            return f"{self._faker.first_name()} {self._faker.last_name()}"
        if original and original[0].isupper():
            return self._faker.first_name()
        return self._faker.last_name()

    def _gen_date(self, original: str) -> str:
        fake_date = self._faker.date_between(start_date="-10y", end_date="today")
        if "/" in original:
            return fake_date.strftime("%m/%d/%Y")
        if "-" in original:
            return fake_date.strftime("%Y-%m-%d")
        return fake_date.strftime("%b %d, %Y")

    def _gen_id(self, original: str) -> str:
        n = max(len(original), 4)
        return str(self._faker.random_number(digits=n)).zfill(n)
