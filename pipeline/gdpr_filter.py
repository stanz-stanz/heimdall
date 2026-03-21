"""GDPR-sensitive industry filter based on CVR branchekoder."""

from __future__ import annotations

import logging

from pipeline.config import GDPR_SENSITIVE_CODES
from pipeline.cvr import Company

log = logging.getLogger(__name__)


def is_gdpr_sensitive(industry_code: str) -> tuple[bool, str]:
    """Check if an industry code indicates GDPR-sensitive sector. Returns (sensitive, reason)."""
    if not industry_code:
        return False, ""

    # Check from most specific to least specific prefix
    for prefix in sorted(GDPR_SENSITIVE_CODES.keys(), key=len, reverse=True):
        if industry_code.startswith(prefix):
            return True, GDPR_SENSITIVE_CODES[prefix]

    return False, ""


def flag_gdpr_sensitive(companies: list[Company]) -> dict[str, tuple[bool, str]]:
    """Flag GDPR-sensitive companies. Returns dict of cvr -> (sensitive, reason)."""
    results: dict[str, tuple[bool, str]] = {}
    sensitive_count = 0

    for company in companies:
        sensitive, reason = is_gdpr_sensitive(company.industry_code)
        results[company.cvr] = (sensitive, reason)
        if sensitive:
            sensitive_count += 1

    log.info("GDPR filter: %d of %d companies flagged as sensitive", sensitive_count, len(companies))
    return results
