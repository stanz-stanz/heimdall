"""Bucketing logic: classify companies A-E based on scan results."""

from __future__ import annotations

import logging

from .config import BUCKET_A_CMS, BUCKET_B_CMS, BUCKET_C_PLATFORMS
from .cvr import Company
from .scanner import ScanResult

log = logging.getLogger(__name__)

BUCKET_LABELS = {
    "A": "HIGHEST — Self-hosted WordPress on shared hosting",
    "B": "HIGH — Other self-hosted CMS",
    "E": "MEDIUM — Custom-built or unidentifiable",
    "C": "LOWER — Hosted platform",
    "D": "SKIP — No website or parked domain",
}


def classify(company: Company, scan: ScanResult | None) -> str:
    """Assign a bucket (A-E) based on CMS and hosting detection."""
    if company.discarded or not scan:
        return "D"

    cms_lower = scan.cms.lower() if scan.cms else ""
    tech_lower = " ".join(scan.tech_stack).lower()

    # Check for hosted platforms first (Bucket C)
    for platform in BUCKET_C_PLATFORMS:
        if platform in cms_lower or platform in tech_lower:
            return "C"

    # Bucket A: WordPress on shared/generic hosting
    if cms_lower in BUCKET_A_CMS or "wordpress" in tech_lower or "woocommerce" in tech_lower:
        return "A"

    # Bucket B: Other self-hosted CMS
    for cms in BUCKET_B_CMS:
        if cms in cms_lower or cms in tech_lower:
            return "B"

    # If we detected some technology but no CMS — custom/unidentifiable
    if scan.tech_stack or scan.server:
        return "E"

    # No scan data at all
    return "D"


def assign_buckets(companies: list[Company], scan_results: dict[str, ScanResult]) -> dict[str, str]:
    """Assign buckets to all companies. Returns dict of cvr -> bucket."""
    buckets: dict[str, str] = {}

    for company in companies:
        scan = scan_results.get(company.website_domain) if company.website_domain else None
        bucket = classify(company, scan)
        buckets[company.cvr] = bucket

    counts = {}
    for b in buckets.values():
        counts[b] = counts.get(b, 0) + 1

    log.info("Bucket distribution: %s", ", ".join(f"{k}: {v}" for k, v in sorted(counts.items())))
    return buckets
