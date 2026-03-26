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
    if scan.exposed_cloud_storage:
        risk_factors.append("Exposed cloud storage bucket detected")

    priority = {"A": "HIGH", "B": "HIGH", "E": "MEDIUM", "C": "LOWER", "D": "SKIP"}.get(bucket, "UNKNOWN")
    risk_summary = ". ".join(risk_factors) + f". Priority: {priority}." if risk_factors else f"Priority: {priority}."

    # Build findings — each with severity (CVSS-aligned), description, and risk
    # Severity levels follow industry standard: critical, high, medium, low, info
    findings = []

    # SSL — expired or missing
    if not scan.ssl_valid and scan.ssl_days_remaining != -1:
        findings.append({
            "severity": "critical",
            "description": "SSL certificate has expired",
            "risk": "Browsers display a full-page security warning to visitors. Most users will leave immediately. Search engines may delist the site.",
        })
    elif scan.ssl_days_remaining == -1:
        findings.append({
            "severity": "critical",
            "description": "No SSL certificate detected",
            "risk": "All traffic between visitors and the website is unencrypted. Any data submitted (forms, bookings, contact details) can be read by third parties on the network.",
        })
    elif scan.ssl_days_remaining < 14:
        findings.append({
            "severity": "high",
            "description": f"SSL certificate expires in {scan.ssl_days_remaining} days",
            "risk": "When it expires, browsers will block access to the site with a security warning. Visitors will not be able to reach the website until the certificate is renewed.",
        })
    elif scan.ssl_days_remaining < 30:
        findings.append({
            "severity": "medium",
            "description": f"SSL certificate expires in {scan.ssl_days_remaining} days",
            "risk": "The certificate will need renewal soon. If missed, browsers will display a security warning and visitors will be unable to access the site.",
        })

    # Security headers
    if not scan.headers.get("strict_transport_security"):
        findings.append({
            "severity": "medium",
            "description": "Missing HSTS header (HTTP Strict Transport Security)",
            "risk": "Browsers are not instructed to always use HTTPS. On unsecured networks (public WiFi), a visitor's first connection could be intercepted before the redirect to HTTPS occurs.",
        })
    if not scan.headers.get("content_security_policy"):
        findings.append({
            "severity": "low",
            "description": "Missing Content-Security-Policy header",
            "risk": "The browser has no restrictions on which scripts can run on the page. If the site is compromised, injected scripts can operate without constraint.",
        })
    if not scan.headers.get("x_frame_options"):
        findings.append({
            "severity": "low",
            "description": "Missing X-Frame-Options header",
            "risk": "The website can be embedded in frames on other sites. This enables clickjacking attacks where users interact with hidden elements overlaid on the legitimate page.",
        })
    if not scan.headers.get("x_content_type_options"):
        findings.append({
            "severity": "low",
            "description": "Missing X-Content-Type-Options header",
            "risk": "Browsers may misinterpret uploaded files as executable content. This is primarily relevant if the site accepts file uploads.",
        })

    # Cloud storage exposure
    if scan.exposed_cloud_storage:
        bucket_count = len(scan.exposed_cloud_storage)
        findings.append({
            "severity": "high",
            "description": f"{bucket_count} exposed cloud storage bucket{'s' if bucket_count > 1 else ''} detected",
            "risk": "Files stored in these buckets are publicly accessible to anyone on the internet. This may include internal documents, backups, or customer data.",
        })

    # Subdomains — informational
    if scan.subdomains:
        findings.append({
            "severity": "info",
            "description": f"{len(scan.subdomains)} subdomain{'s' if len(scan.subdomains) > 1 else ''} detected",
            "risk": "Each subdomain is a separate entry point that may run different software and have its own vulnerabilities. Subdomains are often forgotten and left unpatched.",
        })

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
        "subdomains": {
            "count": len(scan.subdomains),
            "list": scan.subdomains[:20],
        },
        "dns": scan.dns_records,
        "cloud_exposure": scan.exposed_cloud_storage,
        "risk_summary": risk_summary,
        "findings": findings,
    }
