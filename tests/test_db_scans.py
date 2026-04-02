"""Tests for src.db.scans — pipeline runs, scan history, brief snapshots."""

from __future__ import annotations

import json
import logging
import sqlite3
import time

import pytest

from src.db.connection import init_db
from src.db.scans import (
    complete_pipeline_run,
    complete_scan_entry,
    create_pipeline_run,
    create_scan_entry,
    get_latest_brief,
    get_latest_scan,
    get_scan_history,
    save_brief_snapshot,
)

log = logging.getLogger(__name__)


@pytest.fixture()
def db(tmp_path):
    """Initialised client database connection."""
    conn = init_db(tmp_path / "test.db")
    yield conn
    conn.close()


# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

SAMPLE_BRIEF = {
    "domain": "example.dk",
    "bucket": "A",
    "technology": {
        "cms": "WordPress",
        "hosting": "LiteSpeed",
        "server": "LiteSpeed/6.0",
        "ssl": {"valid": True, "issuer": "Let's Encrypt", "days_remaining": 45},
        "detected_plugins": ["yoast-seo", "woocommerce"],
        "detected_themes": ["flavor"],
    },
    "findings": [
        {"severity": "critical", "description": "test1"},
        {"severity": "high", "description": "test2"},
        {"severity": "medium", "description": "test3"},
    ],
    "subdomains": {"count": 5},
    "scan_date": "2026-04-02",
}


# ---------------------------------------------------------------------------
# Pipeline run tests
# ---------------------------------------------------------------------------


def test_create_pipeline_run(db):
    """Create a pipeline run and verify fields + started_at set."""
    row = create_pipeline_run(db, "run-001", "2026-04-02", '{"test": true}')

    assert row["run_id"] == "run-001"
    assert row["run_date"] == "2026-04-02"
    assert row["status"] == "running"
    assert row["started_at"] is not None
    assert row["completed_at"] is None
    assert row["config_json"] == '{"test": true}'
    assert row["domain_count"] == 0


def test_complete_pipeline_run(db):
    """Create + complete a pipeline run, verify completed_at + rollup fields."""
    create_pipeline_run(db, "run-002", "2026-04-02")

    complete_pipeline_run(
        db, "run-002", status="completed",
        domain_count=50, success_count=48, error_count=2,
        finding_count=120,
        critical_count=5, high_count=15, medium_count=30,
        low_count=40, info_count=30,
        bucket_a_count=10, bucket_b_count=20,
        bucket_c_count=8, bucket_d_count=7, bucket_e_count=5,
        total_duration_ms=300_000, avg_domain_ms=6000,
    )

    row = db.execute(
        "SELECT * FROM pipeline_runs WHERE run_id = ?", ("run-002",)
    ).fetchone()

    assert row["status"] == "completed"
    assert row["completed_at"] is not None
    assert row["domain_count"] == 50
    assert row["success_count"] == 48
    assert row["error_count"] == 2
    assert row["finding_count"] == 120
    assert row["critical_count"] == 5
    assert row["high_count"] == 15
    assert row["medium_count"] == 30
    assert row["low_count"] == 40
    assert row["info_count"] == 30
    assert row["bucket_a_count"] == 10
    assert row["bucket_b_count"] == 20
    assert row["bucket_c_count"] == 8
    assert row["bucket_d_count"] == 7
    assert row["bucket_e_count"] == 5
    assert row["total_duration_ms"] == 300_000
    assert row["avg_domain_ms"] == 6000


# ---------------------------------------------------------------------------
# Scan history tests
# ---------------------------------------------------------------------------


def test_create_and_complete_scan_entry(db):
    """Full scan entry lifecycle: create then complete."""
    row = create_scan_entry(
        db, "scan-001", "example.dk", "2026-04-02",
        run_id=None, cvr="12345678",
    )

    assert row["scan_id"] == "scan-001"
    assert row["domain"] == "example.dk"
    assert row["scan_date"] == "2026-04-02"
    assert row["status"] == "completed"  # default
    assert row["created_at"] is not None

    complete_scan_entry(
        db, "scan-001", status="completed",
        total_ms=1500, timing_json='{"httpx": 500}',
        cache_hits=3, cache_misses=7,
        result_json='{"raw": "data"}',
    )

    updated = db.execute(
        "SELECT * FROM scan_history WHERE scan_id = ?", ("scan-001",)
    ).fetchone()

    assert updated["status"] == "completed"
    assert updated["total_ms"] == 1500
    assert updated["cache_hits"] == 3
    assert updated["cache_misses"] == 7
    assert updated["result_json"] == '{"raw": "data"}'
    assert updated["error_message"] is None


