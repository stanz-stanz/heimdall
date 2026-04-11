"""Tests for DB-backed client history -- delta detection via SQLite.

Mirrors test_client_memory_history.py patterns but verifies that
findings are persisted in the normalised finding_definitions +
finding_occurrences tables, with audit trail in finding_status_log.
"""

from __future__ import annotations

import sqlite3

import pytest

from src.client_memory.delta import DeltaDetector
from src.client_memory.models import FindingRecord
from src.db.client_history import DBClientHistory
from src.db.connection import _now, init_db
from src.db.findings import (
    get_definition,
    get_status_log,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def db(tmp_path) -> sqlite3.Connection:
    """Create a fresh test database with full schema applied."""
    conn = init_db(tmp_path / "test.db")
    # Insert a test client so FK constraints pass
    now = _now()
    conn.execute(
        "INSERT INTO clients (cvr, company_name, created_at, updated_at) "
        "VALUES (?, ?, ?, ?)",
        ("12345678", "Test Restaurant ApS", now, now),
    )
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture()
def history(db: sqlite3.Connection) -> DBClientHistory:
    """DBClientHistory wired to the test database."""
    return DBClientHistory(db, DeltaDetector())


@pytest.fixture()
def sample_brief() -> dict:
    """First scan: three findings."""
    return {
        "domain": "example.dk",
        "findings": [
            {"severity": "high", "description": "Missing HSTS header", "risk": "MitM risk"},
            {"severity": "medium", "description": "Missing CSP header"},
            {"severity": "info", "description": "Server version disclosed"},
        ],
    }


@pytest.fixture()
def sample_brief_v2() -> dict:
    """Second scan: 2 recurring + 1 new (Missing CSP removed -> resolved)."""
    return {
        "domain": "example.dk",
        "findings": [
            {"severity": "high", "description": "Missing HSTS header", "risk": "MitM risk"},
            {"severity": "info", "description": "Server version disclosed"},
            {"severity": "high", "description": "SSL certificate expired", "risk": "Visitors blocked"},
        ],
    }


# ---------------------------------------------------------------------------
# First scan -- all new
# ---------------------------------------------------------------------------


class TestFirstScanAllNew:
    """First scan should classify all findings as NEW."""

    def test_first_scan_all_new(
        self, history: DBClientHistory, sample_brief: dict,
    ) -> None:
        """Three findings on first scan -> all classified as new."""
        delta = history.record_scan("12345678", "example.dk", sample_brief, scan_id="scan-001")

        assert len(delta.new) == 3
        assert len(delta.recurring) == 0
        assert len(delta.resolved) == 0


# ---------------------------------------------------------------------------
# Second scan -- delta detection
# ---------------------------------------------------------------------------


class TestSecondScanDelta:
    """Second scan with changes should detect new, recurring, and resolved."""

    def test_second_scan_delta(
        self,
        history: DBClientHistory,
        sample_brief: dict,
        sample_brief_v2: dict,
    ) -> None:
        """Record 3 findings, then 2 same + 1 new. Expect 1 new, 2 recurring, 1 resolved."""
        history.record_scan("12345678", "example.dk", sample_brief, scan_id="scan-001")
        delta = history.record_scan("12345678", "example.dk", sample_brief_v2, scan_id="scan-002")

        assert len(delta.new) == 1  # SSL certificate expired
        assert len(delta.recurring) == 2  # HSTS + Server version
        assert len(delta.resolved) == 1  # Missing CSP header


# ---------------------------------------------------------------------------
# DB persistence
# ---------------------------------------------------------------------------


class TestFindingsPersistedInDB:
    """Verify that findings are written to finding_definitions and finding_occurrences."""

    def test_findings_persisted_in_db(
        self,
        db: sqlite3.Connection,
        history: DBClientHistory,
        sample_brief: dict,
    ) -> None:
        """After record_scan, finding_definitions and finding_occurrences have correct rows."""
        history.record_scan("12345678", "example.dk", sample_brief, scan_id="scan-001")

        # Check definitions
        defs = db.execute("SELECT * FROM finding_definitions").fetchall()
        assert len(defs) == 3

        # Check occurrences
        occs = db.execute("SELECT * FROM finding_occurrences").fetchall()
        assert len(occs) == 3
        assert all(dict(o)["status"] == "open" for o in occs)
        assert all(dict(o)["domain"] == "example.dk" for o in occs)
        assert all(dict(o)["cvr"] == "12345678" for o in occs)

    def test_definitions_have_correct_data(
        self,
        db: sqlite3.Connection,
        history: DBClientHistory,
        sample_brief: dict,
    ) -> None:
        """Definition rows contain severity, description, and risk from the brief."""
        history.record_scan("12345678", "example.dk", sample_brief, scan_id="scan-001")

        # Generate the expected hash for the HSTS finding
        detector = DeltaDetector()
        hsts_hash = detector.generate_finding_id("high", "Missing HSTS header")

        defn = get_definition(db, hsts_hash)
        assert defn is not None
        assert defn["severity"] == "high"
        assert defn["description"] == "Missing HSTS header"
        assert defn["risk"] == "MitM risk"


# ---------------------------------------------------------------------------
# Status log
# ---------------------------------------------------------------------------


class TestStatusLogCreatedForNew:
    """New findings should get a NULL -> open log entry."""

    def test_status_log_created_for_new(
        self,
        db: sqlite3.Connection,
        history: DBClientHistory,
        sample_brief: dict,
    ) -> None:
        """Each new finding gets a status log entry: NULL -> open."""
        history.record_scan("12345678", "example.dk", sample_brief, scan_id="scan-001")

        occs = db.execute("SELECT id FROM finding_occurrences").fetchall()
        for occ in occs:
            log_entries = get_status_log(db, occ["id"])
            assert len(log_entries) == 1
            assert log_entries[0]["from_status"] is None
            assert log_entries[0]["to_status"] == "open"
            assert "scan:scan-001" in log_entries[0]["source"]


class TestStatusLogCreatedForResolved:
    """Resolved findings should get an open -> resolved log entry."""

    def test_status_log_created_for_resolved(
        self,
        db: sqlite3.Connection,
        history: DBClientHistory,
        sample_brief: dict,
        sample_brief_v2: dict,
    ) -> None:
        """Resolving a finding writes an open -> resolved transition to the log."""
        history.record_scan("12345678", "example.dk", sample_brief, scan_id="scan-001")
        history.record_scan("12345678", "example.dk", sample_brief_v2, scan_id="scan-002")

        # Find the resolved occurrence (Missing CSP header)
        resolved_occ = db.execute(
            "SELECT id FROM finding_occurrences WHERE status = 'resolved'",
        ).fetchone()
        assert resolved_occ is not None

        log_entries = get_status_log(db, resolved_occ["id"])
        # Should have 2 entries: NULL->open (scan-001), open->resolved (scan-002)
        assert len(log_entries) == 2
        assert log_entries[0]["to_status"] == "open"
        assert log_entries[1]["from_status"] == "open"
        assert log_entries[1]["to_status"] == "resolved"
        assert "scan:scan-002" in log_entries[1]["source"]


# ---------------------------------------------------------------------------
# get_open_findings
# ---------------------------------------------------------------------------


class TestGetOpenFindings:
    """get_open_findings returns only non-resolved findings as FindingRecord."""

    def test_get_open_findings(
        self,
        history: DBClientHistory,
        sample_brief: dict,
        sample_brief_v2: dict,
    ) -> None:
        """After second scan, only non-resolved findings are returned."""
        history.record_scan("12345678", "example.dk", sample_brief, scan_id="scan-001")
        history.record_scan("12345678", "example.dk", sample_brief_v2, scan_id="scan-002")

        open_findings = history.get_open_findings("example.dk")
        assert len(open_findings) == 3  # HSTS + Server version + SSL expired

        # All returned as FindingRecord instances
        assert all(isinstance(f, FindingRecord) for f in open_findings)

        # None are resolved
        assert all(f.status != "resolved" for f in open_findings)

        # All have _occurrence_id set
        assert all(f._occurrence_id is not None for f in open_findings)

    def test_get_open_findings_empty_domain(
        self, history: DBClientHistory,
    ) -> None:
        """Domain with no findings returns empty list."""
        result = history.get_open_findings("nonexistent.dk")
        assert result == []


# ---------------------------------------------------------------------------
# get_stale_findings
# ---------------------------------------------------------------------------


class TestGetStaleFindings:
    """Stale findings are those open longer than threshold days."""

    def test_get_stale_findings_none_stale(
        self, history: DBClientHistory, sample_brief: dict,
    ) -> None:
        """Freshly created findings are not stale."""
        history.record_scan("12345678", "example.dk", sample_brief, scan_id="scan-001")
        stale = history.get_stale_findings("example.dk", days=14)
        assert len(stale) == 0

    def test_get_stale_findings_old_dates(
        self,
        db: sqlite3.Connection,
        history: DBClientHistory,
    ) -> None:
        """Findings with old first_seen_at are detected as stale."""
        # Insert a finding with first_seen_at 30 days ago
        from src.db.findings import upsert_definition, upsert_occurrence

        old_date = "2026-03-01"
        upsert_definition(
            db,
            finding_hash="stale001",
            severity="high",
            description="Old finding",
            risk="test",
            first_seen_at=old_date,
        )
        upsert_occurrence(
            db,
            cvr="12345678",
            domain="stale.dk",
            finding_hash="stale001",
            status="open",
            first_seen_at=old_date,
            last_seen_at=old_date,
        )

        stale = history.get_stale_findings("stale.dk", days=14)
        assert len(stale) == 1
        assert stale[0].finding_id == "stale001"


# ---------------------------------------------------------------------------
# scan_count bump
# ---------------------------------------------------------------------------


class TestScanCountBumped:
    """Recurring findings should have scan_count incremented."""

    def test_scan_count_bumped(
        self,
        db: sqlite3.Connection,
        history: DBClientHistory,
        sample_brief: dict,
        sample_brief_v2: dict,
    ) -> None:
        """After two scans, a recurring finding has scan_count=2."""
        history.record_scan("12345678", "example.dk", sample_brief, scan_id="scan-001")
        history.record_scan("12345678", "example.dk", sample_brief_v2, scan_id="scan-002")

        # HSTS header is present in both scans
        detector = DeltaDetector()
        hsts_hash = detector.generate_finding_id("high", "Missing HSTS header")

        row = db.execute(
            "SELECT scan_count FROM finding_occurrences "
            "WHERE domain = ? AND finding_hash = ?",
            ("example.dk", hsts_hash),
        ).fetchone()

        assert row is not None
        assert row["scan_count"] == 2
