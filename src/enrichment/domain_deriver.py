"""Domain derivation: email extraction and company name-match validation."""

from __future__ import annotations

import logging
import re
from difflib import SequenceMatcher

log = logging.getLogger(__name__)

# Suffixes to strip from company names before matching
_NAME_SUFFIXES = re.compile(
    r"\b(aps|a/s|i/s|k/s|ivs|p/s|amba|enk|v/\S+|ved\s+\S+)\s*$",
    re.IGNORECASE,
)

# Characters to normalize in both domain and name
_NORMALIZE_RE = re.compile(r"[^a-z0-9]")

# Name-match threshold: liberal because domain abbreviations are common
NAME_MATCH_THRESHOLD = 0.4


def extract_domain_from_email(email: str) -> str:
    """Get the domain part from an email address, lowercased."""
    if not email or "@" not in email:
        return ""
    return email.rsplit("@", 1)[1].strip().lower()


def _clean_company_name(name: str) -> str:
    """Strip legal suffixes and normalize for comparison."""
    cleaned = name.lower().strip()
    cleaned = _NAME_SUFFIXES.sub("", cleaned).strip()
    return cleaned


def _domain_label(domain: str) -> str:
    """Extract the second-level label from a domain (e.g., 'conrads' from 'conrads.dk')."""
    parts = domain.lower().split(".")
    if len(parts) >= 2:
        return parts[-2]
    return domain.lower()


def _normalize(text: str) -> str:
    """Reduce to lowercase alphanumeric for fuzzy comparison."""
    return _NORMALIZE_RE.sub("", text.lower())


def validate_domain_name_match(domain: str, company_name: str) -> tuple[bool, float]:
    """Check if a domain plausibly belongs to a company by name matching.

    Compares the domain's second-level label against the cleaned company name.
    Also checks if either contains the other as a substring.

    Returns (is_match, ratio).
    """
    if not domain or not company_name:
        return False, 0.0

    label = _domain_label(domain)
    cleaned_name = _clean_company_name(company_name)

    norm_label = _normalize(label)
    norm_name = _normalize(cleaned_name)

    # Substring check: if the domain label appears in the name or vice versa
    if len(norm_label) >= 3 and (norm_label in norm_name or norm_name in norm_label):
        return True, 1.0

    # Fuzzy match
    ratio = SequenceMatcher(None, norm_label, norm_name).ratio()
    return ratio >= NAME_MATCH_THRESHOLD, ratio
