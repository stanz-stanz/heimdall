"""Brief generator: assemble per-site JSON briefs matching the SKILL.md schema."""

from __future__ import annotations

from datetime import date

from .config import (
    GDPR_DATA_HANDLING_PLUGINS,
    GDPR_ECOMMERCE_CMS,
    GDPR_SENSITIVE_CODES,
    GDPR_TRACKING_TECH,
    SENSITIVE_TECH,
)
from .cvr import Company
from .scanner import ScanResult


def _determine_gdpr_sensitivity(
    company: Company, scan: ScanResult,
) -> dict:
    """Determine GDPR sensitivity from industry code AND scan evidence.

    Returns a structured object with the determination and all reasons.
    """
    reasons = []

    # Signal 1: Industry code (pre-existing heuristic)
    if company.industry_code:
        for prefix in sorted(GDPR_SENSITIVE_CODES.keys(), key=len, reverse=True):
            if company.industry_code.startswith(prefix):
                reasons.append(f"Industry: {GDPR_SENSITIVE_CODES[prefix]}")
                break

    # Signal 2: Data-handling plugins (forms, bookings, payments)
    data_plugins = [p for p in scan.detected_plugins
                    if p.lower().replace(" ", "-") in GDPR_DATA_HANDLING_PLUGINS]
    if data_plugins:
        names = ", ".join(p.replace("-", " ").title() for p in data_plugins)
        reasons.append(f"Data-handling plugins: {names}")

    # Signal 3: E-commerce CMS or plugin
    if scan.cms and scan.cms.lower() in GDPR_ECOMMERCE_CMS:
        reasons.append(f"E-commerce platform: {scan.cms}")
    ecom_plugins = [t for t in scan.tech_stack if t.lower().split(":")[0] in GDPR_ECOMMERCE_CMS]
    if ecom_plugins and not any("E-commerce" in r for r in reasons):
        reasons.append(f"E-commerce plugin: {', '.join(ecom_plugins)}")

    # Signal 4: Tracking/analytics (visitor behavior data, requires cookie consent)
    tracking = [t for t in scan.tech_stack
                if any(tr in t.lower() for tr in GDPR_TRACKING_TECH)]
    if tracking:
        reasons.append(f"Visitor tracking: {', '.join(tracking)}")

    return {
        "sensitive": len(reasons) > 0,
        "reasons": reasons,
    }


def generate_brief(
    company: Company,
    scan: ScanResult,
    bucket: str,
    outdated_plugins: list[dict] | None = None,
) -> dict:
    """Generate a per-site brief matching .claude/agents/prospecting/SKILL.md schema."""
    # Determine GDPR sensitivity from evidence
    gdpr = _determine_gdpr_sensitivity(company, scan)

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
    data_plugins = [p for p in scan.detected_plugins if p.lower().replace(" ", "-") in GDPR_DATA_HANDLING_PLUGINS]
    other_plugins = [p for p in scan.detected_plugins if p.lower().replace(" ", "-") not in GDPR_DATA_HANDLING_PLUGINS]

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
    exposed_backend = [t for t in scan.tech_stack if t.lower().split(":")[0].lower() in SENSITIVE_TECH]
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

    # Plugin versions — display name → version
    plugin_versions_display = {}
    for slug, ver in scan.plugin_versions.items():
        display_name = slug.replace("-", " ").title()
        plugin_versions_display[display_name] = ver

    # Theme names
    theme_names = [t.replace("-", " ").title() for t in scan.detected_themes]

    # Theme detection finding
    if scan.detected_themes:
        theme_list = ", ".join(theme_names)
        findings.append({
            "severity": "info",
            "description": f"WordPress theme{'s' if len(scan.detected_themes) > 1 else ''} detected: {theme_list}",
            "risk": "The active theme is visible in the HTML source. Outdated themes are a common source of vulnerabilities, similar to plugins.",
        })

    # Outdated plugin findings (pre-computed in scan_job.py)
    for entry in (outdated_plugins or []):
        if entry.get("outdated"):
            display = entry["slug"].replace("-", " ").title()
            findings.append({
                "severity": "medium",
                "description": f"Outdated plugin: {display} (installed {entry['installed']}, latest {entry['latest']})",
                "risk": f"The installed version of {display} is behind the current release. Outdated plugins may contain known vulnerabilities that are fixed in newer versions.",
            })

    return {
        "domain": company.website_domain,
        "cvr": company.cvr,
        "company_name": company.name,
        "scan_date": date.today().isoformat(),
        "bucket": bucket,
        "gdpr_sensitive": gdpr["sensitive"],
        "gdpr_reasons": gdpr["reasons"],
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
            "plugin_versions": plugin_versions_display,
            "detected_themes": theme_names,
            "headers": scan.headers,
        },
        "tech_stack": scan.tech_stack,
        "plugin_versions": dict(scan.plugin_versions),
        "subdomains": {
            "count": len(scan.subdomains),
            "list": scan.subdomains[:20],
        },
        "dns": scan.dns_records,
        "cloud_exposure": scan.exposed_cloud_storage,
        "findings": findings,
    }
