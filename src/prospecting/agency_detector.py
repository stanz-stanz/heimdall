"""Agency detection: identify web agencies from footer credits, meta author tags, and shared hosting."""

from collections import defaultdict

from loguru import logger

from .cvr import Company
from .scanners.models import ScanResult

AGENCY_THRESHOLD = 5  # minimum sites to generate an agency brief


def detect_agencies(
    companies: list[Company],
    scan_results: dict[str, ScanResult],
    buckets: dict[str, str],
) -> list[dict]:
    """Detect web agencies and generate agency briefs for those with 5+ sites."""
    # Group by meta_author and footer_credit
    author_groups: dict[str, list[str]] = defaultdict(list)
    credit_groups: dict[str, list[str]] = defaultdict(list)

    for company in companies:
        if company.discarded or not company.website_domain:
            continue
        scan = scan_results.get(company.website_domain)
        if not scan:
            continue

        if scan.meta_author:
            key = scan.meta_author.strip().lower()
            author_groups[key].append(company.website_domain)

        if scan.footer_credit:
            key = scan.footer_credit.strip().lower()
            credit_groups[key].append(company.website_domain)

    # Merge detections — prefer footer credit as the label
    agency_sites: dict[str, dict] = {}

    for name, domains in credit_groups.items():
        if len(domains) >= AGENCY_THRESHOLD:
            agency_sites[name] = {"detected_via": "footer credit", "domains": list(set(domains))}

    for name, domains in author_groups.items():
        if name not in agency_sites and len(domains) >= AGENCY_THRESHOLD:
            agency_sites[name] = {"detected_via": "meta author", "domains": list(set(domains))}

    # Build agency briefs
    briefs = []
    for agency_name, info in agency_sites.items():
        domains = info["domains"]
        issues = []
        sites_with_issues = 0

        for domain in domains:
            scan = scan_results.get(domain)
            if not scan:
                continue
            site_issues = []
            if not scan.ssl_valid:
                site_issues.append("invalid SSL")
            elif scan.ssl_days_remaining >= 0 and scan.ssl_days_remaining < 30:
                site_issues.append("SSL expiring soon")
            if not scan.headers.get("strict_transport_security"):
                site_issues.append("missing HSTS")
            if not scan.headers.get("content_security_policy"):
                site_issues.append("missing CSP")
            if site_issues:
                sites_with_issues += 1
                issues.extend(site_issues)

        # Count common issues
        from collections import Counter
        common = [issue for issue, _ in Counter(issues).most_common(5)]

        brief = {
            "agency_name": agency_name.title(),
            "detected_via": info["detected_via"],
            "client_sites": sorted(domains),
            "total_sites": len(domains),
            "sites_with_issues": sites_with_issues,
            "common_issues": common,
            "pitch_angle": f"{sites_with_issues} of {len(domains)} client sites have at least one issue.",
        }
        briefs.append(brief)
        logger.info("Agency detected: {} ({} sites, {} with issues)", agency_name.title(), len(domains), sites_with_issues)

    logger.info("Agency detection complete: {} agencies found", len(briefs))
    return briefs
