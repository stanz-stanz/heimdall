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

    # CMS version disclosure
    if scan.cms:
        # Extract version from tech_stack if available (e.g., "WordPress:6.9.4")
        cms_version = ""
        for tech in scan.tech_stack:
            if scan.cms.lower() in tech.lower() and ":" in tech:
                cms_version = tech.split(":", 1)[1]
                break

        if cms_version:
            findings.append({
                "severity": "medium",
                "description": f"{scan.cms} version {cms_version} publicly disclosed",
                "risk": f"The exact {scan.cms} version is visible to anyone viewing the page source. This allows attackers to look up known vulnerabilities specific to this version and target them directly.",
            })
        elif scan.cms.lower() == "wordpress":
            findings.append({
                "severity": "low",
                "description": f"{scan.cms} detected (version not determined)",
                "risk": f"The site runs {scan.cms}. While the exact version is not exposed, CMS-specific attack patterns can still be attempted.",
            })

    # Plugins — especially those handling user data (forms, booking, e-commerce)
    _data_handling_plugins = {
        "gravityforms", "gravity-forms", "contact-form-7", "cf7", "wpforms",
        "woocommerce", "booketbord", "booket-bord", "easy-digital-downloads",
        "formidable", "ninja-forms", "caldera-forms", "everest-forms",
    }
    data_plugins = [p for p in scan.detected_plugins if p.lower().replace(" ", "-") in _data_handling_plugins]
    other_plugins = [p for p in scan.detected_plugins if p.lower().replace(" ", "-") not in _data_handling_plugins]

    if data_plugins:
        plugin_list = ", ".join(p.replace("-", " ").title() for p in data_plugins)
        findings.append({
            "severity": "medium",
            "description": f"Data-handling plugin{'s' if len(data_plugins) > 1 else ''} detected: {plugin_list}",
            "risk": "These plugins collect or process user data (form submissions, bookings, payments). If the site or plugin has a vulnerability, this data could be exposed. Keeping these plugins updated is critical for GDPR compliance.",
        })

    if len(other_plugins) > 0:
        findings.append({
            "severity": "info",
            "description": f"{len(scan.detected_plugins)} WordPress plugin{'s' if len(scan.detected_plugins) > 1 else ''} detected",
            "risk": "Each plugin is additional code from a third-party developer. Outdated or abandoned plugins are a common entry point for attackers. Plugins should be reviewed and kept updated.",
        })

    # Server technology exposure
    _sensitive_tech = {"php", "mysql", "mariadb", "postgresql", "asp.net", "java", "node.js"}
    exposed_backend = [t for t in scan.tech_stack if t.lower().split(":")[0].lower() in _sensitive_tech]
    if exposed_backend:
        tech_list = ", ".join(exposed_backend)
        findings.append({
            "severity": "low",
            "description": f"Backend technology exposed: {tech_list}",
            "risk": "The server advertises which backend technologies it runs. This gives attackers information about which exploits may be applicable. It does not mean the site is vulnerable, but it reduces the effort needed to find an attack vector.",
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
        "findings": findings,
    }
