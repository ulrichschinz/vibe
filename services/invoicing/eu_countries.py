"""EU-Mitgliedsstaaten (ISO-3166-1 alpha-2), ohne Deutschland.

Stand 2026: Großbritannien (GB) ist seit 2021 nicht mehr Mitglied.
"""
from __future__ import annotations

EU_COUNTRY_CODES: frozenset[str] = frozenset({
    "AT",  # Austria
    "BE",  # Belgium
    "BG",  # Bulgaria
    "CY",  # Cyprus
    "CZ",  # Czech Republic
    "DK",  # Denmark
    "EE",  # Estonia
    "ES",  # Spain
    "FI",  # Finland
    "FR",  # France
    "GR",  # Greece (auch EL möglich; ISO-Standard ist GR)
    "HR",  # Croatia
    "HU",  # Hungary
    "IE",  # Ireland
    "IT",  # Italy
    "LT",  # Lithuania
    "LU",  # Luxembourg
    "LV",  # Latvia
    "MT",  # Malta
    "NL",  # Netherlands
    "PL",  # Poland
    "PT",  # Portugal
    "RO",  # Romania
    "SE",  # Sweden
    "SI",  # Slovenia
    "SK",  # Slovakia
})


def is_eu_country(code: str | None) -> bool:
    if not code:
        return False
    return code.upper() in EU_COUNTRY_CODES
