#!/usr/bin/env python3
"""Analyze pipeline output — prospect list + briefs.

Usage:
    python3 scripts/analyze_pipeline.py [--briefs-dir DIR] [--csv PATH]

Produces a full breakdown: buckets, CMS, hosting, GDPR, findings,
plugins, SSL status, digital twin coverage, and top prospects.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
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


def analyze(briefs: list[dict], csv_rows: list[dict]) -> None:
    total = len(briefs)
    if total == 0:
        print("No briefs found.")
        return

    print(f"{'=' * 60}")
    print(f"  HEIMDALL PIPELINE ANALYSIS — {total} domains")
    print(f"{'=' * 60}")

    # --- Buckets ---
    buckets = Counter(b.get("bucket", "?") for b in briefs)
    print(f"\n  BUCKETS")
    for bucket in ["A", "B", "E", "C", "D"]:
        count = buckets.get(bucket, 0)
        bar = "#" * (count // 2)
        print(f"    {bucket}: {count:3d}  {bar}")

    # --- CMS ---
    cms_counts = Counter(b.get("technology", {}).get("cms", "") or "none" for b in briefs)
    print(f"\n  CMS DETECTION")
    for cms, count in cms_counts.most_common():
        print(f"    {count:3d}  {cms}")

    # --- Hosting ---
    hosting = Counter(b.get("technology", {}).get("hosting", "Unknown") for b in briefs)
    print(f"\n  HOSTING (top 10)")
    for h, count in hosting.most_common(10):
        print(f"    {count:3d}  {h}")

    # --- GDPR ---
    gdpr_count = sum(1 for b in briefs if b.get("gdpr_sensitive"))
    gdpr_reasons = Counter()
    for b in briefs:
        for r in b.get("gdpr_reasons", []):
            gdpr_reasons[r.split(":")[0].strip()] += 1
    print(f"\n  GDPR SENSITIVE: {gdpr_count}/{total} ({gdpr_count * 100 // total}%)")
    for reason, count in gdpr_reasons.most_common():
        print(f"    {count:3d}  {reason}")

    # --- SSL ---
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

    # --- Findings ---
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

    # --- Plugins ---
    plugin_counts = Counter()
    for b in briefs:
        for p in b.get("technology", {}).get("detected_plugins", []):
            plugin_counts[p] += 1
    if plugin_counts:
        print(f"\n  TOP PLUGINS")
        for plugin, count in plugin_counts.most_common(15):
            print(f"    {count:3d}  {plugin}")

    # --- Digital Twin ---
    twin_enriched = sum(1 for b in briefs if b.get("twin_scan"))
    wp_sites = sum(1 for b in briefs if b.get("technology", {}).get("cms") == "WordPress")
    print(f"\n  DIGITAL TWIN")
    print(f"    WordPress sites (eligible): {wp_sites}")
    print(f"    Twin-enriched briefs: {twin_enriched}")

    # --- Bucket A deep dive ---
    bucket_a = [b for b in briefs if b.get("bucket") == "A"]
    if bucket_a:
        a_gdpr = sum(1 for b in bucket_a if b.get("gdpr_sensitive"))
        a_findings = [len(b.get("findings", [])) for b in bucket_a]
        print(f"\n  BUCKET A DEEP DIVE ({len(bucket_a)} sites)")
        print(f"    GDPR sensitive: {a_gdpr}/{len(bucket_a)}")
        print(f"    Avg findings: {sum(a_findings) / len(a_findings):.1f}")
        print(f"    Max findings: {max(a_findings)}")

    # --- Top prospects (Bucket A, GDPR sensitive, most findings) ---
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

    print(f"\n{'=' * 60}")


def main():
    parser = argparse.ArgumentParser(description="Analyze Heimdall pipeline output")
    parser.add_argument("--briefs-dir", default="data/output/briefs")
    parser.add_argument("--csv", default="data/output/prospects-list.csv")
    args = parser.parse_args()

    briefs = load_briefs(Path(args.briefs_dir))
    csv_rows = load_csv(Path(args.csv))
    analyze(briefs, csv_rows)


if __name__ == "__main__":
    main()
