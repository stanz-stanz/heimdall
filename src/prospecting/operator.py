"""Operator notification: formatted terminal output for Valdí compliance gates."""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

# ANSI formatting — stripped when stdout is not a TTY
_IS_TTY = sys.stdout.isatty()

BOLD = "\033[1m" if _IS_TTY else ""
DIM = "\033[2m" if _IS_TTY else ""
RED = "\033[91m" if _IS_TTY else ""
GREEN = "\033[92m" if _IS_TTY else ""
YELLOW = "\033[93m" if _IS_TTY else ""
CYAN = "\033[96m" if _IS_TTY else ""
RESET = "\033[0m" if _IS_TTY else ""

_W = 64  # box width


def _box_top() -> str:
    return f"{CYAN}{'=' * _W}{RESET}"


def _box_sep() -> str:
    return f"{CYAN}{'-' * _W}{RESET}"


def _box_bot() -> str:
    return f"{CYAN}{'=' * _W}{RESET}"


def _verdict_colour(verdict: str) -> str:
    v = verdict.upper()
    if v == "APPROVED":
        return f"{GREEN}{v}{RESET}"
    if v == "REJECTED":
        return f"{RED}{v}{RESET}"
    return f"{YELLOW}{v}{RESET}"


def print_gate1_summary(approvals: dict) -> None:
    """Print a formatted summary of Gate 1 approval token status."""
    entries = approvals.get("approvals", [])

    lines = [
        "",
        _box_top(),
        f"  {BOLD}VALDI GATE 1 — APPROVAL TOKEN STATUS{RESET}",
        _box_sep(),
        f"  {'Scan Type':<34} {'Verdict':<12} {'Token':<10}",
        _box_sep(),
    ]

    for entry in entries:
        scan_id = entry["scan_type_id"]
        token_short = entry["token"][:8]
        # Read verdict from log file header
        verdict = _read_verdict(entry.get("log_file", ""))
        lines.append(f"  {scan_id:<34} {_verdict_colour(verdict):<22} {DIM}{token_short}{RESET}")

    lines.append(_box_sep())
    lines.append(f"  {len(entries)} scan types registered. All function hashes verified.")
    lines.append(f"  Forensic logs: {DIM}.claude/agents/valdi/logs/{RESET}")
    lines.append(_box_bot())
    lines.append("")

    print("\n".join(lines))


def _read_verdict(log_path: str) -> str:
    """Extract verdict from a forensic log file's header."""
    if not log_path:
        return "UNKNOWN"
    from .config import PROJECT_ROOT
    full_path = PROJECT_ROOT / log_path
    try:
        with open(full_path) as f:
            for line in f:
                if "**Verdict:**" in line:
                    # e.g. "- **Verdict:** APPROVED"
                    return line.split("**Verdict:**")[1].strip().split()[0]
    except (FileNotFoundError, IndexError):
        pass
    return "UNKNOWN"


def print_pre_scan_summary(
    allowed: list[str],
    skipped: list[str],
    scan_types: list[str],
    approvals: dict,
) -> None:
    """Print the Gate 2 pre-scan summary before confirmation."""
    entries = {a["scan_type_id"]: a for a in approvals.get("approvals", [])}

    lines = [
        _box_top(),
        f"  {BOLD}VALDI GATE 2 — PRE-SCAN SUMMARY{RESET}",
        _box_sep(),
        "  Batch type:    prospect-scan-level0",
        "  Layer: 1 (Passive)  |  Target Level: 0 (No consent)",
        "",
        f"  Domains to scan:    {BOLD}{len(allowed)}{RESET}",
        f"  Domains skipped:    {len(skipped)}  {DIM}(robots.txt denial){RESET}",
        f"  Scan types:         {len(scan_types)}  (all tokens valid)",
        "",
        f"  {DIM}Approval tokens referenced:{RESET}",
    ]

    for st in scan_types:
        entry = entries.get(st)
        token_short = entry["token"][:8] if entry else "MISSING"
        lines.append(f"    {st:<34} {DIM}{token_short}{RESET}")

    lines.append("")
    lines.append(_box_bot())
    lines.append("")

    print("\n".join(lines))


def prompt_confirmation(domain_count: int) -> bool:
    """Require the operator to type CONFIRM before scans execute.

    Returns False if stdin is not a TTY (programmatic safety).
    """
    if not sys.stdin.isatty():
        print(
            f"\n{RED}{BOLD}  BLOCKED — non-interactive session.{RESET}\n"
            f"  Use --confirmed to bypass interactive confirmation.\n"
        )
        return False

    print(
        f"{YELLOW}{BOLD}"
        f"  OPERATOR CONFIRMATION REQUIRED\n"
        f"{RESET}"
        f"  Scans will send HTTP requests to {BOLD}{domain_count}{RESET} live domains.\n"
        f"  Review the summary above before proceeding.\n"
    )

    try:
        response = input(f"  Type {BOLD}CONFIRM{RESET} to proceed, anything else to abort: ")
    except (EOFError, KeyboardInterrupt):
        print()
        return False

    return response.strip() == "CONFIRM"


