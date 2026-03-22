"""Brief generator: assemble per-site JSON briefs matching the SKILL.md schema."""

from __future__ import annotations

import logging
from datetime import date

from pipeline.cvr import Company
from pipeline.scanner import ScanResult

log = logging.getLogger(__name__)


def generate_brief(
    company: Company,
    scan: ScanResult,
    bucket: str,
    gdpr_sensitive: bool,
) -> dict:
    """Generate a per-site brief matching docs/agents/prospecting/SKILL.md schema."""
    # Build risk summary
    risk_factors = []
    if scan.cms and "wordpress" in scan.cms.lower():
        risk_factors.append(f"Self-hosted {scan.cms}")
        if scan.hosting:
            risk_factors.append(f"on {scan.hosting}")
    elif scan.cms:
        risk_factors.append(f"Self-hosted {scan.cms}")

    if not scan.ssl_valid:
        risk_factors.append("SSL invalid or missing")
    elif scan.ssl_days_remaining >= 0 and scan.ssl_days_remaining < 30:
        risk_factors.append(f"SSL expiring in {scan.ssl_days_remaining} days")

    if not scan.headers.get("x_frame_options"):
        risk_factors.append("Missing X-Frame-Options")
    if not scan.headers.get("content_security_policy"):
        risk_factors.append("Missing Content-Security-Policy")
    if not scan.headers.get("strict_transport_security"):
        risk_factors.append("Missing HSTS")

    priority = {"A": "HIGH", "B": "HIGH", "E": "MEDIUM", "C": "LOWER", "D": "SKIP"}.get(bucket, "UNKNOWN")
    risk_summary = ". ".join(risk_factors) + f". Priority: {priority}." if risk_factors else f"Priority: {priority}."

    # Build sales hook
    hooks = []
    if scan.ssl_days_remaining >= 0 and scan.ssl_days_remaining < 30:
        hooks.append(f"SSL certificate expires in {scan.ssl_days_remaining} days")
    if not scan.headers.get("strict_transport_security"):
        hooks.append("No HSTS header — browser connections not enforced as HTTPS")

    sales_hook = ". ".join(hooks) + "." if hooks else ""

    # Plugin names — clean up wp-content/plugins/ slugs
    plugin_names = [p.replace("-", " ").title() for p in scan.detected_plugins]

    return {
        "domain": company.website_domain,
        "cvr": company.cvr,
        "company_name": company.name,
        "scan_date": date.today().isoformat(),
        "bucket": bucket,
        "gdpr_sensitive": gdpr_sensitive,
        "industry": company.industry_name,
        "technology": {
            "cms": scan.cms,
            "hosting": scan.hosting or "Unknown",
            "ssl": {
                "valid": scan.ssl_valid,
                "issuer": scan.ssl_issuer,
                "expiry": scan.ssl_expiry,
                "days_remaining": scan.ssl_days_remaining,
            },
            "server": scan.server,
            "detected_plugins": plugin_names,
            "headers": scan.headers,
        },
        "tech_stack": scan.tech_stack,
        "risk_summary": risk_summary,
        "sales_hook": sales_hook,
    }
