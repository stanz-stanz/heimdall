"""Static enrichments: company form, industry lookup, GDPR flag, contactable."""

from __future__ import annotations

import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

_CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "config"


def _load_json(filename: str) -> dict | list:
    with open(_CONFIG_DIR / filename, encoding="utf-8") as f:
        return json.load(f)


def load_company_forms() -> dict[str, str]:
    """Load company form normalization map from config/company_forms.json."""
    return _load_json("company_forms.json")


def load_industry_codes() -> dict[str, str]:
    """Load industry code → English name map from config/industry_codes.json."""
    return _load_json("industry_codes.json")


def load_gdpr_industry_codes() -> dict[str, str]:
    """Load GDPR-sensitive industry code prefixes from config/gdpr_signals.json."""
    signals = _load_json("gdpr_signals.json")
    return signals.get("industry_codes", {})


def load_free_webmail() -> frozenset[str]:
    """Load free webmail provider domains from config/free_webmail.json."""
    return frozenset(_load_json("free_webmail.json"))


def normalize_company_form(raw_form: str, form_map: dict[str, str]) -> str:
    """Map a raw company form string to its abbreviation.

    Returns the abbreviation if found, otherwise the raw form unchanged.
    """
    return form_map.get(raw_form, raw_form)


def lookup_industry_name(code: str, industry_map: dict[str, str]) -> str:
    """Look up the English name for an industry code.

    Tries exact match first, then progressively shorter prefixes.
    """
    if not code:
        return ""
    if code in industry_map:
        return industry_map[code]
    # Try shorter prefixes: 561110 → 56111 → 5611 → 561 → 56
    for length in range(len(code) - 1, 1, -1):
        prefix = code[:length]
        if prefix in industry_map:
            return industry_map[prefix]
    return ""


def check_gdpr_industry(code: str, gdpr_codes: dict[str, str]) -> tuple[bool, str]:
    """Check if an industry code prefix-matches a GDPR-sensitive category.

    Returns (is_sensitive, reason_text). Longest prefix match wins.
    """
    if not code:
        return False, ""
    # Sort by prefix length descending → longest match first
    for prefix in sorted(gdpr_codes.keys(), key=len, reverse=True):
        if code.startswith(prefix):
            return True, gdpr_codes[prefix]
    return False, ""


def extract_email_domain(email: str) -> str:
    """Get the domain part from an email address, lowercased."""
    if not email or "@" not in email:
        return ""
    return email.rsplit("@", 1)[1].strip().lower()


def is_free_webmail(domain: str, webmail_set: frozenset[str]) -> bool:
    """Check if a domain is a free webmail provider."""
    return domain in webmail_set
