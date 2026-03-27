#!/usr/bin/env python3
"""Analyze scan results from a Docker run.

Usage:
    python scripts/analyze_results.py /data/results/prospect
    python scripts/analyze_results.py --results-dir /path/to/results
    python scripts/analyze_results.py  # defaults to data/output/results or /data/results/prospect

Can be run on the Pi5 directly or with results copied to laptop.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path


def load_results(results_dir: Path) -> list[dict]:
    """Load all JSON result files from a results directory tree."""
    results = []
    for path in sorted(results_dir.rglob("*.json")):
        try:
            with open(path) as f:
                data = json.load(f)
            if "domain" in data or "scan_result" in data:
                data["_source_file"] = str(path)
                results.append(data)
        except (json.JSONDecodeError, OSError) as e:
            print(f"  WARN: skipping {path}: {e}", file=sys.stderr)
    return results


def analyze(results: list[dict]) -> dict:
    """Produce summary statistics from scan results."""
    total = len(results)
    completed = [r for r in results if r.get("status") == "completed"]
    skipped = [r for r in results if r.get("status") == "skipped"]
    failed = [r for r in results if r.get("status") not in ("completed", "skipped")]

    # Timing — handle both total_ms (int, new) and total (float seconds, legacy)
    durations = []
    for r in completed:
        t = r.get("timing", {})
        if "total_ms" in t:
            durations.append(t["total_ms"])
        elif "total" in t:
            durations.append(int(t["total"] * 1000))
        else:
            durations.append(0)
    avg_ms = sum(durations) / len(durations) if durations else 0
    max_ms = max(durations) if durations else 0
    min_ms = min(durations) if durations else 0

    # Cache stats
    total_hits = sum(r.get("cache_stats", {}).get("hits", 0) for r in completed)
    total_misses = sum(r.get("cache_stats", {}).get("misses", 0) for r in completed)

    # Scan results
    scan_results = [r.get("scan_result", {}) for r in completed]
    briefs = [r.get("brief", {}) for r in completed]

    # CMS distribution
    cms_counter = Counter()
    for sr in scan_results:
        cms = sr.get("cms", "")
        cms_counter[cms or "(none)"] += 1

    # Findings by severity — read from brief (preferred) or scan_result (legacy)
    severity_counter = Counter()
    finding_types = Counter()
    for brief in briefs:
        for f in brief.get("findings", []):
            severity_counter[f.get("severity", "unknown")] += 1
            finding_types[f.get("description", "unknown")[:60]] += 1

    # GDPR — read from brief
    gdpr_sensitive = sum(1 for b in briefs if b.get("gdpr_sensitive"))
    gdpr_reasons = Counter()
    for b in briefs:
        for reason in b.get("gdpr_reasons", []):
            gdpr_reasons[reason[:60]] += 1

    # Hosting
    hosting_counter = Counter()
    for sr in scan_results:
        hosting_counter[sr.get("hosting", "") or "(unknown)"] += 1

    # SSL
    ssl_valid = sum(1 for sr in scan_results if sr.get("ssl_valid"))
    ssl_invalid = sum(1 for sr in scan_results if not sr.get("ssl_valid"))

    # Subdomains
    subdomain_counts = [len(sr.get("subdomains", [])) for sr in scan_results]
    total_subdomains = sum(subdomain_counts)

    # Per-scan-type timing — convert to ms
    type_durations: dict[str, list[int]] = {}
    for r in completed:
        for scan_type, val in r.get("timing", {}).items():
            if scan_type in ("total_ms", "total"):
                continue
            if isinstance(val, (int, float)):
                ms = int(val) if val > 100 else int(val * 1000)  # auto-detect s vs ms
                type_durations.setdefault(scan_type, []).append(ms)

    return {
        "total_domains": total,
        "completed": len(completed),
        "skipped": len(skipped),
        "failed": len(failed),
        "timing": {
            "avg_ms": int(avg_ms),
            "min_ms": min_ms,
            "max_ms": max_ms,
            "total_ms": sum(durations),
        },
        "cache": {
            "total_hits": total_hits,
            "total_misses": total_misses,
            "hit_rate": f"{total_hits / (total_hits + total_misses) * 100:.1f}%" if (total_hits + total_misses) > 0 else "N/A",
        },
        "cms": dict(cms_counter.most_common()),
        "hosting": dict(hosting_counter.most_common(10)),
        "ssl": {"valid": ssl_valid, "invalid": ssl_invalid},
        "gdpr": {"sensitive": gdpr_sensitive, "not_sensitive": len(completed) - gdpr_sensitive, "reasons": dict(gdpr_reasons.most_common(10))},
        "findings": {
            "total": sum(severity_counter.values()),
            "by_severity": dict(severity_counter.most_common()),
            "top_types": dict(finding_types.most_common(15)),
        },
        "subdomains": {"total": total_subdomains, "avg_per_domain": round(total_subdomains / len(completed), 1) if completed else 0},
        "scan_type_timing": {
            st: {"avg_ms": int(sum(v) / len(v)), "max_ms": max(v), "min_ms": min(v)}
            for st, v in sorted(type_durations.items())
        },
    }


def print_report(stats: dict) -> None:
    """Print a human-readable summary."""
    print("=" * 60)
    print("  Heimdall Scan Results Analysis")
    print("=" * 60)
    print()

    print(f"  Domains: {stats['total_domains']} total, {stats['completed']} completed, {stats['skipped']} skipped, {stats['failed']} failed")
    print()

    t = stats["timing"]
    print(f"  Timing: {t['avg_ms']}ms avg, {t['min_ms']}ms min, {t['max_ms']}ms max")
    print(f"  Total scan time: {t['total_ms'] / 1000:.0f}s ({t['total_ms'] / 60000:.1f} min)")
    print()

    c = stats["cache"]
    print(f"  Cache: {c['total_hits']} hits, {c['total_misses']} misses ({c['hit_rate']} hit rate)")
    print()

    print("  CMS Distribution:")
    for cms, count in stats["cms"].items():
        print(f"    {cms:30s} {count:4d}")
    print()

    print("  Hosting Providers:")
    for host, count in stats["hosting"].items():
        print(f"    {host:30s} {count:4d}")
    print()

    s = stats["ssl"]
    print(f"  SSL: {s['valid']} valid, {s['invalid']} invalid")
    print()

    g = stats["gdpr"]
    print(f"  GDPR Sensitive: {g['sensitive']} yes, {g['not_sensitive']} no")
    if g["reasons"]:
        print("  Top reasons:")
        for reason, count in g["reasons"].items():
            print(f"    {reason:55s} {count:4d}")
    print()

    f = stats["findings"]
    print(f"  Findings: {f['total']} total")
    print("  By severity:")
    for sev, count in f["by_severity"].items():
        print(f"    {sev:15s} {count:4d}")
    print()
    print("  Top finding types:")
    for desc, count in f["top_types"].items():
        print(f"    {desc:55s} {count:4d}")
    print()

    sub = stats["subdomains"]
    print(f"  Subdomains: {sub['total']} total ({sub['avg_per_domain']} avg/domain)")
    print()

    if stats["scan_type_timing"]:
        print("  Per-scan-type timing:")
        for st, timing in stats["scan_type_timing"].items():
            print(f"    {st:15s}  avg {timing['avg_ms']:6d}ms  min {timing['min_ms']:6d}ms  max {timing['max_ms']:6d}ms")
    print()
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Analyze Heimdall scan results")
    parser.add_argument("results_dir", nargs="?", default=None, help="Path to results directory")
    parser.add_argument("--json", action="store_true", help="Output as JSON instead of table")
    args = parser.parse_args()

    # Find results directory
    if args.results_dir:
        results_dir = Path(args.results_dir)
    elif Path("/data/results/prospect").is_dir():
        results_dir = Path("/data/results/prospect")
    elif Path("data/results/prospect").is_dir():
        results_dir = Path("data/results/prospect")
    else:
        print("ERROR: No results directory found. Specify path as argument.", file=sys.stderr)
        sys.exit(1)

    print(f"Loading results from {results_dir}...", file=sys.stderr)
    results = load_results(results_dir)
    if not results:
        print("No results found.", file=sys.stderr)
        sys.exit(1)

    print(f"Loaded {len(results)} results.", file=sys.stderr)
    stats = analyze(results)

    if args.json:
        print(json.dumps(stats, indent=2))
    else:
        print_report(stats)


if __name__ == "__main__":
    main()
