"""Tests for src.db.findings — definitions, occurrences, and status log CRUD."""

from __future__ import annotations

import sqlite3
import time

import pytest

from src.db.connection import _now, init_db
from src.db.findings import (
    get_definition,
    get_occurrences_by_cvr,
    get_open_occurrences,
    get_status_log,
    log_status_transition,
    resolve_occurrence,
    update_occurrence_status,
    upsert_definition,
    upsert_occurrence,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def db(tmp_path: object) -> sqlite3.Connection:
    """Create a fresh test database with full schema applied."""
    conn = init_db(tmp_path / "test.db")  # type: ignore[arg-type]
    yield conn
    conn.close()


def _insert_client(conn: sqlite3.Connection, cvr: str = "12345678") -> None:
    """Helper: insert a minimal client row so FK constraints pass."""
    now = _now()
    conn.execute(
        "INSERT OR IGNORE INTO clients (cvr, company_name, created_at, updated_at) "
        "VALUES (?, ?, ?, ?)",
        (cvr, f"Test Company {cvr}", now, now),
    )
    conn.commit()


def _insert_test_definition(
    conn: sqlite3.Connection,
    finding_hash: str = "abc123",
    severity: str = "high",
    description: str = "Missing HSTS header",
) -> None:
    """Helper: insert a finding definition for occurrence tests."""
    upsert_definition(
        conn,
        finding_hash=finding_hash,
        severity=severity,
        description=description,
        risk="Allows protocol downgrade attacks",
        category="missing_header",
        first_seen_at="2026-04-01T00:00:00Z",
    )


# ---------------------------------------------------------------------------
# Finding definitions
# ---------------------------------------------------------------------------


class TestUpsertDefinition:
    """Tests for upsert_definition."""

    def test_upsert_definition_insert(self, db: sqlite3.Connection) -> None:
        """Insert a new definition, verify all fields are stored correctly."""
        upsert_definition(
            db,
            finding_hash="abc123",
            severity="high",
            description="Missing HSTS header",
            risk="Allows protocol downgrade attacks",
            cve_id=None,
            plugin_slug=None,
            provenance=None,
            category="missing_header",
            first_seen_at="2026-04-01T00:00:00Z",
        )

        row = get_definition(db, "abc123")
        assert row is not None
        assert row["finding_hash"] == "abc123"
        assert row["severity"] == "high"
        assert row["description"] == "Missing HSTS header"
        assert row["risk"] == "Allows protocol downgrade attacks"
        assert row["cve_id"] is None
        assert row["plugin_slug"] is None
        assert row["provenance"] is None
        assert row["category"] == "missing_header"
        assert row["first_seen_at"] == "2026-04-01T00:00:00Z"

    def test_upsert_definition_idempotent(self, db: sqlite3.Connection) -> None:
        """Inserting the same hash twice is a no-op: no error, data unchanged."""
        upsert_definition(
            db,
            finding_hash="abc123",
            severity="high",
            description="Missing HSTS header",
            risk="Original risk text",
            first_seen_at="2026-04-01T00:00:00Z",
        )
        # Second insert with different risk text — should be ignored
        upsert_definition(
            db,
            finding_hash="abc123",
            severity="critical",
            description="Changed description",
            risk="Changed risk text",
            first_seen_at="2026-04-02T00:00:00Z",
        )

        row = get_definition(db, "abc123")
        assert row is not None
        assert row["severity"] == "high", "Original severity must be preserved"
        assert row["description"] == "Missing HSTS header"
        assert row["risk"] == "Original risk text"
        assert row["first_seen_at"] == "2026-04-01T00:00:00Z"

    def test_get_definition_not_found(self, db: sqlite3.Connection) -> None:
        """Querying a nonexistent hash returns None."""
        result = get_definition(db, "nonexistent")
        assert result is None

    def test_upsert_definition_with_cve(self, db: sqlite3.Connection) -> None:
        """Definition with CVE and plugin_slug stores all optional fields."""
        upsert_definition(
            db,
            finding_hash="cve001",
            severity="critical",
            description="LiteSpeed Cache Auth Bypass",
            risk="Unauthenticated admin access",
            cve_id="CVE-2024-28000",
            plugin_slug="litespeed-cache",
            provenance="twin-derived",
            category="cve",
            first_seen_at="2026-04-01T00:00:00Z",
        )

        row = get_definition(db, "cve001")
        assert row is not None
        assert row["cve_id"] == "CVE-2024-28000"
        assert row["plugin_slug"] == "litespeed-cache"
        assert row["provenance"] == "twin-derived"
        assert row["category"] == "cve"


# ---------------------------------------------------------------------------
# Finding occurrences
# ---------------------------------------------------------------------------


class TestUpsertOccurrence:
    """Tests for upsert_occurrence."""

    def test_upsert_occurrence_new(self, db: sqlite3.Connection) -> None:
        """Insert a new occurrence, verify id returned and scan_count=1."""
        _insert_client(db)
        _insert_test_definition(db)

        occ_id = upsert_occurrence(
            db,
            cvr="12345678",
            domain="example.dk",
            finding_hash="abc123",
            confidence="confirmed",
            first_seen_at="2026-04-01T00:00:00Z",
            last_seen_at="2026-04-01T00:00:00Z",
            first_scan_id="scan-001",
            last_scan_id="scan-001",
        )

        assert isinstance(occ_id, int)
        assert occ_id > 0

        row = db.execute(
            "SELECT * FROM finding_occurrences WHERE id = ?", (occ_id,)
        ).fetchone()
        assert row["scan_count"] == 1
        assert row["cvr"] == "12345678"
        assert row["domain"] == "example.dk"
        assert row["finding_hash"] == "abc123"
        assert row["confidence"] == "confirmed"
        assert row["status"] == "open"
        assert row["first_scan_id"] == "scan-001"
        assert row["last_scan_id"] == "scan-001"

    def test_upsert_occurrence_bump(self, db: sqlite3.Connection) -> None:
        """Re-inserting same (domain, finding_hash) bumps scan_count and last_seen_at."""
        _insert_client(db)
        _insert_test_definition(db)

        occ_id_1 = upsert_occurrence(
            db,
            cvr="12345678",
            domain="example.dk",
            finding_hash="abc123",
            first_seen_at="2026-04-01T00:00:00Z",
            last_seen_at="2026-04-01T00:00:00Z",
            first_scan_id="scan-001",
            last_scan_id="scan-001",
        )

        occ_id_2 = upsert_occurrence(
            db,
            cvr="12345678",
            domain="example.dk",
            finding_hash="abc123",
            last_seen_at="2026-04-02T00:00:00Z",
            last_scan_id="scan-002",
        )

        # Same occurrence row
        assert occ_id_1 == occ_id_2

        row = db.execute(
            "SELECT * FROM finding_occurrences WHERE id = ?", (occ_id_1,)
        ).fetchone()
        assert row["scan_count"] == 2
        assert row["last_seen_at"] == "2026-04-02T00:00:00Z"
        assert row["last_scan_id"] == "scan-002"
        # first_seen_at and first_scan_id must NOT change
        assert row["first_seen_at"] == "2026-04-01T00:00:00Z"
        assert row["first_scan_id"] == "scan-001"


class TestGetOccurrences:
    """Tests for get_open_occurrences and get_occurrences_by_cvr."""

    def test_get_open_occurrences(self, db: sqlite3.Connection) -> None:
        """Returns only non-resolved occurrences for the given domain."""
        _insert_client(db)
        _insert_test_definition(db, "h1", "high", "Finding 1")
        _insert_test_definition(db, "h2", "medium", "Finding 2")
        _insert_test_definition(db, "h3", "low", "Finding 3")

        occ1 = upsert_occurrence(db, "12345678", "example.dk", "h1")
        occ2 = upsert_occurrence(db, "12345678", "example.dk", "h2")
        occ3 = upsert_occurrence(db, "12345678", "example.dk", "h3")

        # Resolve one
        resolve_occurrence(db, occ3, resolved_at="2026-04-02T00:00:00Z")

        results = get_open_occurrences(db, "example.dk")
        assert len(results) == 2
        hashes = {r["finding_hash"] for r in results}
        assert hashes == {"h1", "h2"}

    def test_get_open_occurrences_joins_definition(
        self, db: sqlite3.Connection
    ) -> None:
        """Returned dicts include severity and description from definitions."""
        _insert_client(db)
        _insert_test_definition(db, "h1", "critical", "SQL injection in login form")

        upsert_occurrence(db, "12345678", "example.dk", "h1")

        results = get_open_occurrences(db, "example.dk")
        assert len(results) == 1
        row = results[0]
        assert row["severity"] == "critical"
        assert row["description"] == "SQL injection in login form"
        assert row["category"] == "missing_header"  # from _insert_test_definition

    def test_get_occurrences_by_cvr(self, db: sqlite3.Connection) -> None:
        """Filter occurrences by CVR, returning only the matching client's findings."""
        _insert_client(db, "11111111")
        _insert_client(db, "22222222")
        _insert_test_definition(db, "h1", "high", "Finding 1")
        _insert_test_definition(db, "h2", "medium", "Finding 2")

        upsert_occurrence(db, "11111111", "alpha.dk", "h1")
        upsert_occurrence(db, "11111111", "alpha.dk", "h2")
        upsert_occurrence(db, "22222222", "beta.dk", "h1")

        results_1 = get_occurrences_by_cvr(db, "11111111")
        results_2 = get_occurrences_by_cvr(db, "22222222")

        assert len(results_1) == 2
        assert len(results_2) == 1
        assert results_2[0]["domain"] == "beta.dk"

    def test_get_open_occurrences_empty(self, db: sqlite3.Connection) -> None:
        """Returns empty list for a domain with no occurrences."""
        results = get_open_occurrences(db, "nonexistent.dk")
        assert results == []


# ---------------------------------------------------------------------------
# Resolve + status updates
# ---------------------------------------------------------------------------


class TestStatusUpdates:
    """Tests for resolve_occurrence and update_occurrence_status."""

    def test_resolve_occurrence(self, db: sqlite3.Connection) -> None:
        """Resolving sets status='resolved' and resolved_at."""
        _insert_client(db)
        _insert_test_definition(db)

        occ_id = upsert_occurrence(db, "12345678", "example.dk", "abc123")
        resolve_occurrence(db, occ_id, "2026-04-02T12:00:00Z", scan_id="scan-005")

        row = db.execute(
            "SELECT * FROM finding_occurrences WHERE id = ?", (occ_id,)
        ).fetchone()
        assert row["status"] == "resolved"
        assert row["resolved_at"] == "2026-04-02T12:00:00Z"
        assert row["last_scan_id"] == "scan-005"

    def test_update_occurrence_status(self, db: sqlite3.Connection) -> None:
        """Status can be changed to acknowledged."""
        _insert_client(db)
        _insert_test_definition(db)

        occ_id = upsert_occurrence(db, "12345678", "example.dk", "abc123")
        update_occurrence_status(db, occ_id, "acknowledged")

        row = db.execute(
            "SELECT status FROM finding_occurrences WHERE id = ?", (occ_id,)
        ).fetchone()
        assert row["status"] == "acknowledged"


# ---------------------------------------------------------------------------
# Status log (audit trail)
# ---------------------------------------------------------------------------


class TestStatusLog:
    """Tests for log_status_transition and get_status_log."""

    def test_log_status_transition(self, db: sqlite3.Connection) -> None:
        """Log a single transition, verify it appears in get_status_log."""
        _insert_client(db)
        _insert_test_definition(db)
        occ_id = upsert_occurrence(db, "12345678", "example.dk", "abc123")

        log_status_transition(db, occ_id, None, "open", "scan")

        log = get_status_log(db, occ_id)
        assert len(log) == 1
        assert log[0]["occurrence_id"] == occ_id
        assert log[0]["from_status"] is None
        assert log[0]["to_status"] == "open"
        assert log[0]["source"] == "scan"
        assert log[0]["created_at"] is not None

    def test_status_log_ordered(self, db: sqlite3.Connection) -> None:
        """Multiple transitions are returned in chronological order."""
        _insert_client(db)
        _insert_test_definition(db)
        occ_id = upsert_occurrence(db, "12345678", "example.dk", "abc123")

        log_status_transition(db, occ_id, None, "open", "scan")
        # Tiny sleep to ensure distinct timestamps (sub-second resolution)
        time.sleep(0.01)
        log_status_transition(db, occ_id, "open", "acknowledged", "operator")
        time.sleep(0.01)
        log_status_transition(db, occ_id, "acknowledged", "in_progress", "client")

        log = get_status_log(db, occ_id)
        assert len(log) == 3
        assert log[0]["to_status"] == "open"
        assert log[1]["to_status"] == "acknowledged"
        assert log[2]["to_status"] == "in_progress"
        # Verify chronological order
        assert log[0]["created_at"] <= log[1]["created_at"]
        assert log[1]["created_at"] <= log[2]["created_at"]

    def test_status_log_empty(self, db: sqlite3.Connection) -> None:
        """No log entries for an occurrence that has none."""
        log = get_status_log(db, 99999)
        assert log == []


# ---------------------------------------------------------------------------
# v_findings view
# ---------------------------------------------------------------------------


class TestVFindingsView:
    """Tests for the v_findings denormalised view."""

    def test_v_findings_view(self, db: sqlite3.Connection) -> None:
        """Insert definition + occurrence, query v_findings, verify denormalized data."""
        _insert_client(db)
        upsert_definition(
            db,
            finding_hash="vf001",
            severity="critical",
            description="LiteSpeed Cache Auth Bypass",
            risk="Unauthenticated admin access",
            cve_id="CVE-2024-28000",
            plugin_slug="litespeed-cache",
            provenance="twin-derived",
            category="cve",
            first_seen_at="2026-04-01T00:00:00Z",
        )
        occ_id = upsert_occurrence(
            db,
            cvr="12345678",
            domain="shop.dk",
            finding_hash="vf001",
            confidence="confirmed",
            first_seen_at="2026-04-01T00:00:00Z",
            last_seen_at="2026-04-01T00:00:00Z",
            first_scan_id="scan-v01",
            last_scan_id="scan-v01",
        )

        row = db.execute(
            "SELECT * FROM v_findings WHERE id = ?", (occ_id,)
        ).fetchone()
        assert row is not None
        vf = dict(row)

        # Definition columns
        assert vf["severity"] == "critical"
        assert vf["description"] == "LiteSpeed Cache Auth Bypass"
        assert vf["risk"] == "Unauthenticated admin access"
        assert vf["cve_id"] == "CVE-2024-28000"
        assert vf["plugin_slug"] == "litespeed-cache"
        assert vf["provenance"] == "twin-derived"
        assert vf["category"] == "cve"

        # Occurrence columns
        assert vf["domain"] == "shop.dk"
        assert vf["cvr"] == "12345678"
        assert vf["confidence"] == "confirmed"
        assert vf["status"] == "open"
        assert vf["scan_count"] == 1
        assert vf["first_scan_id"] == "scan-v01"
        assert vf["last_scan_id"] == "scan-v01"
        assert vf["follow_ups_sent"] == 0
