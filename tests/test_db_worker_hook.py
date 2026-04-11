"""Tests for the worker DB hook (src.db.worker_hook)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.db.connection import init_db
from src.db.worker_hook import save_scan_to_db

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db(tmp_path: Path):
    """In-memory-like temp DB with schema applied and a test client inserted."""
    conn = init_db(str(tmp_path / "test.db"))
    conn.execute(
        "INSERT INTO clients (cvr, company_name, created_at, updated_at) "
        "VALUES (?, ?, ?, ?)",
        ("12345678", "Test Restaurant", "2026-01-01", "2026-01-01"),
    )
    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

SAMPLE_JOB: dict = {
    "job_id": "job-001",
    "domain": "test.dk",
    "client_id": "12345678",
}

SAMPLE_RESULT: dict = {
    "domain": "test.dk",
    "status": "completed",
    "brief": {
        "domain": "test.dk",
        "bucket": "A",
        "company_name": "Test Restaurant",
        "scan_date": "2026-04-02",
        "technology": {
            "cms": "WordPress",
            "hosting": "LiteSpeed",
            "server": "Apache",
            "ssl": {"valid": True, "issuer": "Let's Encrypt", "days_remaining": 90},
            "detected_plugins": ["yoast-seo"],
            "detected_themes": [],
        },
        "findings": [
            {"severity": "high", "description": "Missing HSTS header", "risk": "MitM risk"},
            {"severity": "medium", "description": "Missing CSP header"},
        ],
        "subdomains": {"count": 3},
    },
    "timing": {"total_ms": 1500, "httpx": 800, "dns": 200},
    "cache_stats": {"hits": 2, "misses": 5},
    "scan_result": {"domain": "test.dk", "cms": "WordPress"},
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSaveScanCreatesScanEntry:
    """Verify scan_history receives a row for the scanned domain."""

    def test_save_scan_creates_scan_entry(self, db) -> None:
        save_scan_to_db(db, SAMPLE_JOB, SAMPLE_RESULT)

        row = db.execute(
            "SELECT * FROM scan_history WHERE domain = ?", ("test.dk",)
        ).fetchone()
        assert row is not None
        entry = dict(row)
        assert entry["domain"] == "test.dk"
        assert entry["status"] == "completed"
        assert entry["cvr"] == "12345678"
        assert entry["total_ms"] == 1500
        assert entry["cache_hits"] == 2
        assert entry["cache_misses"] == 5
        assert entry["result_json"] is not None
        parsed = json.loads(entry["result_json"])
        assert parsed["domain"] == "test.dk"


class TestSaveScanCreatesBriefSnapshot:
    """Verify brief_snapshots receives a row with correct extracted fields."""

    def test_save_scan_creates_brief_snapshot(self, db) -> None:
        save_scan_to_db(db, SAMPLE_JOB, SAMPLE_RESULT)

        row = db.execute(
            "SELECT * FROM brief_snapshots WHERE domain = ?", ("test.dk",)
        ).fetchone()
        assert row is not None
        snap = dict(row)
        assert snap["bucket"] == "A"
        assert snap["cms"] == "WordPress"
        assert snap["hosting"] == "LiteSpeed"
        assert snap["server"] == "Apache"
        assert snap["finding_count"] == 2
        assert snap["high_count"] == 1
        assert snap["medium_count"] == 1
        assert snap["plugin_count"] == 1
        assert snap["subdomain_count"] == 3
        assert snap["ssl_valid"] == 1
        assert snap["ssl_issuer"] == "Let's Encrypt"
        assert snap["ssl_days_remaining"] == 90
        assert snap["company_name"] == "Test Restaurant"
        assert snap["cvr"] == "12345678"
        # brief_json is the full archive
        assert snap["brief_json"] is not None
        parsed_brief = json.loads(snap["brief_json"])
        assert parsed_brief["bucket"] == "A"


class TestSaveScanRunsDelta:
    """Verify finding_occurrences are created for each finding via delta detection."""

    def test_save_scan_runs_delta(self, db) -> None:
        save_scan_to_db(db, SAMPLE_JOB, SAMPLE_RESULT)

        occurrences = db.execute(
            "SELECT * FROM finding_occurrences WHERE domain = ?", ("test.dk",)
        ).fetchall()
        # Two findings in the brief -> two occurrences
        assert len(occurrences) == 2

        # Verify finding_definitions were also created
        definitions = db.execute("SELECT * FROM finding_definitions").fetchall()
        assert len(definitions) == 2

        # Verify status log entries exist
        log_entries = db.execute("SELECT * FROM finding_status_log").fetchall()
        assert len(log_entries) >= 2  # at least one 'open' transition per finding


class TestSaveScanWithoutCvr:
    """Job without client_id -- scan and brief saved, but no delta detection."""

    def test_save_scan_without_cvr(self, db) -> None:
        job_no_cvr = {
            "job_id": "job-002",
            "domain": "nocvr.dk",
        }
        save_scan_to_db(db, job_no_cvr, SAMPLE_RESULT)

        # scan_history should have a row
        scan_row = db.execute(
            "SELECT * FROM scan_history WHERE domain = ?", ("nocvr.dk",)
        ).fetchone()
        assert scan_row is not None
        assert dict(scan_row)["cvr"] is None

        # brief_snapshots should have a row
        brief_row = db.execute(
            "SELECT * FROM brief_snapshots WHERE domain = ?", ("nocvr.dk",)
        ).fetchone()
        assert brief_row is not None

        # No delta -> no finding_occurrences for this domain
        occurrences = db.execute(
            "SELECT * FROM finding_occurrences WHERE domain = ?", ("nocvr.dk",)
        ).fetchall()
        assert len(occurrences) == 0


class TestSaveScanWithoutBrief:
    """Result with empty brief -- scan entry still created, no brief snapshot."""

    def test_save_scan_without_brief(self, db) -> None:
        result_no_brief = {
            "domain": "nobrief.dk",
            "status": "skipped",
            "brief": {},
            "timing": {"total_ms": 200},
            "cache_stats": {"hits": 0, "misses": 0},
            "scan_result": None,
        }
        save_scan_to_db(db, SAMPLE_JOB, result_no_brief)

        # scan_history should have a row with status=skipped
        scan_row = db.execute(
            "SELECT * FROM scan_history WHERE domain = ?", ("test.dk",)
        ).fetchone()
        assert scan_row is not None
        assert dict(scan_row)["status"] == "skipped"

        # brief_snapshots should NOT have a row (brief was empty)
        brief_row = db.execute(
            "SELECT * FROM brief_snapshots WHERE domain = ?", ("test.dk",)
        ).fetchone()
        assert brief_row is None


class TestSaveScanExceptionSafe:
    """The hook itself propagates exceptions; the worker wraps in try/except."""

    def test_save_scan_exception_on_closed_connection(self, db) -> None:
        db.close()
        with pytest.raises(Exception):
            save_scan_to_db(db, SAMPLE_JOB, SAMPLE_RESULT)


class TestWorkerHookPointExists:
    """Integration check: verify the hook call site exists in main.py."""

    def test_worker_hook_point_exists(self) -> None:
        main_path = Path(__file__).resolve().parent.parent / "src" / "worker" / "main.py"
        source = main_path.read_text(encoding="utf-8")
        assert "Save to client database" in source
        assert "save_scan_to_db" in source
        assert "db_hook_error" in source
