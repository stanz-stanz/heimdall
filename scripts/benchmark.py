#!/usr/bin/env python3
"""Heimdall Pipeline Benchmark (Increment 1.3)

Measures wall-clock time for each pipeline stage and per-scan-type within the
scanning stage. Supports real execution and a --mock mode that replaces all
network I/O and CLI tools with fast stubs so the Python overhead can be
profiled without hitting the internet.

Performance targets (from docs/architecture/pi5-docker-architecture.md):
  - Per domain: < 30 s (cold cache)
  - 50 domains:  < 10 min
  - 1000 domains: < 30 min (with caching)

Usage:
    python scripts/benchmark.py                    # 5 real domains from CVR
    python scripts/benchmark.py --domains 20       # 20 real domains
    python scripts/benchmark.py --mock             # mock mode (no network)
    python scripts/benchmark.py --mock --domains 50 --output bench.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure the repo root is on sys.path so `src.prospecting` is importable
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

# ---------------------------------------------------------------------------
# Timing helpers
# ---------------------------------------------------------------------------

def _ms(seconds: float) -> int:
    """Convert seconds to integer milliseconds."""
    return int(round(seconds * 1000))


def _timer():
    """Return a context-manager-like pair: call start(), then elapsed_ms()."""
    class _T:
        def __init__(self):
            self._start = time.perf_counter()
        def elapsed_ms(self) -> int:
            return _ms(time.perf_counter() - self._start)
    return _T()


# ---------------------------------------------------------------------------
# Mock data generators
# ---------------------------------------------------------------------------

_FAKE_DOMAINS = [
    "example-restaurant.dk",
    "tandlaege-soenderborg.dk",
    "hotel-nordjylland.dk",
    "fysioterapi-odense.dk",
    "advokat-horsens.dk",
    "baadservice-svendborg.dk",
    "toemrer-silkeborg.dk",
    "gartner-roskilde.dk",
    "boghandel-kolding.dk",
    "dyreklinik-aarhus.dk",
    "ejendomsmaegler-vejle.dk",
    "frisorsalon-aalborg.dk",
    "guldsmed-herning.dk",
    "hjemmeservice-esbjerg.dk",
    "isenkram-naestved.dk",
    "klinik-fredericia.dk",
    "laaseservice-helsingor.dk",
    "malerfirma-viborg.dk",
    "nattevagt-koebenhavn.dk",
    "optiker-randers.dk",
    "planlaeggerfirma-skive.dk",
    "revisorfirma-slagelse.dk",
    "smedefirma-holstebro.dk",
    "taxi-horsholm.dk",
    "underviser-hillerod.dk",
    "vinduespudser-haderslev.dk",
    "web-bureau-copenhagen.dk",
    "xtra-service-odense.dk",
    "yoga-studio-aarhus.dk",
    "zoologisk-have-aalborg.dk",
    "bageri-slagelse.dk",
    "cafe-ishoj.dk",
    "danseskole-roskilde.dk",
    "elektrik-greve.dk",
    "fotograf-koege.dk",
    "glarmester-taastrup.dk",
    "handelsfirma-ballerup.dk",
    "it-support-lyngby.dk",
    "jord-og-beton-hvidovre.dk",
    "kunstgalleri-dragor.dk",
    "landskabsarkitekt-gentofte.dk",
    "musikskole-valby.dk",
    "notarkontor-frederiksberg.dk",
    "ortoptist-vanlose.dk",
    "psykolog-norrebro.dk",
    "rengoring-amager.dk",
    "skraedder-christianshavn.dk",
    "terapeut-osterbro.dk",
    "udlejning-vesterbro.dk",
    "vaerksted-bronshoj.dk",
]


def _fake_companies(n: int):
    """Build n mock Company objects without reading Excel."""
    from prospecting.cvr import Company

    companies = []
    for i in range(n):
        domain = _FAKE_DOMAINS[i % len(_FAKE_DOMAINS)]
        companies.append(Company(
            cvr=str(10000000 + i),
            name=f"Mock Firma {i + 1}",
            address=f"Testvej {i + 1}",
            postcode="1000",
            city="Testby",
            company_form="ApS",
            industry_code="561010",
            industry_name="Restauranter",
            phone="12345678",
            email=f"info@{domain}",
            website_domain=domain,
        ))
    return companies


# ---------------------------------------------------------------------------
# Mock patchers
# ---------------------------------------------------------------------------

_MOCK_HTTPX_LINE = json.dumps({
    "input": "PLACEHOLDER",
    "host": "PLACEHOLDER",
    "status_code": 200,
    "title": "Welcome",
    "webserver": "nginx",
    "tech": ["WordPress", "PHP:8.2", "MySQL"],
})

_MOCK_WEBANALYZE = json.dumps([{
    "hostname": "https://PLACEHOLDER",
    "matches": [
        {"app_name": "WordPress"},
        {"app_name": "PHP"},
    ],
}])

_MOCK_SUBFINDER_LINE = json.dumps({"host": "mail.PLACEHOLDER"})

_MOCK_DNSX_LINE = json.dumps({
    "host": "PLACEHOLDER",
    "a": ["93.184.216.34"],
    "aaaa": [],
    "cname": [],
    "mx": ["mail.PLACEHOLDER"],
    "ns": ["ns1.example.dk"],
    "txt": [],
})


def _mock_subprocess_run(domains: list[str]):
    """Return a side_effect function for subprocess.run that returns canned output."""

    def _side_effect(cmd, **kwargs):
        tool = cmd[0] if cmd else ""
        result = MagicMock()
        result.returncode = 0
        result.stderr = ""

        if "httpx" in tool:
            lines = []
            for d in domains:
                lines.append(_MOCK_HTTPX_LINE.replace("PLACEHOLDER", d))
            result.stdout = "\n".join(lines)
        elif "webanalyze" in tool:
            entries = []
            for d in domains:
                entries.append({
                    "hostname": f"https://{d}",
                    "matches": [{"app_name": "WordPress"}, {"app_name": "PHP"}],
                })
            result.stdout = json.dumps(entries)
        elif "subfinder" in tool:
            lines = []
            for d in domains:
                lines.append(json.dumps({"host": f"mail.{d}"}))
            result.stdout = "\n".join(lines)
        elif "dnsx" in tool:
            lines = []
            for d in domains:
                lines.append(_MOCK_DNSX_LINE.replace("PLACEHOLDER", d))
            result.stdout = "\n".join(lines)
        else:
            result.stdout = ""
        return result

    return _side_effect


def _mock_requests_get(*args, **kwargs):
    """Mock requests.get with fast stub responses."""
    url = args[0] if args else kwargs.get("url", "")
    resp = MagicMock()
    resp.status_code = 200
    resp.url = url

    if "robots.txt" in url:
        resp.text = "User-agent: *\nAllow: /"
    elif "crt.sh" in url:
        resp.json.return_value = [
            {"common_name": "*.example.dk", "issuer_name": "Let's Encrypt", "not_before": "2025-01-01", "not_after": "2026-01-01"},
        ]
        resp.text = "[]"
    else:
        resp.text = (
            '<html><head><meta name="author" content="Test Bureau">'
            "</head><body><footer>Website by Test Bureau</footer></body></html>"
        )
    return resp


def _mock_requests_head(*args, **kwargs):
    """Mock requests.head with stub headers."""
    resp = MagicMock()
    resp.status_code = 200
    resp.headers = {
        "x-frame-options": "SAMEORIGIN",
        "content-security-policy": "default-src 'self'",
        "strict-transport-security": "max-age=31536000",
        "x-content-type-options": "nosniff",
        "server": "nginx",
    }
    return resp


def _mock_ssl_context():
    """Return a mock SSL context that produces a fake certificate."""
    ctx = MagicMock()
    sock = MagicMock()
    sock.getpeercert.return_value = {
        "notAfter": "Jan 15 00:00:00 2027 GMT",
        "issuer": ((("organizationName", "Let's Encrypt"),),),
    }
    ctx.wrap_socket.return_value.__enter__ = MagicMock(return_value=sock)
    ctx.wrap_socket.return_value.__exit__ = MagicMock(return_value=False)
    return ctx


# ---------------------------------------------------------------------------
# Per-scan-type timing within the scanning stage
# ---------------------------------------------------------------------------

def _timed_scan_domains(companies, mocked, domains_list):
    """Run scan_domains while capturing per-scan-type timings.

    In mock mode we instrument each scanner function. In real mode we time
    the whole scanning stage and report scan_types with an estimate note.
    """
    from prospecting.scanner import (
        _check_ssl,
        _extract_page_meta,
        _get_response_headers,
        _query_crt_sh,
        _query_grayhatwarfare,
        _run_dnsx,
        _run_httpx,
        _run_subfinder,
        _run_webanalyze,
        scan_domains,
    )

    scan_type_timings: dict[str, dict] = {}
    per_domain_timings: dict[str, list[int]] = {
        "ssl": [],
        "headers": [],
        "meta": [],
        "crt_sh": [],
    }
    batch_timings: dict[str, dict] = {}

    # Wrappers that record timing
    def _wrap_per_domain(name, fn):
        def wrapper(*a, **kw):
            t = _timer()
            result = fn(*a, **kw)
            per_domain_timings[name].append(t.elapsed_ms())
            return result
        return wrapper

    def _wrap_batch(name, fn):
        def wrapper(*a, **kw):
            t = _timer()
            result = fn(*a, **kw)
            batch_timings[name] = {"duration_ms": t.elapsed_ms(), "batch": True}
            return result
        return wrapper

    patches = [
        patch("prospecting.scanner._check_ssl", _wrap_per_domain("ssl", _check_ssl)),
        patch("prospecting.scanner._get_response_headers", _wrap_per_domain("headers", _get_response_headers)),
        patch("prospecting.scanner._extract_page_meta", _wrap_per_domain("meta", _extract_page_meta)),
        patch("prospecting.scanner._run_httpx", _wrap_batch("httpx", _run_httpx)),
        patch("prospecting.scanner._run_webanalyze", _wrap_batch("webanalyze", _run_webanalyze)),
        patch("prospecting.scanner._run_subfinder", _wrap_batch("subfinder", _run_subfinder)),
        patch("prospecting.scanner._run_dnsx", _wrap_batch("dnsx", _run_dnsx)),
        patch("prospecting.scanner._query_crt_sh", _wrap_batch("crt_sh", _query_crt_sh)),
        patch("prospecting.scanner._query_grayhatwarfare", _wrap_batch("grayhatwarfare", _query_grayhatwarfare)),
    ]

    for p in patches:
        p.start()

    try:
        t = _timer()
        results = scan_domains(companies, confirmed=True)
        total_ms = t.elapsed_ms()
    finally:
        for p in patches:
            p.stop()

    # Assemble scan_types dict
    for name, times in per_domain_timings.items():
        if times:
            scan_type_timings[name] = {
                "avg_ms": int(round(sum(times) / len(times))),
                "min_ms": min(times),
                "max_ms": max(times),
            }

    for name, info in batch_timings.items():
        scan_type_timings[name] = info

    # Check if grayhatwarfare was skipped (no API key)
    if "grayhatwarfare" not in scan_type_timings:
        scan_type_timings["grayhatwarfare"] = {"avg_ms": 0, "skipped": True}

    n = len(results)
    return results, {
        "duration_ms": total_ms,
        "per_domain_avg_ms": int(round(total_ms / n)) if n else 0,
        "scan_types": scan_type_timings,
    }, n


# ---------------------------------------------------------------------------
# Main benchmark runner
# ---------------------------------------------------------------------------

def run_benchmark(n_domains: int, mocked: bool, output_path: Path) -> dict:
    """Execute the full benchmark and return the results dict."""
    from src.core.logging_config import setup_logging
    setup_logging(level="WARNING")

    from prospecting.agency_detector import detect_agencies
    from prospecting.brief_generator import generate_brief
    from prospecting.bucketer import assign_buckets
    from prospecting.config import DEFAULT_FILTERS, DEFAULT_INPUT
    from prospecting.cvr import derive_domains, read_excel
    from prospecting.filters import apply_post_scan_filters, apply_pre_scan_filters, load_filters
    from prospecting.output import write_agency_briefs, write_briefs, write_csv
    from prospecting.resolver import resolve_domains

    stages: dict[str, dict] = {}
    overall_start = time.perf_counter()

    # Context managers for mock mode
    mock_ctx_managers = []
    domains_for_mock = [_FAKE_DOMAINS[i % len(_FAKE_DOMAINS)] for i in range(n_domains)]

    if mocked:
        mock_ctx_managers = [
            patch("prospecting.scanner.requests.get", side_effect=_mock_requests_get),
            patch("prospecting.scanner.requests.head", side_effect=_mock_requests_head),
            patch("prospecting.resolver.requests.get", side_effect=_mock_requests_get),
            patch("prospecting.scanner.subprocess.run", side_effect=_mock_subprocess_run(domains_for_mock)),
            patch("prospecting.scanner.shutil.which", return_value="/usr/local/bin/mock"),
            patch("prospecting.scanner.ssl.create_default_context", return_value=_mock_ssl_context()),
            patch("prospecting.scanner._validate_approval_tokens", return_value={"approvals": []}),
            patch("prospecting.scanner._write_pre_scan_check", return_value=Path("/dev/null")),
            patch("prospecting.scanner.time.sleep"),  # skip crt.sh delays
            # Suppress operator output in benchmark
            patch("prospecting.operator.print_gate1_summary"),
            patch("prospecting.operator.print_pre_scan_summary"),
            patch("prospecting.operator.print_run_summary"),
            patch("prospecting.operator.write_run_summary", return_value=Path("/dev/null")),
        ]
        for cm in mock_ctx_managers:
            cm.start()

    try:
        # --- Stage 1: CVR read ---
        t = _timer()
        if mocked:
            companies = _fake_companies(n_domains)
        else:
            companies = read_excel(DEFAULT_INPUT)
            # Limit to N domains
            companies = companies[:n_domains * 3]  # read extra to account for filtering
        stages["cvr_read"] = {"duration_ms": t.elapsed_ms()}

        # --- Stage 2: Pre-scan filters ---
        t = _timer()
        if mocked:
            filters = {}
        else:
            filters = load_filters(DEFAULT_FILTERS)
        companies = apply_pre_scan_filters(companies, filters)
        stages["pre_scan_filters"] = {"duration_ms": t.elapsed_ms()}

        # --- Stage 3: Domain derivation ---
        t = _timer()
        if not mocked:
            companies = derive_domains(companies)
        # In mock mode, domains are pre-set
        stages["domain_derivation"] = {"duration_ms": t.elapsed_ms()}

        # --- Stage 4: Domain resolution ---
        t = _timer()
        companies = resolve_domains(companies)
        alive = sum(1 for c in companies if not c.discarded and c.website_domain)
        dead = sum(1 for c in companies if c.discard_reason in ("no_website", "robots_txt_denied"))
        stages["domain_resolution"] = {
            "duration_ms": t.elapsed_ms(),
            "alive": alive,
            "dead": dead,
        }

        # Trim to exactly N domains for scanning
        active = [c for c in companies if not c.discarded and c.website_domain]
        if len(active) > n_domains:
            # Discard extras
            for c in active[n_domains:]:
                c.discard_reason = "benchmark_limit"
            active = active[:n_domains]
        domains_list = [c.website_domain for c in active]

        # --- Stage 5: Scanning (with per-type timing) ---
        scan_results, scanning_stage, scanned_count = _timed_scan_domains(
            companies, mocked, domains_list,
        )
        stages["scanning"] = scanning_stage

        # --- Stage 6: Bucketing ---
        t = _timer()
        buckets = assign_buckets(companies, scan_results)
        stages["bucketing"] = {"duration_ms": t.elapsed_ms()}

        # --- Stage 7: Post-scan filters ---
        t = _timer()
        companies = apply_post_scan_filters(companies, buckets, filters)
        stages["post_scan_filters"] = {"duration_ms": t.elapsed_ms()}

        # --- Stage 8: Agency detection ---
        t = _timer()
        agency_briefs = detect_agencies(companies, scan_results, buckets)
        stages["agency_detection"] = {"duration_ms": t.elapsed_ms()}

        # --- Stage 9: Brief generation ---
        t = _timer()
        site_briefs: dict[str, dict] = {}
        for company in companies:
            if company.discarded or not company.website_domain:
                continue
            scan = scan_results.get(company.website_domain)
            if not scan:
                continue
            bucket = buckets.get(company.cvr, "D")
            brief = generate_brief(company, scan, bucket)
            site_briefs[company.website_domain] = brief
        stages["brief_generation"] = {"duration_ms": t.elapsed_ms()}

        # --- Stage 10: Output write ---
        t = _timer()
        if not mocked:
            write_csv(companies, buckets, site_briefs, scan_results)
            write_briefs(site_briefs)
            write_agency_briefs(agency_briefs)
        stages["output_write"] = {"duration_ms": t.elapsed_ms()}

    finally:
        for cm in mock_ctx_managers:
            cm.stop()

    total_ms = _ms(time.perf_counter() - overall_start)
    per_domain_actual = int(round(total_ms / n_domains)) if n_domains else 0
    per_domain_target = 30000

    result = {
        "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "domains_count": n_domains,
        "mocked": mocked,
        "stages": stages,
        "total_duration_ms": total_ms,
        "performance_targets": {
            "per_domain_target_ms": per_domain_target,
            "per_domain_actual_ms": per_domain_actual,
            "target_met": per_domain_actual <= per_domain_target,
        },
    }

    # Write JSON output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    return result


# ---------------------------------------------------------------------------
# Terminal output
# ---------------------------------------------------------------------------

def _print_results(result: dict) -> None:
    """Print a clean benchmark table to stdout."""
    n = result["domains_count"]
    stages = result["stages"]
    total = result["total_duration_ms"]
    perf = result["performance_targets"]
    mode = "MOCK" if result["mocked"] else "LIVE"

    print(f"\nHeimdall Pipeline Benchmark -- {n} domains ({mode})")
    print("=" * 48)

    def _row(label: str, ms: int, extra: str = ""):
        suffix = f"  {extra}" if extra else ""
        print(f"  {label:<22}{ms:>7} ms{suffix}")

    _row("CVR read:", stages["cvr_read"]["duration_ms"])
    _row("Pre-scan filters:", stages["pre_scan_filters"]["duration_ms"])
    _row("Domain derivation:", stages["domain_derivation"]["duration_ms"])

    res = stages["domain_resolution"]
    _row("Domain resolution:", res["duration_ms"],
         f"({res.get('alive', '?')} alive, {res.get('dead', '?')} dead)")

    sc = stages["scanning"]
    _row("Scanning:", sc["duration_ms"],
         f"({sc.get('per_domain_avg_ms', '?')} ms/domain avg)")

    # Per-scan-type breakdown
    scan_types = sc.get("scan_types", {})
    for name, info in scan_types.items():
        if info.get("skipped"):
            print(f"    {name + ':':<20}{'skipped':>7}")
        elif info.get("batch"):
            print(f"    {name + ':':<20}{info['duration_ms']:>7} ms (batch)")
        else:
            print(f"    {name + ':':<20}{info.get('avg_ms', 0):>7} ms avg")

    _row("Bucketing:", stages["bucketing"]["duration_ms"])

    if "post_scan_filters" in stages:
        _row("Post-scan filters:", stages["post_scan_filters"]["duration_ms"])

    _row("Agency detection:", stages["agency_detection"]["duration_ms"])
    _row("Brief generation:", stages["brief_generation"]["duration_ms"])
    _row("Output write:", stages["output_write"]["duration_ms"])

    print("-" * 48)
    target_mark = "OK" if perf["target_met"] else "EXCEEDED"
    _row("TOTAL:", total)
    print(f"  {'Per-domain avg:':<22}{perf['per_domain_actual_ms']:>7} ms  "
          f"(target: <{perf['per_domain_target_ms']} ms {target_mark})")
    print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Benchmark the Heimdall pipeline stages",
    )
    parser.add_argument(
        "--domains", type=int, default=5,
        help="Number of domains to scan (default: 5)",
    )
    parser.add_argument(
        "--mock", action="store_true",
        help="Use mocked HTTP responses instead of real network (for CI)",
    )
    parser.add_argument(
        "--output", type=str,
        default=str(REPO_ROOT / "data" / "benchmarks" / "latest.json"),
        help="Write results JSON to this path (default: data/benchmarks/latest.json)",
    )
    args = parser.parse_args()

    output_path = Path(args.output)

    print(f"Running benchmark: {args.domains} domains, "
          f"{'mock' if args.mock else 'live'} mode")
    print(f"Output: {output_path}")

    result = run_benchmark(args.domains, args.mock, output_path)
    _print_results(result)

    print(f"Results written to {output_path}")


if __name__ == "__main__":
    main()