def test_get_scan_history(db):
    """Create 3 scans, verify ordered by date DESC and limit works."""
    for i, dt in enumerate(["2026-04-01", "2026-04-02", "2026-04-03"]):
        create_scan_entry(db, f"scan-{i}", "example.dk", dt)

    history = get_scan_history(db, "example.dk")
    assert len(history) == 3
    assert history[0]["scan_date"] == "2026-04-03"
    assert history[1]["scan_date"] == "2026-04-02"
    assert history[2]["scan_date"] == "2026-04-01"

    # Test limit
    limited = get_scan_history(db, "example.dk", limit=2)
    assert len(limited) == 2
    assert limited[0]["scan_date"] == "2026-04-03"


def test_get_latest_scan(db):
    """Returns the most recent scan for a domain."""
    create_scan_entry(db, "scan-old", "example.dk", "2026-03-01")
    create_scan_entry(db, "scan-new", "example.dk", "2026-04-02")

    latest = get_latest_scan(db, "example.dk")
    assert latest is not None
    assert latest["scan_id"] == "scan-new"

    # Non-existent domain returns None
    assert get_latest_scan(db, "nonexistent.dk") is None


# ---------------------------------------------------------------------------
# Brief snapshot tests
# ---------------------------------------------------------------------------


def test_save_brief_snapshot_extracts_fields(db):
    """Save a realistic brief dict, verify extracted fields."""
    save_brief_snapshot(
        db, "example.dk", "2026-04-02", SAMPLE_BRIEF,
        scan_id="scan-001", run_id="run-001",
        company_name="Example ApS", cvr="12345678",
    )

    row = get_latest_brief(db, "example.dk")
    assert row is not None

    # Identity
    assert row["domain"] == "example.dk"
    assert row["scan_date"] == "2026-04-02"
    assert row["scan_id"] == "scan-001"
    assert row["run_id"] == "run-001"
    assert row["company_name"] == "Example ApS"
    assert row["cvr"] == "12345678"

    # Extracted fields
    assert row["bucket"] == "A"
    assert row["cms"] == "WordPress"
    assert row["hosting"] == "LiteSpeed"
    assert row["server"] == "LiteSpeed/6.0"

    # Finding counts
    assert row["finding_count"] == 3
    assert row["critical_count"] == 1
    assert row["high_count"] == 1
    assert row["medium_count"] == 1
    assert row["low_count"] == 0
    assert row["info_count"] == 0

    # Technology counts
    assert row["plugin_count"] == 2
    assert row["theme_count"] == 1
    assert row["subdomain_count"] == 5

    # SSL fields
    assert row["ssl_valid"] == 1
    assert row["ssl_issuer"] == "Let's Encrypt"
    assert row["ssl_days_remaining"] == 45

    # Twin scan
    assert row["has_twin_scan"] == 0
    assert row["twin_finding_count"] == 0

    # Full JSON stored
    stored = json.loads(row["brief_json"])
    assert stored["domain"] == "example.dk"
    assert stored["bucket"] == "A"

    # created_at set
    assert row["created_at"] is not None


def test_brief_snapshot_unique_constraint(db):
    """Same (domain, scan_date) twice raises IntegrityError."""
    save_brief_snapshot(db, "example.dk", "2026-04-02", SAMPLE_BRIEF)

    with pytest.raises(sqlite3.IntegrityError):
        save_brief_snapshot(db, "example.dk", "2026-04-02", SAMPLE_BRIEF)


def test_get_latest_brief(db):
    """Returns most recent snapshot for a domain."""
    brief_old = {**SAMPLE_BRIEF, "bucket": "C"}
    brief_new = {**SAMPLE_BRIEF, "bucket": "A"}

    save_brief_snapshot(db, "example.dk", "2026-03-01", brief_old)
    save_brief_snapshot(db, "example.dk", "2026-04-02", brief_new)

    latest = get_latest_brief(db, "example.dk")
    assert latest is not None
    assert latest["scan_date"] == "2026-04-02"
    assert latest["bucket"] == "A"

    # Non-existent domain returns None
    assert get_latest_brief(db, "nonexistent.dk") is None


def test_brief_snapshot_benchmark(db):
    """Insert 100 brief snapshots, log timing."""
    base_brief = {
        "domain": "bench.dk",
        "bucket": "B",
        "technology": {
            "cms": "WordPress",
            "hosting": "Apache",
            "server": "Apache/2.4",
            "ssl": {"valid": True, "issuer": "DigiCert", "days_remaining": 90},
            "detected_plugins": ["cf7"],
            "detected_themes": ["flavor"],
        },
        "findings": [
            {"severity": "medium", "description": f"finding-{i}"}
            for i in range(5)
        ],
        "subdomains": {"count": 2},
    }

    start = time.perf_counter()
    for i in range(100):
        domain = f"bench-{i:04d}.dk"
        save_brief_snapshot(db, domain, "2026-04-02", base_brief)
    elapsed_ms = (time.perf_counter() - start) * 1000

    log.info("100 brief snapshots inserted in %.1f ms (%.2f ms/insert)", elapsed_ms, elapsed_ms / 100)

    count = db.execute("SELECT COUNT(*) FROM brief_snapshots").fetchone()[0]
    assert count == 100
