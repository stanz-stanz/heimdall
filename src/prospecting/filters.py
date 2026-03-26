"""Pipeline filters: load and apply configurable filters from JSON."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from .cvr import Company

log = logging.getLogger(__name__)

VALID_KEYS = {"industry_code", "contactable", "bucket"}


def load_filters(path: Path) -> dict:
    """Load filters from a JSON file. Returns empty dict if file is missing."""
    if not path.exists():
        log.info("No filters file at %s — processing all companies", path.name)
        return {}

    with open(path, encoding="utf-8") as f:
        filters = json.load(f)

    unknown = set(filters.keys()) - VALID_KEYS
    if unknown:
        log.warning("Unknown filter keys ignored: %s", ", ".join(sorted(unknown)))

    active = {k: v for k, v in filters.items() if k in VALID_KEYS}
    if active:
        log.info("Active filters: %s", active)
    else:
        log.info("Filters file loaded but empty — processing all companies")

    return active


def apply_pre_scan_filters(companies: list[Company], filters: dict) -> list[Company]:
    """Apply industry_code and contactable filters before scanning. Mutates discard_reason."""
    industry_prefixes = filters.get("industry_code")
    contactable_filter = filters.get("contactable")

    if industry_prefixes is None and contactable_filter is None:
        return companies

    excluded = 0
    for company in companies:
        if company.discarded:
            continue

        if industry_prefixes is not None:
            if not any(company.industry_code.startswith(prefix) for prefix in industry_prefixes):
                company.discard_reason = "filtered:industry_code"
                excluded += 1
                continue

        if contactable_filter is not None:
            is_contactable = not company.ad_protected
            if is_contactable != contactable_filter:
                company.discard_reason = "filtered:contactable"
                excluded += 1
                continue

    log.info("Pre-scan filters excluded %d companies", excluded)
    return companies


def apply_post_scan_filters(
    companies: list[Company],
    buckets: dict[str, str],
    filters: dict,
) -> list[Company]:
    """Apply bucket filter after bucketing. Mutates discard_reason."""
    bucket_filter = filters.get("bucket")
    if bucket_filter is None:
        return companies

    allowed = {b.upper() for b in bucket_filter}
    excluded = 0
    for company in companies:
        if company.discarded:
            continue
        bucket = buckets.get(company.cvr, "D")
        if bucket not in allowed:
            company.discard_reason = f"filtered:bucket:{bucket}"
            excluded += 1

    log.info("Post-scan bucket filter excluded %d companies", excluded)
    return companies
