#!/usr/bin/env python3
"""Heimdall project audit — checks infrastructure, tests, config, and gaps.

Usage:
    python3 scripts/audit.py

Verifies Dockerfile contents, dockerignore, compose config, operational
scripts, test coverage, and flags anything missing or misconfigured.
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _check(label: str, passed: bool) -> bool:
    status = "OK" if passed else "MISSING"
    print(f"  [{status}] {label}")
    return passed


def audit_dockerfile() -> int:
    """Check worker Dockerfile has all required COPY and config."""
    print("\n  WORKER DOCKERFILE")
    df_path = PROJECT_ROOT / "infra" / "docker" / "Dockerfile.worker"
    if not df_path.is_file():
        print("  [MISSING] Dockerfile.worker not found")
        return 1
    df = df_path.read_text()
    fails = 0
    for item in ["COPY tools/", "COPY src/", "COPY config/", "COPY .claude/agents/", "COPY scripts/"]:
        if not _check(item, item in df):
            fails += 1
    _check("/opt/go-tools in PATH", "/opt/go-tools" in df) or fails.__add__(1)
    _check("nuclei templates baked", "nuclei-templates" in df) or fails.__add__(1)
    _check("CMSeek cloned", "cmseek" in df.lower()) or fails.__add__(1)
    # Version pinning
    latest_lines = [l.strip() for l in df.splitlines() if "@latest" in l and l.strip().startswith("RUN")]
    if not _check("No @latest tags (all Go tools pinned)", len(latest_lines) == 0):
        for l in latest_lines:
            print(f"    ^ {l}")
        fails += 1
    if not _check("CMSeek commit pinned (git checkout)", "git checkout" in df):
        fails += 1
    return fails


def audit_dockerignore() -> int:
    """Check .dockerignore excludes what it should and includes what it must."""
    print("\n  DOCKERIGNORE")
    di_path = PROJECT_ROOT / ".dockerignore"
    if not di_path.is_file():
        print("  [MISSING] .dockerignore not found")
        return 1
    di = di_path.read_text()
    fails = 0
    for item in [".git", "data/", "tests/", "docs/", ".env"]:
        if not _check(f"Excludes {item}", item in di):
            fails += 1
    # .claude/agents must NOT be excluded (or must have exception)
    excluded = ".claude/" in di and "!.claude/agents" not in di
    if not _check("Allows .claude/agents/", not excluded):
        fails += 1
    return fails


def audit_compose() -> int:
    """Check docker-compose.yml has required services, volumes, ports."""
    print("\n  DOCKER COMPOSE")
    compose_path = PROJECT_ROOT / "infra" / "docker" / "docker-compose.yml"
    if not compose_path.is_file():
        print("  [MISSING] docker-compose.yml not found")
        return 1
    compose = compose_path.read_text()
    fails = 0
    checks = [
        ("results bind-mounted (not named volume)", "../../data/results:/data/results"),
        ("briefs mounted for API", "briefs"),
        ("port 8000 exposed", "8000:8000"),
        ("twin service defined", "Dockerfile.twin"),
        ("enriched data mounted for scheduler", "data/enriched"),
        ("ct-collector defined", "ct-collector"),
    ]
    for label, pattern in checks:
        if not _check(label, pattern in compose):
            fails += 1

    # Tailscale — check if active or still commented out
    tailscale_active = "tailscale:" in compose and not all(
        l.strip().startswith("#") for l in compose.splitlines() if "tailscale" in l.lower()
    )
    _check("Tailscale active (not commented)", tailscale_active)
    if not tailscale_active:
        print("    ^ Tailscale is commented out — remote console access unavailable")

    return fails


def audit_scripts() -> int:
    """Check operational scripts exist."""
    print("\n  OPERATIONAL SCRIPTS")
    scripts_dir = PROJECT_ROOT / "scripts"
    expected = [
        ("export_results.py", "Export worker results to CSV + briefs"),
        ("analyze_pipeline.py", "Pipeline output analysis"),
        ("pi5-aliases.sh", "Pi5 command shortcuts"),
        ("audit.py", "This audit script"),
        ("benchmark.py", "Performance benchmarking"),
        ("validate_pi5.sh", "Pi5 deployment validation"),
    ]
    fails = 0
    for name, desc in expected:
        if not _check(f"{name} — {desc}", (scripts_dir / name).is_file()):
            fails += 1
    return fails


def audit_tests() -> int:
    """Check test coverage for critical modules."""
    print("\n  TEST COVERAGE")
    test_dir = PROJECT_ROOT / "tests"
    twin_test_dir = PROJECT_ROOT / "tools" / "twin" / "tests"
    existing = set()
    for d in [test_dir, twin_test_dir]:
        if d.is_dir():
            existing.update(f.stem for f in d.glob("test_*.py"))

    expected = [
        "test_scanner",
        "test_worker",
        "test_console",
        "test_api",
        "test_interpreter",
        "test_composer",
        "test_consent",
        "test_delta_detection",
        "test_remediation_tracker",
        "test_client_memory_profile",
        "test_client_memory_history",
        "test_client_memory_integration",
        "test_twin_regression",
        "test_synthetic_targets",
        "test_level1_scanners",
        "test_cvr_enrichment",
        "test_twin",
        "test_docker_smoke",
        "test_export_results",
    ]
    fails = 0
    for name in expected:
        if not _check(name, name in existing):
            fails += 1
    return fails


def audit_config() -> int:
    """Check config files exist and are valid JSON."""
    print("\n  CONFIG FILES")
    config_dir = PROJECT_ROOT / "config"
    expected = [
        "filters.json",
        "industry_codes.json",
        "consent_schema.json",
        "remediation_states.json",
        "synthetic_targets.json",
        "interpreter.json",
        "buckets.json",
        "cms_keywords.json",
        "hosting_providers.json",
    ]
    fails = 0
    for name in expected:
        path = config_dir / name
        if not path.is_file():
            _check(name, False)
            fails += 1
            continue
        try:
            import json
            json.loads(path.read_text())
            _check(name, True)
        except Exception:
            print(f"  [INVALID] {name} — not valid JSON")
            fails += 1
    return fails


def audit_backlog() -> int:
    """Check for known unresolved items."""
    print("\n  KNOWN GAPS (from backlog + this session)")
    gaps = [
        ("Tailscale VPN for remote console access", "BACKLOG (Sprint 4)"),
        ("Remote monitoring from phone", "BACKLOG (Sprint 4, depends on Tailscale)"),
        ("Twin Nuclei templates don't match simplified twin responses", "DESIGN LIMITATION"),
        ("WPVulnerability cache — verify vulndb findings appear in briefs on Pi5", "PENDING VERIFICATION"),
    ]
    for desc, status in gaps:
        marker = "OK" if "FIXED" in status else "TODO"
        print(f"  [{marker}] {desc} — {status}")
    return 0


def main():
    print("=" * 60)
    print("  HEIMDALL PROJECT AUDIT")
    print("=" * 60)

    total_fails = 0
    total_fails += audit_dockerfile()
    total_fails += audit_dockerignore()
    total_fails += audit_compose()
    total_fails += audit_scripts()
    total_fails += audit_tests()
    total_fails += audit_config()
    audit_backlog()

    print(f"\n{'=' * 60}")
    if total_fails == 0:
        print("  ALL CHECKS PASSED")
    else:
        print(f"  {total_fails} ISSUE(S) FOUND")
    print("=" * 60)


if __name__ == "__main__":
    main()
