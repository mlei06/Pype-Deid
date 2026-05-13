"""Synthetic multi-locale person names."""

from __future__ import annotations

import random

from faker import Faker

locale_weights = {
    "en_US": 0.4,
    "en_GB": 0.2,
    "en_CA": 0.1,
    "zh_CN": 0.1,
    "ja_JP": 0.05,
    "ko_KR": 0.05,
    "hi_IN": 0.05,
    "ar_EG": 0.05,
}

# Faker instances for all locales (non-English may produce transliterated names)
_fakers: dict[str, Faker] = {}


def _get_locale_faker(locale: str) -> Faker:
    if locale not in _fakers:
        _fakers[locale] = Faker(locale)
    return _fakers[locale]


def generate_name(locale: str | None = None) -> str:
    """Return a synthetic name in one of several clinical-note surface forms."""
    if locale is None:
        locale = random.choices(
            population=list(locale_weights.keys()),
            weights=list(locale_weights.values()),
            k=1,
        )[0]

    fake = _get_locale_faker(locale)
    try:
        first = fake.first_name()
        last = fake.last_name()
    except Exception:
        # Fallback to en_US if locale provider fails
        fake = _get_locale_faker("en_US")
        first = fake.first_name()
        last = fake.last_name()

    # Surface form weights: full_title most common, last_only and title_last
    # common in clinical notes, full_lower rare but present
    format_style = random.choices(
        ["full_title", "last_only", "title_last", "initial_title", "full_lower"],
        weights=[0.45, 0.20, 0.15, 0.12, 0.08],
        k=1,
    )[0]

    if format_style == "full_title":
        return f"{first.capitalize()} {last.capitalize()}"
    if format_style == "last_only":
        return last.capitalize()
    if format_style == "title_last":
        title = random.choice(["Dr.", "Mr.", "Ms.", "Mrs."])
        return f"{title} {last.capitalize()}"
    if format_style == "initial_title":
        return f"{first[0].upper()}. {last.capitalize()}"
    # full_lower
    return f"{first.lower()} {last.lower()}"