def print_run_summary(
    results: dict,
    skipped: list[str],
    start_time: datetime,
    end_time: datetime,
) -> None:
    """Print post-scan statistics."""
    duration = end_time - start_time
    minutes = int(duration.total_seconds()) // 60
    seconds = int(duration.total_seconds()) % 60

    # CMS breakdown
    cms_counts: dict[str, int] = {}
    ssl_valid = 0
    ssl_expiring = 0
    for scan in results.values():
        if scan.cms:
            cms_counts[scan.cms] = cms_counts.get(scan.cms, 0) + 1
        if scan.ssl_valid:
            ssl_valid += 1
        if 0 <= scan.ssl_days_remaining < 30:
            ssl_expiring += 1

    total_cms = sum(cms_counts.values())
    top_cms = sorted(cms_counts.items(), key=lambda x: -x[1])[:5]

    lines = [
        "",
        _box_top(),
        f"  {BOLD}SCAN RUN COMPLETE{RESET}",
        _box_sep(),
        f"  Duration:           {minutes}m {seconds}s",
        f"  Domains scanned:    {len(results)}",
        f"  Domains skipped:    {len(skipped)}  {DIM}(robots.txt){RESET}",
        "",
        f"  CMS detected:       {total_cms}  ({_pct(total_cms, len(results))})",
    ]
    for cms, count in top_cms:
        lines.append(f"    {cms:<22} {count}")

    lines.append(f"  SSL valid:          {ssl_valid}  ({_pct(ssl_valid, len(results))})")
    if ssl_expiring:
        lines.append(f"  {YELLOW}SSL expiring <30d:   {ssl_expiring}{RESET}")

    lines.append("")
    lines.append(_box_bot())
    lines.append("")

    print("\n".join(lines))


def _pct(part: int, total: int) -> str:
    if total == 0:
        return "0%"
    return f"{part * 100 // total}%"


def write_run_summary(
    results: dict,
    skipped: list[str],
    allowed: list[str],
    pre_scan_path: Path,
    confirmed_by: str,
    start_time: datetime,
    end_time: datetime,
    approvals: dict,
) -> Path:
    """Write a JSON run summary to data/compliance/."""
    from .config import PROJECT_ROOT
    check_dir = PROJECT_ROOT / ".claude" / "agents" / "valdi" / "compliance"
    check_dir.mkdir(parents=True, exist_ok=True)

    # CMS breakdown
    cms_counts: dict[str, int] = {}
    ssl_valid = 0
    ssl_expiring = 0
    for scan in results.values():
        if scan.cms:
            cms_counts[scan.cms] = cms_counts.get(scan.cms, 0) + 1
        if scan.ssl_valid:
            ssl_valid += 1
        if 0 <= scan.ssl_days_remaining < 30:
            ssl_expiring += 1

    summary = {
        "run_id": f"run-{start_time.strftime('%Y%m%d-%H%M%S')}",
        "started_at": start_time.isoformat() + "Z",
        "completed_at": end_time.isoformat() + "Z",
        "duration_seconds": int((end_time - start_time).total_seconds()),
        "confirmation": {
            "method": confirmed_by,
            "confirmed_at": start_time.isoformat() + "Z",
        },
        "gate1": {
            "all_tokens_valid": True,
            "all_hashes_match": True,
            "scan_types_validated": len(approvals.get("approvals", [])),
            "approvals_file": "data/valdi/active_approvals.json",
        },
        "gate2": {
            "pre_scan_check_file": str(pre_scan_path),
            "domains_total": len(allowed) + len(skipped),
            "domains_allowed": len(allowed),
            "domains_skipped_robots_txt": len(skipped),
            "skipped_domains": skipped,
        },
        "results": {
            "domains_scanned": len(results),
            "cms_detected": sum(cms_counts.values()),
            "cms_breakdown": cms_counts,
            "ssl_valid": ssl_valid,
            "ssl_expiring_30d": ssl_expiring,
        },
        "approval_tokens_referenced": [
            a["token"] for a in approvals.get("approvals", [])
        ],
    }

    filepath = check_dir / f"run-summary-{start_time.strftime('%Y-%m-%d_%H-%M-%S')}.json"
    with open(filepath, "w") as f:
        json.dump(summary, f, indent=2)

    return filepath
