#!/usr/bin/env python3
"""Deep statistical analysis of Heimdall pipeline scan data.

Reads the prospects CSV and per-domain JSON briefs to produce a comprehensive
breakdown of security posture across ~1,173 Danish SMB websites.

Usage:
    python scripts/analyze_stats.py
"""

from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "data" / "output" / "prospects-list.csv"
BRIEFS_DIR = ROOT / "data" / "output" / "briefs"
INDUSTRY_CODES_PATH = ROOT / "config" / "industry_codes.json"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SEVERITY_ORDER = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}
TODAY = datetime(2026, 4, 5)  # Matches project current date


def _pct(part: int, total: int) -> str:
    """Format a percentage string, safe for zero division."""
    if total == 0:
        return "0.0%"
    return f"{part / total * 100:.1f}%"


def _bar(count: int, total: int, width: int = 30) -> str:
    """Simple ASCII bar."""
    if total == 0:
        return ""
    filled = int(count / total * width)
    return "#" * filled + "." * (width - filled)


def _avg(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _severity_score(findings: list[dict]) -> float:
    """Compute an average severity score for a list of findings (0-4 scale)."""
    scores = [SEVERITY_ORDER.get(f.get("severity", "").lower(), 0) for f in findings]
    return _avg(scores)


def _section(title: str) -> None:
    print(f"\n{'=' * 72}")
    print(f"  {title}")
    print(f"{'=' * 72}")


def _subsection(title: str) -> None:
    print(f"\n  --- {title} ---")


def _normalise_finding(desc: str) -> str:
    """Normalise finding descriptions for grouping.

    Strips version numbers, counts, specific plugin names from common patterns
    so similar findings cluster together.
    """
    # "X WordPress plugins detected" -> "N WordPress plugins detected"
    desc = re.sub(r"^\d+ WordPress plugins? detected$", "N WordPress plugins detected", desc)
    # "WordPress version X publicly disclosed"
    desc = re.sub(r"^WordPress version .+ publicly disclosed$", "WordPress version publicly disclosed", desc)
    # "Backend technology exposed: ..."
    desc = re.sub(r"^Backend technology exposed: .+$", "Backend technology exposed", desc)
    # "WordPress theme(s) detected: ..."
    desc = re.sub(r"^WordPress themes? detected: .+$", "WordPress theme(s) detected", desc)
    # "Outdated plugin: X (installed Y, latest Z)"
    if desc.startswith("Outdated plugin:"):
        match = re.match(r"Outdated plugin: (.+?) \(installed", desc)
        if match:
            return f"Outdated plugin: {match.group(1)}"
        return "Outdated plugin (various)"
    # "Data-handling plugin detected: X"
    desc = re.sub(r"^Data-handling plugin detected: .+$", "Data-handling plugin detected", desc)
    # CVE findings — group by plugin slug
    cve_match = re.search(r"\[([^\]]+)\]", desc)
    if cve_match:
        slug = cve_match.group(1)
        cve_id = re.search(r"(CVE-\d{4}-\d+)", desc)
        if cve_id:
            return f"CVE for [{slug}]: {cve_id.group(1)}"
        return f"Vulnerability in [{slug}]"
    # "N exposed cloud storage bucket(s) detected"
    desc = re.sub(r"^\d+ exposed cloud storage buckets? detected$", "Exposed cloud storage bucket(s)", desc)
    return desc


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_csv() -> list[dict[str, str]]:
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_briefs() -> dict[str, dict[str, Any]]:
    """Load all JSON briefs keyed by domain."""
    briefs: dict[str, dict[str, Any]] = {}
    for path in BRIEFS_DIR.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            domain = data.get("domain", path.stem)
            briefs[domain] = data
        except (json.JSONDecodeError, OSError):
            continue
    return briefs


def load_industry_codes() -> dict[str, str]:
    try:
        return json.loads(INDUSTRY_CODES_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


# ---------------------------------------------------------------------------
# Analysis functions
# ---------------------------------------------------------------------------

def analyze_severity(briefs: dict[str, dict]) -> None:
    _section("1. FINDING SEVERITY BREAKDOWN")

    severity_counts: Counter[str] = Counter()
    total_findings = 0
    sites_with_findings: dict[str, int] = {}  # severity -> count of sites

    severity_per_site: dict[str, Counter] = {}
    for domain, brief in briefs.items():
        findings = brief.get("findings", [])
        site_sev: Counter[str] = Counter()
        for f in findings:
            sev = f.get("severity", "unknown").lower()
            severity_counts[sev] += 1
            site_sev[sev] += 1
            total_findings += 1
        severity_per_site[domain] = site_sev

    n_sites = len(briefs)
    print(f"\n  Total findings across all briefs: {total_findings:,}")
    print(f"  Total sites analysed: {n_sites:,}")
    print(f"  Average findings per site: {total_findings / max(n_sites, 1):.1f}")

    print(f"\n  {'Severity':<12} {'Count':>8} {'% of all':>10} {'Sites with >=1':>16}")
    print(f"  {'-' * 50}")
    for sev in ["critical", "high", "medium", "low", "info"]:
        count = severity_counts.get(sev, 0)
        sites_with = sum(1 for sc in severity_per_site.values() if sc.get(sev, 0) > 0)
        print(f"  {sev.capitalize():<12} {count:>8,} {_pct(count, total_findings):>10} {sites_with:>8} ({_pct(sites_with, n_sites)})")

    unknown = severity_counts.get("unknown", 0)
    if unknown:
        print(f"  {'Unknown':<12} {unknown:>8,}")


def analyze_common_findings(briefs: dict[str, dict]) -> None:
    _section("2. MOST COMMON FINDINGS (Top 20)")

    raw_counts: Counter[str] = Counter()
    normalised_counts: Counter[str] = Counter()

    for brief in briefs.values():
        for f in brief.get("findings", []):
            desc = f.get("description", "")
            raw_counts[desc] += 1
            normalised_counts[_normalise_finding(desc)] += 1

    _subsection("Top 20 finding descriptions (normalised)")
    print(f"\n  {'#':<4} {'Count':>6} {'Description'}")
    print(f"  {'-' * 68}")
    for i, (desc, count) in enumerate(normalised_counts.most_common(20), 1):
        truncated = desc[:58] if len(desc) > 58 else desc
        print(f"  {i:<4} {count:>6}  {truncated}")

    _subsection("Top 20 exact finding descriptions (raw)")
    print(f"\n  {'#':<4} {'Count':>6} {'Description'}")
    print(f"  {'-' * 68}")
    for i, (desc, count) in enumerate(raw_counts.most_common(20), 1):
        truncated = desc[:58] if len(desc) > 58 else desc
        print(f"  {i:<4} {count:>6}  {truncated}")


def analyze_headers(briefs: dict[str, dict]) -> None:
    _section("3. SECURITY HEADER ADOPTION RATES")

    header_keys = [
        ("strict_transport_security", "HSTS (Strict-Transport-Security)"),
        ("content_security_policy", "Content-Security-Policy"),
        ("x_frame_options", "X-Frame-Options"),
        ("x_content_type_options", "X-Content-Type-Options"),
        ("permissions_policy", "Permissions-Policy"),
        ("referrer_policy", "Referrer-Policy"),
    ]

    n_sites = len(briefs)
    header_present: Counter[str] = Counter()
    sites_with_headers = 0

    for brief in briefs.values():
        headers = brief.get("technology", {}).get("headers", {})
        if not headers:
            continue
        sites_with_headers += 1
        for key, _ in header_keys:
            if headers.get(key):
                header_present[key] += 1

    print(f"\n  Sites with header data: {sites_with_headers:,} / {n_sites:,}")
    print(f"\n  {'Header':<38} {'Present':>8} {'Adoption':>10} {'Bar'}")
    print(f"  {'-' * 72}")
    for key, label in header_keys:
        count = header_present.get(key, 0)
        pct = _pct(count, sites_with_headers)
        bar = _bar(count, sites_with_headers, 20)
        print(f"  {label:<38} {count:>8} {pct:>10}  {bar}")

    # How many sites have ALL 4 core headers?
    all_four = 0
    none_four = 0
    for brief in briefs.values():
        headers = brief.get("technology", {}).get("headers", {})
        core = ["strict_transport_security", "content_security_policy",
                "x_frame_options", "x_content_type_options"]
        vals = [headers.get(k, False) for k in core]
        if all(vals):
            all_four += 1
        if not any(vals):
            none_four += 1

    print(f"\n  Sites with ALL 4 core security headers: {all_four} ({_pct(all_four, sites_with_headers)})")
    print(f"  Sites with NONE of the 4 core headers:  {none_four} ({_pct(none_four, sites_with_headers)})")


def analyze_ssl(briefs: dict[str, dict], csv_rows: list[dict]) -> None:
    _section("4. SSL / TLS ANALYSIS")

    n_sites = len(briefs)
    valid_count = 0
    invalid_count = 0
    no_ssl_count = 0
    expiry_30 = 0
    expiry_60 = 0
    expiry_90 = 0
    expired = 0
    issuer_counts: Counter[str] = Counter()
    days_remaining_values: list[int] = []

    for brief in briefs.values():
        ssl = brief.get("technology", {}).get("ssl", {})
        if not ssl or not ssl.get("expiry"):
            no_ssl_count += 1
            continue

        is_valid = ssl.get("valid", False)
        if is_valid:
            valid_count += 1
        else:
            invalid_count += 1

        issuer = ssl.get("issuer", "Unknown")
        if issuer:
            issuer_counts[issuer] += 1

        expiry_str = ssl.get("expiry", "")
        days = ssl.get("days_remaining")
        if days is not None:
            days_remaining_values.append(days)
            if days < 0:
                expired += 1
            if days <= 30:
                expiry_30 += 1
            if days <= 60:
                expiry_60 += 1
            if days <= 90:
                expiry_90 += 1
        elif expiry_str:
            try:
                exp_date = datetime.strptime(expiry_str, "%Y-%m-%d")
                delta = (exp_date - TODAY).days
                days_remaining_values.append(delta)
                if delta < 0:
                    expired += 1
                if delta <= 30:
                    expiry_30 += 1
                if delta <= 60:
                    expiry_60 += 1
                if delta <= 90:
                    expiry_90 += 1
            except ValueError:
                pass

    has_ssl = valid_count + invalid_count
    print(f"\n  Total sites: {n_sites:,}")
    print(f"  Valid SSL:   {valid_count:>6} ({_pct(valid_count, n_sites)})")
    print(f"  Invalid SSL: {invalid_count:>6} ({_pct(invalid_count, n_sites)})")
    print(f"  No SSL data: {no_ssl_count:>6} ({_pct(no_ssl_count, n_sites)})")

    print(f"\n  Already expired:       {expired:>6} ({_pct(expired, has_ssl)})")
    print(f"  Expiring within 30d:   {expiry_30:>6} ({_pct(expiry_30, has_ssl)})")
    print(f"  Expiring within 60d:   {expiry_60:>6} ({_pct(expiry_60, has_ssl)})")
    print(f"  Expiring within 90d:   {expiry_90:>6} ({_pct(expiry_90, has_ssl)})")

    if days_remaining_values:
        print(f"\n  Average days until expiry: {_avg(days_remaining_values):.0f}")
        print(f"  Median days until expiry:  {sorted(days_remaining_values)[len(days_remaining_values) // 2]}")
        print(f"  Min: {min(days_remaining_values)}, Max: {max(days_remaining_values)}")

    _subsection("SSL Certificate Issuers (Top 10)")
    print(f"\n  {'Issuer':<30} {'Count':>6} {'%':>8}")
    print(f"  {'-' * 48}")
    for issuer, count in issuer_counts.most_common(10):
        print(f"  {issuer:<30} {count:>6} {_pct(count, has_ssl):>8}")


def analyze_wordpress(briefs: dict[str, dict]) -> None:
    _section("5. WORDPRESS-SPECIFIC ANALYSIS")

    wp_briefs = {d: b for d, b in briefs.items()
                 if b.get("technology", {}).get("cms", "").lower() == "wordpress"}
    n_wp = len(wp_briefs)
    n_total = len(briefs)

    print(f"\n  WordPress sites: {n_wp} / {n_total} ({_pct(n_wp, n_total)})")

    if n_wp == 0:
        print("  No WordPress sites found.")
        return

    # Plugin stats
    plugin_counts: list[int] = []
    plugin_freq: Counter[str] = Counter()
    outdated_plugins: Counter[str] = Counter()
    sites_with_cves = 0
    cves_per_site: list[int] = []
    all_cve_ids: Counter[str] = Counter()

    for domain, brief in wp_briefs.items():
        tech = brief.get("technology", {})
        plugins = tech.get("detected_plugins", [])
        plugin_counts.append(len(plugins))
        for p in plugins:
            plugin_freq[p] += 1

        # Count outdated and CVEs from findings
        findings = brief.get("findings", [])
        site_cves = 0
        for f in findings:
            desc = f.get("description", "")
            if desc.startswith("Outdated plugin:"):
                match = re.match(r"Outdated plugin: (.+?) \(", desc)
                if match:
                    outdated_plugins[match.group(1)] += 1
            cve_match = re.search(r"(CVE-\d{4}-\d+)", desc)
            if cve_match:
                site_cves += 1
                all_cve_ids[cve_match.group(1)] += 1

        cves_per_site.append(site_cves)
        if site_cves > 0:
            sites_with_cves += 1

    _subsection("Plugin Statistics")
    print(f"  Average plugins per WP site: {_avg(plugin_counts):.1f}")
    print(f"  Median plugins: {sorted(plugin_counts)[len(plugin_counts) // 2]}")
    print(f"  Max plugins on a single site: {max(plugin_counts)}")
    print(f"  Sites with 0 detected plugins: {sum(1 for c in plugin_counts if c == 0)} ({_pct(sum(1 for c in plugin_counts if c == 0), n_wp)})")

    _subsection("Most Common Plugins (Top 20)")
    print(f"\n  {'#':<4} {'Plugin':<40} {'Count':>6} {'% of WP sites':>14}")
    print(f"  {'-' * 66}")
    for i, (plugin, count) in enumerate(plugin_freq.most_common(20), 1):
        print(f"  {i:<4} {plugin:<40} {count:>6} {_pct(count, n_wp):>14}")

    _subsection("Most Commonly Outdated Plugins (Top 15)")
    print(f"\n  {'#':<4} {'Plugin':<40} {'Sites outdated':>14}")
    print(f"  {'-' * 60}")
    for i, (plugin, count) in enumerate(outdated_plugins.most_common(15), 1):
        print(f"  {i:<4} {plugin:<40} {count:>14}")

    _subsection("CVE Exposure")
    print(f"  WP sites with known CVEs:    {sites_with_cves} ({_pct(sites_with_cves, n_wp)})")
    print(f"  WP sites without known CVEs: {n_wp - sites_with_cves} ({_pct(n_wp - sites_with_cves, n_wp)})")
    print(f"  Average CVEs per WP site:    {_avg(cves_per_site):.1f}")
    if cves_per_site:
        print(f"  Max CVEs on a single WP site: {max(cves_per_site)}")

    _subsection("Most Frequent CVEs (Top 15)")
    print(f"\n  {'CVE ID':<22} {'Sites affected':>14}")
    print(f"  {'-' * 40}")
    for cve_id, count in all_cve_ids.most_common(15):
        print(f"  {cve_id:<22} {count:>14}")


def analyze_gdpr(briefs: dict[str, dict]) -> None:
    _section("6. GDPR EXPOSURE ANALYSIS")

    n_sites = len(briefs)
    gdpr_sensitive = sum(1 for b in briefs.values() if b.get("gdpr_sensitive"))
    gdpr_not = n_sites - gdpr_sensitive

    print(f"\n  GDPR-sensitive sites: {gdpr_sensitive} ({_pct(gdpr_sensitive, n_sites)})")
    print(f"  Non-GDPR-sensitive:  {gdpr_not} ({_pct(gdpr_not, n_sites)})")

    # Analyse gdpr_reasons
    reason_counts: Counter[str] = Counter()
    for brief in briefs.values():
        for reason in brief.get("gdpr_reasons", []):
            # Normalise: extract the core tech name
            reason_counts[reason] += 1

    # Also count data-handling tech from tech_stack and detected_plugins
    data_tech: Counter[str] = Counter()
    data_tech_patterns = {
        "WooCommerce": re.compile(r"woocommerce", re.I),
        "Contact Form 7": re.compile(r"contact.form.7", re.I),
        "Google Analytics": re.compile(r"google.analytics|google.tag.manager|gtag", re.I),
        "Facebook Pixel": re.compile(r"facebook.pixel|meta.pixel|fbevents", re.I),
        "Gravity Forms": re.compile(r"gravity.forms", re.I),
        "WPForms": re.compile(r"wpforms", re.I),
        "Mailchimp": re.compile(r"mailchimp", re.I),
        "Hotjar": re.compile(r"hotjar", re.I),
        "Matomo": re.compile(r"matomo|piwik", re.I),
        "Cookiebot": re.compile(r"cookiebot", re.I),
        "Cookie Notice": re.compile(r"cookie.notice|cookie.consent|cookie.law", re.I),
        "Yoast SEO": re.compile(r"yoast|wordpress.seo", re.I),
        "Jetpack": re.compile(r"jetpack", re.I),
        "Easy Digital Downloads": re.compile(r"easy.digital.downloads|edd", re.I),
    }

    for brief in briefs.values():
        tech_stack = brief.get("tech_stack", [])
        plugins = brief.get("technology", {}).get("detected_plugins", [])
        all_tech = " ".join(tech_stack + plugins)
        for tech_name, pattern in data_tech_patterns.items():
            if pattern.search(all_tech):
                data_tech[tech_name] += 1

    _subsection("GDPR Reasons (from pipeline, Top 20)")
    print(f"\n  {'Reason':<58} {'Count':>6}")
    print(f"  {'-' * 66}")
    for reason, count in reason_counts.most_common(20):
        truncated = reason[:56] if len(reason) > 56 else reason
        print(f"  {truncated:<58} {count:>6}")

    _subsection("Data-Handling Technology Prevalence")
    print(f"\n  {'Technology':<30} {'Sites':>6} {'% of all':>10}")
    print(f"  {'-' * 50}")
    for tech, count in data_tech.most_common():
        print(f"  {tech:<30} {count:>6} {_pct(count, n_sites):>10}")


def analyze_industry(briefs: dict[str, dict], csv_rows: list[dict], industry_codes: dict[str, str]) -> None:
    _section("7. INDUSTRY BREAKDOWN")

    # Build domain -> industry_code from CSV
    domain_industry: dict[str, str] = {}
    for row in csv_rows:
        domain = row.get("website", "")
        code = row.get("industry_code", "").strip()
        if domain and code:
            domain_industry[domain] = code

    # Group by industry
    industry_findings: dict[str, list[int]] = defaultdict(list)
    industry_severity: dict[str, list[float]] = defaultdict(list)
    industry_count: Counter[str] = Counter()

    for domain, brief in briefs.items():
        code = domain_industry.get(domain, "")
        if not code:
            code = "Unknown"
        industry_name = industry_codes.get(code, code)
        industry_count[industry_name] += 1
        findings = brief.get("findings", [])
        industry_findings[industry_name].append(len(findings))
        industry_severity[industry_name].append(_severity_score(findings))

    # Show top 20 industries by count
    _subsection("Top 20 Industries by Site Count")
    print(f"\n  {'Industry':<48} {'Sites':>6} {'Avg Findings':>13} {'Avg Severity':>13}")
    print(f"  {'-' * 84}")
    for industry, count in industry_count.most_common(20):
        avg_f = _avg(industry_findings[industry])
        avg_s = _avg(industry_severity[industry])
        truncated = industry[:46] if len(industry) > 46 else industry
        print(f"  {truncated:<48} {count:>6} {avg_f:>13.1f} {avg_s:>13.2f}")

    # Worst security posture (min 5 sites)
    _subsection("Worst Security Posture by Industry (min 5 sites, by avg severity score)")
    eligible = {ind: _avg(industry_severity[ind])
                for ind, cnt in industry_count.items() if cnt >= 5}
    sorted_worst = sorted(eligible.items(), key=lambda x: x[1], reverse=True)
    print(f"\n  {'Industry':<48} {'Sites':>6} {'Avg Severity':>13} {'Avg Findings':>13}")
    print(f"  {'-' * 84}")
    for industry, avg_s in sorted_worst[:15]:
        avg_f = _avg(industry_findings[industry])
        count = industry_count[industry]
        truncated = industry[:46] if len(industry) > 46 else industry
        print(f"  {truncated:<48} {count:>6} {avg_s:>13.2f} {avg_f:>13.1f}")


def analyze_contactable(briefs: dict[str, dict], csv_rows: list[dict]) -> None:
    _section("8. CONTACTABLE vs NON-CONTACTABLE")

    domain_contactable: dict[str, bool] = {}
    for row in csv_rows:
        domain = row.get("website", "")
        val = row.get("contactable", "").strip().lower()
        if domain:
            domain_contactable[domain] = val == "true"

    groups: dict[str, list[dict]] = {"Contactable": [], "Non-contactable": [], "Unknown": []}
    for domain, brief in briefs.items():
        if domain not in domain_contactable:
            groups["Unknown"].append(brief)
        elif domain_contactable[domain]:
            groups["Contactable"].append(brief)
        else:
            groups["Non-contactable"].append(brief)

    print(f"\n  {'Group':<20} {'Sites':>6} {'Avg Findings':>13} {'Avg Severity':>13} {'% GDPR-sensitive':>18}")
    print(f"  {'-' * 76}")
    for group_name, group_briefs in groups.items():
        if not group_briefs:
            continue
        n = len(group_briefs)
        avg_f = _avg([len(b.get("findings", [])) for b in group_briefs])
        avg_s = _avg([_severity_score(b.get("findings", [])) for b in group_briefs])
        gdpr_rate = _pct(sum(1 for b in group_briefs if b.get("gdpr_sensitive")), n)
        print(f"  {group_name:<20} {n:>6} {avg_f:>13.1f} {avg_s:>13.2f} {gdpr_rate:>18}")


def analyze_hosting(briefs: dict[str, dict]) -> None:
    _section("9. HOSTING PROVIDER DISTRIBUTION")

    hosting_counts: Counter[str] = Counter()
    hosting_findings: dict[str, list[int]] = defaultdict(list)
    hosting_severity: dict[str, list[float]] = defaultdict(list)

    for brief in briefs.values():
        hosting = brief.get("technology", {}).get("hosting", "Unknown") or "Unknown"
        hosting_counts[hosting] += 1
        findings = brief.get("findings", [])
        hosting_findings[hosting].append(len(findings))
        hosting_severity[hosting].append(_severity_score(findings))

    n_sites = len(briefs)
    print(f"\n  {'Provider':<25} {'Sites':>6} {'% share':>8} {'Avg Findings':>13} {'Avg Severity':>13}")
    print(f"  {'-' * 70}")
    for provider, count in hosting_counts.most_common(20):
        avg_f = _avg(hosting_findings[provider])
        avg_s = _avg(hosting_severity[provider])
        print(f"  {provider:<25} {count:>6} {_pct(count, n_sites):>8} {avg_f:>13.1f} {avg_s:>13.2f}")


def analyze_correlations(briefs: dict[str, dict], csv_rows: list[dict]) -> None:
    _section("10. CROSS-CORRELATIONS")

    # CMS type vs avg findings
    _subsection("CMS Type vs Average Findings")
    cms_findings: dict[str, list[int]] = defaultdict(list)
    cms_severity: dict[str, list[float]] = defaultdict(list)

    for brief in briefs.values():
        cms = brief.get("technology", {}).get("cms", "") or "None/Unknown"
        findings = brief.get("findings", [])
        cms_findings[cms].append(len(findings))
        cms_severity[cms].append(_severity_score(findings))

    print(f"\n  {'CMS':<25} {'Sites':>6} {'Avg Findings':>13} {'Avg Severity':>13}")
    print(f"  {'-' * 60}")
    for cms in sorted(cms_findings.keys(), key=lambda c: len(cms_findings[c]), reverse=True):
        n = len(cms_findings[cms])
        avg_f = _avg(cms_findings[cms])
        avg_s = _avg(cms_severity[cms])
        print(f"  {cms:<25} {n:>6} {avg_f:>13.1f} {avg_s:>13.2f}")

    # GDPR-sensitive vs average findings
    _subsection("GDPR-Sensitive vs Average Findings")
    gdpr_groups: dict[str, list[dict]] = {"GDPR-sensitive": [], "Not GDPR-sensitive": []}
    for brief in briefs.values():
        key = "GDPR-sensitive" if brief.get("gdpr_sensitive") else "Not GDPR-sensitive"
        gdpr_groups[key].append(brief)

    print(f"\n  {'Group':<25} {'Sites':>6} {'Avg Findings':>13} {'Avg Severity':>13}")
    print(f"  {'-' * 60}")
    for group_name, group_briefs in gdpr_groups.items():
        n = len(group_briefs)
        avg_f = _avg([len(b.get("findings", [])) for b in group_briefs])
        avg_s = _avg([_severity_score(b.get("findings", [])) for b in group_briefs])
        print(f"  {group_name:<25} {n:>6} {avg_f:>13.1f} {avg_s:>13.2f}")

    # Industry vs GDPR sensitivity rate (top 15 industries by count, min 5 sites)
    _subsection("Industry vs GDPR Sensitivity Rate (min 5 sites)")
    domain_industry: dict[str, str] = {}
    industry_codes = load_industry_codes()
    for row in csv_rows:
        domain = row.get("website", "")
        code = row.get("industry_code", "").strip()
        if domain and code:
            domain_industry[domain] = industry_codes.get(code, code)

    industry_gdpr: dict[str, tuple[int, int]] = defaultdict(lambda: (0, 0))  # (total, gdpr_count)
    industry_totals: Counter[str] = Counter()
    industry_gdpr_counts: Counter[str] = Counter()

    for domain, brief in briefs.items():
        ind = domain_industry.get(domain, "Unknown")
        industry_totals[ind] += 1
        if brief.get("gdpr_sensitive"):
            industry_gdpr_counts[ind] += 1

    eligible = {ind: cnt for ind, cnt in industry_totals.items() if cnt >= 5}
    sorted_by_gdpr = sorted(eligible.keys(),
                            key=lambda i: industry_gdpr_counts[i] / industry_totals[i],
                            reverse=True)

    print(f"\n  {'Industry':<48} {'Sites':>6} {'GDPR':>6} {'Rate':>8}")
    print(f"  {'-' * 72}")
    for ind in sorted_by_gdpr[:15]:
        total = industry_totals[ind]
        gdpr = industry_gdpr_counts[ind]
        truncated = ind[:46] if len(ind) > 46 else ind
        print(f"  {truncated:<48} {total:>6} {gdpr:>6} {_pct(gdpr, total):>8}")


def analyze_provenance(briefs: dict[str, dict]) -> None:
    """Split all key metrics by confirmed vs unconfirmed (twin-derived) provenance."""
    _section("11. PROVENANCE SPLIT — Confirmed vs Potential (twin-inferred)")

    n_sites = len(briefs)

    # Global counters
    confirmed_sev: Counter[str] = Counter()
    unconfirmed_sev: Counter[str] = Counter()
    confirmed_descs: Counter[str] = Counter()
    unconfirmed_descs: Counter[str] = Counter()

    # Per-site tracking
    sites_confirmed_crit_high = 0
    sites_unconfirmed_crit_high = 0
    sites_any_confirmed = 0
    confirmed_per_site: list[int] = []
    unconfirmed_per_site: list[int] = []

    # WordPress-specific
    wp_confirmed_cves: Counter[str] = Counter()
    wp_unconfirmed_cves: Counter[str] = Counter()
    wp_sites_confirmed_cve = 0
    wp_sites_unconfirmed_only_cve = 0
    wp_count = 0

    for domain, brief in briefs.items():
        findings = brief.get("findings", [])
        cms = brief.get("technology", {}).get("cms", "").lower()
        is_wp = "wordpress" in cms

        site_conf = 0
        site_unconf = 0
        has_confirmed_crit_high = False
        has_unconfirmed_crit_high = False
        has_confirmed_cve = False
        has_unconfirmed_cve = False

        if is_wp:
            wp_count += 1

        for f in findings:
            prov = f.get("provenance", "confirmed")
            sev = (f.get("severity") or "info").lower()
            desc = f.get("description", "")
            cve_match = re.search(r"(CVE-\d{4}-\d+)", desc)

            if prov == "confirmed":
                confirmed_sev[sev] += 1
                confirmed_descs[_normalise_finding(desc)] += 1
                site_conf += 1
                if sev in ("critical", "high"):
                    has_confirmed_crit_high = True
                if cve_match and is_wp:
                    wp_confirmed_cves[cve_match.group(1)] += 1
                    has_confirmed_cve = True
            else:
                unconfirmed_sev[sev] += 1
                unconfirmed_descs[_normalise_finding(desc)] += 1
                site_unconf += 1
                if sev in ("critical", "high"):
                    has_unconfirmed_crit_high = True
                if cve_match and is_wp:
                    wp_unconfirmed_cves[cve_match.group(1)] += 1
                    has_unconfirmed_cve = True

        confirmed_per_site.append(site_conf)
        unconfirmed_per_site.append(site_unconf)

        if has_confirmed_crit_high:
            sites_confirmed_crit_high += 1
        if has_unconfirmed_crit_high:
            sites_unconfirmed_crit_high += 1
        if site_conf > 0:
            sites_any_confirmed += 1
        if is_wp:
            if has_confirmed_cve:
                wp_sites_confirmed_cve += 1
            elif has_unconfirmed_cve:
                wp_sites_unconfirmed_only_cve += 1

    total_confirmed = sum(confirmed_sev.values())
    total_unconfirmed = sum(unconfirmed_sev.values())
    total_all = total_confirmed + total_unconfirmed

    # --- Overview ---
    _subsection("Overall Split")
    print(f"  Confirmed findings:   {total_confirmed:>6,} ({_pct(total_confirmed, total_all)})")
    print(f"  Unconfirmed (twin):   {total_unconfirmed:>6,} ({_pct(total_unconfirmed, total_all)})")
    print(f"  Total:                {total_all:>6,}")
    print(f"\n  Avg confirmed per site:   {_avg([float(c) for c in confirmed_per_site]):.1f}")
    print(f"  Avg unconfirmed per site: {_avg([float(c) for c in unconfirmed_per_site]):.1f}")

    # --- Severity split ---
    _subsection("Severity by Provenance")
    print(f"\n  {'Severity':<12} {'Confirmed':>10} {'Unconfirmed':>12} {'Total':>8}")
    print(f"  {'-' * 46}")
    for sev in ["critical", "high", "medium", "low", "info"]:
        c = confirmed_sev.get(sev, 0)
        u = unconfirmed_sev.get(sev, 0)
        print(f"  {sev.capitalize():<12} {c:>10,} {u:>12,} {c + u:>8,}")

    # --- Critical/High site exposure ---
    _subsection("Sites with Critical or High Findings")
    both = sum(1 for i in range(len(confirmed_per_site))
               for domain, brief in [(list(briefs.keys())[i], list(briefs.values())[i])]
               if any(f.get("provenance", "confirmed") == "confirmed"
                      and (f.get("severity") or "").lower() in ("critical", "high")
                      for f in brief.get("findings", []))
               and any(f.get("provenance") == "twin-derived"
                       and (f.get("severity") or "").lower() in ("critical", "high")
                       for f in brief.get("findings", [])))
    conf_only = sites_confirmed_crit_high - both
    unconf_only = sites_unconfirmed_crit_high - both

    print(f"  Confirmed Critical/High only:     {conf_only:>4} sites ({_pct(conf_only, n_sites)})")
    print(f"  Unconfirmed Critical/High only:    {unconf_only:>4} sites ({_pct(unconf_only, n_sites)})")
    print(f"  Both confirmed + unconfirmed:      {both:>4} sites ({_pct(both, n_sites)})")
    print(f"  Any Critical/High (either):        {sites_confirmed_crit_high + unconf_only:>4} sites ({_pct(sites_confirmed_crit_high + unconf_only, n_sites)})")

    # --- Top confirmed findings ---
    _subsection("Top 15 CONFIRMED Findings")
    print(f"\n  {'#':<4} {'Count':>6} {'Description'}")
    print(f"  {'-' * 68}")
    for i, (desc, count) in enumerate(confirmed_descs.most_common(15), 1):
        truncated = desc[:58] if len(desc) > 58 else desc
        print(f"  {i:<4} {count:>6}  {truncated}")

    # --- Top unconfirmed findings ---
    _subsection("Top 15 UNCONFIRMED (twin-derived) Findings")
    print(f"\n  {'#':<4} {'Count':>6} {'Description'}")
    print(f"  {'-' * 68}")
    for i, (desc, count) in enumerate(unconfirmed_descs.most_common(15), 1):
        truncated = desc[:58] if len(desc) > 58 else desc
        print(f"  {i:<4} {count:>6}  {truncated}")

    # --- WordPress CVE split ---
    if wp_count > 0:
        _subsection(f"WordPress CVE Split ({wp_count} WP sites)")
        print(f"  WP sites with CONFIRMED CVEs:        {wp_sites_confirmed_cve:>4} ({_pct(wp_sites_confirmed_cve, wp_count)})")
        print(f"  WP sites with unconfirmed CVEs ONLY: {wp_sites_unconfirmed_only_cve:>4} ({_pct(wp_sites_unconfirmed_only_cve, wp_count)})")
        print(f"  WP sites with NO CVEs:               {wp_count - wp_sites_confirmed_cve - wp_sites_unconfirmed_only_cve:>4} ({_pct(wp_count - wp_sites_confirmed_cve - wp_sites_unconfirmed_only_cve, wp_count)})")
        print(f"\n  Unique confirmed CVEs:   {len(wp_confirmed_cves)}")
        print(f"  Unique unconfirmed CVEs: {len(wp_unconfirmed_cves)}")

    # --- Corrected headline stats ---
    _subsection("CORRECTED HEADLINE STATS (confirmed only)")
    print(f"""
  When citing externally, use CONFIRMED numbers:

  * {_pct(sites_confirmed_crit_high, n_sites)} of sites have a CONFIRMED Critical or High vulnerability
    ({sites_confirmed_crit_high} of {n_sites:,} sites)

  * The average site has {_avg([float(c) for c in confirmed_per_site]):.1f} confirmed findings
    (+ {_avg([float(c) for c in unconfirmed_per_site]):.1f} potential/unconfirmed per site)

  * {_pct(wp_sites_confirmed_cve, wp_count)} of WordPress sites have confirmed CVE matches
    ({wp_sites_confirmed_cve} of {wp_count} WP sites)

  NOTE: Unconfirmed findings are version-inferred from the WPVulnerability
  API and digital twin analysis. They indicate the installed version falls
  within a known-affected range, but the vulnerability has not been
  directly confirmed on the target. Use "potential" language externally.""")


def analyze_headlines(briefs: dict[str, dict]) -> None:
    _section("12. HEADLINE STATISTICS (Marketing-Ready)")

    n_sites = len(briefs)

    # Sites with at least one Critical or High
    sites_crit_high = 0
    sites_any_finding = 0
    total_findings = 0
    sites_with_cve = 0
    sites_missing_all_headers = 0
    sites_missing_csp = 0
    sites_missing_hsts = 0
    sites_outdated_plugin = 0
    sites_wp_version_exposed = 0
    sites_cloud_exposure = 0
    sites_backend_exposed = 0

    all_finding_counts: list[int] = []

    for brief in briefs.values():
        findings = brief.get("findings", [])
        all_finding_counts.append(len(findings))
        if findings:
            sites_any_finding += 1
        total_findings += len(findings)

        severities = {f.get("severity", "").lower() for f in findings}
        if "critical" in severities or "high" in severities:
            sites_crit_high += 1

        has_cve = any("CVE-" in f.get("description", "") for f in findings)
        if has_cve:
            sites_with_cve += 1

        has_outdated = any(f.get("description", "").startswith("Outdated plugin:") for f in findings)
        if has_outdated:
            sites_outdated_plugin += 1

        has_wp_version = any("WordPress version" in f.get("description", "") and "disclosed" in f.get("description", "") for f in findings)
        if has_wp_version:
            sites_wp_version_exposed += 1

        has_cloud = any("cloud storage" in f.get("description", "").lower() for f in findings)
        if has_cloud:
            sites_cloud_exposure += 1

        has_backend = any(f.get("description", "").startswith("Backend technology exposed") for f in findings)
        if has_backend:
            sites_backend_exposed += 1

        headers = brief.get("technology", {}).get("headers", {})
        core_headers = ["strict_transport_security", "content_security_policy",
                        "x_frame_options", "x_content_type_options"]
        vals = [headers.get(k, False) for k in core_headers]
        if not any(vals):
            sites_missing_all_headers += 1
        if not headers.get("content_security_policy"):
            sites_missing_csp += 1
        if not headers.get("strict_transport_security"):
            sites_missing_hsts += 1

    avg_findings = _avg([float(c) for c in all_finding_counts])

    print(f"""
  HEADLINE STATS — Based on {n_sites:,} Danish SMB websites scanned
  {'=' * 64}

  * {_pct(sites_crit_high, n_sites)} of Danish SMBs have at least one Critical or High vulnerability
    ({sites_crit_high:,} of {n_sites:,} sites)

  * The average SMB website has {avg_findings:.1f} known security issues
    (Total: {total_findings:,} findings across {n_sites:,} sites)

  * Only {_pct(n_sites - sites_missing_csp, n_sites)} of sites use Content Security Policy
    ({sites_missing_csp:,} sites missing CSP)

  * Only {_pct(n_sites - sites_missing_hsts, n_sites)} of sites enforce HTTPS via HSTS
    ({sites_missing_hsts:,} sites missing HSTS)

  * {_pct(sites_missing_all_headers, n_sites)} of sites have ZERO security headers
    ({sites_missing_all_headers:,} of {n_sites:,})

  * {_pct(sites_with_cve, n_sites)} of sites have components with known CVEs
    ({sites_with_cve:,} sites)

  * {_pct(sites_outdated_plugin, n_sites)} of WordPress sites run outdated plugins
    ({sites_outdated_plugin:,} sites)

  * {_pct(sites_wp_version_exposed, n_sites)} of WordPress sites publicly disclose their version number
    ({sites_wp_version_exposed:,} sites)

  * {_pct(sites_cloud_exposure, n_sites)} of sites have exposed cloud storage buckets
    ({sites_cloud_exposure:,} sites)

  * {_pct(sites_backend_exposed, n_sites)} of sites expose backend technology details
    ({sites_backend_exposed:,} sites)

  * {_pct(sites_any_finding, n_sites)} of all scanned sites have at least one finding
    ({sites_any_finding:,} of {n_sites:,})
""")


def analyze_bucket_distribution(csv_rows: list[dict]) -> None:
    _section("BONUS: BUCKET DISTRIBUTION")

    bucket_counts: Counter[str] = Counter()
    for row in csv_rows:
        bucket = row.get("bucket", "?").strip()
        bucket_counts[bucket] += 1

    n = len(csv_rows)
    print(f"\n  Total rows in CSV: {n}")
    print(f"\n  {'Bucket':<10} {'Count':>6} {'%':>8} {'Bar'}")
    print(f"  {'-' * 50}")
    for bucket in ["A", "B", "C", "D", "E"]:
        count = bucket_counts.get(bucket, 0)
        print(f"  {bucket:<10} {count:>6} {_pct(count, n):>8}  {_bar(count, n, 20)}")
    others = sum(c for b, c in bucket_counts.items() if b not in "ABCDE")
    if others:
        print(f"  {'Other':<10} {others:>6} {_pct(others, n):>8}")


def analyze_cms_distribution(briefs: dict[str, dict]) -> None:
    _section("BONUS: CMS DISTRIBUTION")

    cms_counts: Counter[str] = Counter()
    for brief in briefs.values():
        cms = brief.get("technology", {}).get("cms", "") or "None/Unknown"
        cms_counts[cms] += 1

    n_sites = len(briefs)
    print(f"\n  {'CMS':<25} {'Sites':>6} {'%':>8}")
    print(f"  {'-' * 42}")
    for cms, count in cms_counts.most_common():
        print(f"  {cms:<25} {count:>6} {_pct(count, n_sites):>8}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 72)
    print("  HEIMDALL PIPELINE — DEEP STATISTICAL ANALYSIS")
    print(f"  Analysis date: {TODAY.strftime('%Y-%m-%d')}")
    print("=" * 72)

    print("\n  Loading data...")
    csv_rows = load_csv()
    briefs = load_briefs()
    industry_codes = load_industry_codes()
    print(f"  CSV rows:    {len(csv_rows):,}")
    print(f"  JSON briefs: {len(briefs):,}")
    print(f"  Industry codes loaded: {len(industry_codes):,}")

    analyze_severity(briefs)
    analyze_common_findings(briefs)
    analyze_headers(briefs)
    analyze_ssl(briefs, csv_rows)
    analyze_wordpress(briefs)
    analyze_gdpr(briefs)
    analyze_industry(briefs, csv_rows, industry_codes)
    analyze_contactable(briefs, csv_rows)
    analyze_hosting(briefs)
    analyze_correlations(briefs, csv_rows)
    analyze_provenance(briefs)
    analyze_headlines(briefs)
    analyze_bucket_distribution(csv_rows)
    analyze_cms_distribution(briefs)

    print("\n" + "=" * 72)
    print("  Analysis complete.")
    print("=" * 72)


if __name__ == "__main__":
    main()
