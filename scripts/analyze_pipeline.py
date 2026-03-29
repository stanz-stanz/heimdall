#!/usr/bin/env python3
"""Analyze pipeline output — prospect list + briefs.

Usage:
    python3 scripts/analyze_pipeline.py [--briefs-dir DIR] [--csv PATH] [--deep]

Default: summary analysis (buckets, CMS, findings, top prospects).
--deep: full deep analysis (contactable breakdown, industries, agencies,
        timing, per-domain scoring, outreach prioritization).
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path


def load_briefs(briefs_dir: Path) -> list[dict]:
    briefs = []
    for f in sorted(briefs_dir.glob("*.json")):
        try:
            with open(f) as fh:
                briefs.append(json.load(fh))
        except (json.JSONDecodeError, OSError):
            continue
    return briefs


def load_csv(csv_path: Path) -> list[dict]:
    if not csv_path.is_file():
        return []
    with open(csv_path) as f:
        return list(csv.DictReader(f))


def load_results(results_dir: Path) -> dict:
    """Load timing data from worker results. Returns {domain: result_dict}."""
    results = {}
    if not results_dir.is_dir():
        return results
    for client_dir in results_dir.iterdir():
        if not client_dir.is_dir():
            continue
        for domain_dir in client_dir.iterdir():
            if not domain_dir.is_dir():
                continue
            json_files = sorted(domain_dir.glob("*.json"), reverse=True)
            if json_files:
                try:
                    with open(json_files[0]) as f:
                        results[domain_dir.name] = json.load(f)
                except (json.JSONDecodeError, OSError):
                    continue
    return results


# ---------------------------------------------------------------------------
# Summary analysis (default)
# ---------------------------------------------------------------------------


def analyze_summary(briefs: list[dict], csv_rows: list[dict]) -> None:
    total = len(briefs)
    if total == 0:
        print("No briefs found.")
        return

    print(f"{'=' * 70}")
    print(f"  HEIMDALL PIPELINE ANALYSIS — {total} domains")
    print(f"{'=' * 70}")

    # Buckets
    buckets = Counter(b.get("bucket", "?") for b in briefs)
    print(f"\n  BUCKETS")
    for bucket in ["A", "B", "E", "C", "D"]:
        count = buckets.get(bucket, 0)
        bar = "#" * (count // 2)
        print(f"    {bucket}: {count:3d}  {bar}")

    # CMS
    cms_counts = Counter(b.get("technology", {}).get("cms", "") or "none" for b in briefs)
    print(f"\n  CMS DETECTION")
    for cms, count in cms_counts.most_common():
        print(f"    {count:3d}  {cms}")

    # Hosting
    hosting = Counter(b.get("technology", {}).get("hosting", "Unknown") for b in briefs)
    print(f"\n  HOSTING (top 10)")
    for h, count in hosting.most_common(10):
        print(f"    {count:3d}  {h}")

    # GDPR
    gdpr_count = sum(1 for b in briefs if b.get("gdpr_sensitive"))
    gdpr_reasons = Counter()
    for b in briefs:
        for r in b.get("gdpr_reasons", []):
            gdpr_reasons[r.split(":")[0].strip()] += 1
    print(f"\n  GDPR SENSITIVE: {gdpr_count}/{total} ({gdpr_count * 100 // total}%)")
    for reason, count in gdpr_reasons.most_common():
        print(f"    {count:3d}  {reason}")

    # SSL
    ssl_valid = sum(1 for b in briefs if b.get("technology", {}).get("ssl", {}).get("valid"))
    no_ssl = sum(1 for b in briefs if b.get("technology", {}).get("ssl", {}).get("days_remaining", -1) == -1)
    expiring_soon = []
    for b in briefs:
        days = b.get("technology", {}).get("ssl", {}).get("days_remaining", 999)
        if 0 < days < 30:
            expiring_soon.append((b["domain"], days, b.get("technology", {}).get("ssl", {}).get("expiry", "")))

    print(f"\n  SSL STATUS")
    print(f"    Valid: {ssl_valid}/{total}")
    print(f"    No certificate: {no_ssl}")
    print(f"    Expiring <30 days: {len(expiring_soon)}")
    for domain, days, expiry in sorted(expiring_soon, key=lambda x: x[1]):
        print(f"      {days:2d} days  {domain}  ({expiry})")

    # Findings
    finding_dist = Counter()
    total_findings = 0
    finding_types = Counter()
    for b in briefs:
        findings = b.get("findings", [])
        n = len(findings)
        finding_dist[n] += 1
        total_findings += n
        for f in findings:
            finding_types[f.get("description", "")] += 1

    print(f"\n  FINDINGS: {total_findings} total, {total_findings / total:.1f} avg per domain")
    print(f"    Distribution:")
    for count in sorted(finding_dist.keys()):
        bar = "#" * finding_dist[count]
        print(f"      {count} findings: {finding_dist[count]:3d}  {bar}")

    print(f"\n    Top finding types:")
    for desc, count in finding_types.most_common(10):
        print(f"      {count:3d}  {desc}")

    # Plugins
    plugin_counts = Counter()
    for b in briefs:
        for p in b.get("technology", {}).get("detected_plugins", []):
            plugin_counts[p] += 1
    if plugin_counts:
        print(f"\n  TOP PLUGINS")
        for plugin, count in plugin_counts.most_common(15):
            print(f"    {count:3d}  {plugin}")

    # Digital Twin
    twin_enriched = sum(1 for b in briefs if b.get("twin_scan"))
    wp_sites = sum(1 for b in briefs if b.get("technology", {}).get("cms") == "WordPress")
    print(f"\n  DIGITAL TWIN")
    print(f"    WordPress sites (eligible): {wp_sites}")
    print(f"    Twin-enriched briefs: {twin_enriched}")

    # Bucket A deep dive
    bucket_a = [b for b in briefs if b.get("bucket") == "A"]
    if bucket_a:
        a_gdpr = sum(1 for b in bucket_a if b.get("gdpr_sensitive"))
        a_findings = [len(b.get("findings", [])) for b in bucket_a]
        print(f"\n  BUCKET A DEEP DIVE ({len(bucket_a)} sites)")
        print(f"    GDPR sensitive: {a_gdpr}/{len(bucket_a)}")
        print(f"    Avg findings: {sum(a_findings) / len(a_findings):.1f}")
        print(f"    Max findings: {max(a_findings)}")

    # Top prospects
    top = sorted(
        [b for b in briefs if b.get("bucket") == "A" and b.get("gdpr_sensitive")],
        key=lambda b: len(b.get("findings", [])),
        reverse=True,
    )
    if top:
        print(f"\n  TOP 10 PROSPECTS (Bucket A + GDPR + most findings)")
        for b in top[:10]:
            cms = b.get("technology", {}).get("cms", "?")
            n = len(b.get("findings", []))
            plugins = len(b.get("technology", {}).get("detected_plugins", []))
            print(f"    {n} findings  {b['domain']:<35s}  {cms:<12s}  {plugins} plugins")

    print(f"\n{'=' * 70}")


# ---------------------------------------------------------------------------
# Deep analysis (--deep)
# ---------------------------------------------------------------------------


def analyze_deep(briefs: list[dict], csv_rows: list[dict], results_dir: Path) -> None:
    total = len(briefs)
    if total == 0:
        print("No briefs found.")
        return

    # Run summary first
    analyze_summary(briefs, csv_rows)

    print(f"\n{'=' * 70}")
    print(f"  DEEP ANALYSIS")
    print(f"{'=' * 70}")

    # --- Contactable breakdown ---
    contactable_true = sum(1 for r in csv_rows if r.get("contactable") == "True")
    contactable_false = sum(1 for r in csv_rows if r.get("contactable") == "False")
    contactable_empty = sum(1 for r in csv_rows if r.get("contactable", "") == "")

    print(f"\n  CONTACT STATUS")
    print(f"    Contactable (not Reklamebeskyttet): {contactable_true}")
    print(f"    Protected (Reklamebeskyttet):       {contactable_false}")
    print(f"    Unknown:                            {contactable_empty}")

    # Contactable by bucket
    print(f"\n  CONTACTABLE BY BUCKET")
    print(f"    {'Bucket':<10s} {'Total':>6s} {'Contact':>8s} {'Protected':>10s}")
    print(f"    {'------':<10s} {'-----':>6s} {'-------':>8s} {'---------':>10s}")
    for bucket in ["A", "B", "E", "C", "D"]:
        b_rows = [r for r in csv_rows if r.get("bucket") == bucket]
        b_contact = sum(1 for r in b_rows if r.get("contactable") == "True")
        b_protected = sum(1 for r in b_rows if r.get("contactable") == "False")
        print(f"    {bucket:<10s} {len(b_rows):>6d} {b_contact:>8d} {b_protected:>10d}")

    # --- Industry breakdown ---
    industries = Counter(r.get("industry_name", "") for r in csv_rows if r.get("industry_name"))
    if industries:
        print(f"\n  TOP INDUSTRIES")
        for ind, count in industries.most_common(15):
            print(f"    {count:3d}  {ind}")

    # GDPR by industry
    gdpr_by_industry = Counter()
    for b in briefs:
        if b.get("gdpr_sensitive") and b.get("industry"):
            gdpr_by_industry[b["industry"]] += 1
    if gdpr_by_industry:
        print(f"\n  GDPR-SENSITIVE BY INDUSTRY")
        for ind, count in gdpr_by_industry.most_common(10):
            print(f"    {count:3d}  {ind}")

    # --- Agency detection ---
    agencies = Counter()
    agency_sites = defaultdict(list)
    for b in briefs:
        tech = b.get("technology", {})
        # Check for meta author or footer credit
        for field in ["meta_author", "footer_credit"]:
            val = tech.get(field, "") or b.get(field, "")
            if val and len(val) > 2:
                agencies[val] += 1
                agency_sites[val].append(b["domain"])

    if agencies:
        print(f"\n  DETECTED AGENCIES / BUILDERS")
        for agency, count in agencies.most_common(10):
            sites = agency_sites[agency][:3]
            site_str = ", ".join(sites)
            if count > 3:
                site_str += f" +{count - 3} more"
            print(f"    {count:3d}  {agency:<30s}  ({site_str})")

    # --- Severity distribution ---
    severity_counts = Counter()
    for b in briefs:
        for f in b.get("findings", []):
            severity_counts[f.get("severity", "unknown")] += 1
    if severity_counts:
        print(f"\n  FINDING SEVERITY BREAKDOWN")
        for sev in ["critical", "high", "medium", "low", "info"]:
            count = severity_counts.get(sev, 0)
            bar = "#" * (count // 5)
            print(f"    {sev:<10s} {count:>4d}  {bar}")

    # --- Timing analysis ---
    results = load_results(results_dir)
    if results:
        timings = []
        for domain, result in results.items():
            timing = result.get("timing", {})
            total_ms = timing.get("total_ms", 0)
            if total_ms > 0:
                timings.append((domain, total_ms, timing))

        if timings:
            total_scan_ms = sum(t[1] for t in timings)
            avg_ms = total_scan_ms / len(timings)
            timings_sorted = sorted(timings, key=lambda x: x[1], reverse=True)

            print(f"\n  SCAN TIMING")
            print(f"    Domains scanned: {len(timings)}")
            print(f"    Total scan time: {total_scan_ms / 1000:.1f}s ({total_scan_ms / 60000:.1f} min)")
            print(f"    Average per domain: {avg_ms:.0f}ms ({avg_ms / 1000:.1f}s)")
            print(f"    Fastest: {timings_sorted[-1][1]}ms — {timings_sorted[-1][0]}")
            print(f"    Slowest: {timings_sorted[0][1]}ms — {timings_sorted[0][0]}")

            # Per-scan-type average timing
            scan_type_totals = defaultdict(list)
            for domain, total_ms, timing in timings:
                for scan_type, ms in timing.items():
                    if scan_type != "total_ms" and isinstance(ms, (int, float)):
                        scan_type_totals[scan_type].append(ms)

            if scan_type_totals:
                print(f"\n    Per-scan-type average:")
                for stype, values in sorted(scan_type_totals.items(), key=lambda x: sum(x[1]) / len(x[1]), reverse=True):
                    avg = sum(values) / len(values)
                    print(f"      {stype:<20s} {avg:>8.0f}ms avg  ({len(values)} runs)")

            # Top 5 slowest domains
            print(f"\n    Slowest 5 domains:")
            for domain, ms, _ in timings_sorted[:5]:
                print(f"      {ms:>6d}ms  {domain}")

    # --- Outreach prioritization matrix ---
    print(f"\n  OUTREACH PRIORITIZATION")
    print(f"  (Bucket A + GDPR + contactable + sorted by findings)")
    print(f"")
    print(f"    {'Domain':<35s} {'Find':>4s} {'Plugins':>7s} {'SSL':>5s} {'Industry'}")
    print(f"    {'------':<35s} {'----':>4s} {'-------':>7s} {'---':>5s} {'--------'}")

    # Build lookup from CSV for contactable + industry
    csv_lookup = {r.get("website", ""): r for r in csv_rows}

    outreach = []
    for b in briefs:
        if b.get("bucket") != "A":
            continue
        if not b.get("gdpr_sensitive"):
            continue
        csv_row = csv_lookup.get(b["domain"], {})
        if csv_row.get("contactable") != "True":
            continue
        outreach.append({
            "domain": b["domain"],
            "findings": len(b.get("findings", [])),
            "plugins": len(b.get("technology", {}).get("detected_plugins", [])),
            "ssl_valid": b.get("technology", {}).get("ssl", {}).get("valid", False),
            "industry": b.get("industry", ""),
            "company": b.get("company_name", ""),
        })

    outreach.sort(key=lambda x: x["findings"], reverse=True)
    for p in outreach:
        ssl_icon = "OK" if p["ssl_valid"] else "NO"
        industry_short = p["industry"][:30] if p["industry"] else ""
        print(f"    {p['domain']:<35s} {p['findings']:>4d} {p['plugins']:>7d} {ssl_icon:>5s} {industry_short}")

    print(f"\n    Total outreach candidates: {len(outreach)}")

    # --- Summary stats ---
    print(f"\n  QUICK STATS FOR SALES")
    print(f"    '{len(briefs)} businesses scanned in Vejle'")

    wp_count = sum(1 for b in briefs if b.get("technology", {}).get("cms") == "WordPress")
    no_ssl_count = sum(1 for b in briefs if b.get("technology", {}).get("ssl", {}).get("days_remaining", -1) == -1)
    missing_hsts = sum(1 for b in briefs for f in b.get("findings", []) if "HSTS" in f.get("description", ""))
    with_findings = sum(1 for b in briefs if b.get("findings"))
    pct_with_findings = with_findings * 100 // total if total else 0

    print(f"    '{pct_with_findings}% have at least one security issue'")
    print(f"    '{no_ssl_count} have no SSL certificate at all'")
    print(f"    '{wp_count} run WordPress'")
    print(f"    '{missing_hsts} are missing HSTS (HTTPS enforcement)'")
    print(f"    '{len(outreach)} are high-priority, GDPR-sensitive, and contactable'")

    print(f"\n{'=' * 70}")


def main():
    parser = argparse.ArgumentParser(description="Analyze Heimdall pipeline output")
    parser.add_argument("--briefs-dir", default="data/output/briefs")
    parser.add_argument("--csv", default="data/output/prospects-list.csv")
    parser.add_argument("--results-dir", default="data/results")
    parser.add_argument("--deep", action="store_true", help="Run deep analysis with contactable, industry, timing, and outreach prioritization")
    args = parser.parse_args()

    briefs = load_briefs(Path(args.briefs_dir))
    csv_rows = load_csv(Path(args.csv))

    if args.deep:
        analyze_deep(briefs, csv_rows, Path(args.results_dir))
    else:
        analyze_summary(briefs, csv_rows)


if __name__ == "__main__":
    main()
