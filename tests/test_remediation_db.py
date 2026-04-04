"""Tests for RemediationTracker DB integration.

Verifies that transition() and reopen() write to finding_status_log and
update finding_occurrences.status when conn + occurrence_id are provided.
"""

from __future__ import annotations

import pytest

from src.client_memory.models import FindingRecord
from src.client_memory.remediation import RemediationTracker
from src.db.connection import init_db
from src.db.findings import get_status_log, upsert_definition, upsert_occurrence


@pytest.fixture
def db(tmp_path):
    """Create an in-memory-like temp DB with one client, definition, and occurrence."""
    conn = init_db(str(tmp_path / "test.db"))
    conn.execute(
        "INSERT INTO clients (cvr, company_name, created_at, updated_at) "
        "VALUES (?, ?, ?, ?)",
        ("12345678", "Test Co", "2026-01-01", "2026-01-01"),
    )
    upsert_definition(
        conn, "hash1", "high", "Test finding", first_seen_at="2026-01-01"
    )
    occ_id = upsert_occurrence(
        conn,
        "12345678",
        "test.dk",
        "hash1",
        first_seen_at="2026-01-01",
        last_seen_at="2026-01-01",
    )
    conn.commit()
    return conn, occ_id


@pytest.fixture
def tracker():
    return RemediationTracker()


@pytest.fixture
def open_finding():
    return FindingRecord(
        finding_id="abc123def456",
        description="Missing HSTS header",
        severity="medium",
        status="open",
        first_detected="2026-03-21",
        last_detected="2026-03-28",
        status_history=[
            {"status": "open", "date": "2026-03-21", "source": "scan:initial"}
        ],
    )


# --- DB writes on transition ---


def test_transition_writes_to_db(tracker, open_finding, db):
    """transition() with conn + occurrence_id writes a status log entry."""
    conn, occ_id = db

    tracker.transition(
        open_finding,
        "acknowledged",
        "client_reply",
        "2026-03-22T10:00:00Z",
        conn=conn,
        occurrence_id=occ_id,
    )

    log_entries = get_status_log(conn, occ_id)
    assert len(log_entries) == 1
    entry = log_entries[0]
    assert entry["from_status"] == "open"
    assert entry["to_status"] == "acknowledged"
    assert entry["source"] == "client_reply"

    # Verify occurrence row status was updated
    row = conn.execute(
        "SELECT status FROM finding_occurrences WHERE id = ?", (occ_id,)
    ).fetchone()
    assert row["status"] == "acknowledged"


def test_reopen_writes_to_db(tracker, open_finding, db):
    """reopen() with conn + occurrence_id writes a status log entry."""
    conn, occ_id = db

    # Walk to resolved first (in-memory only, no DB writes)
    tracker.transition(open_finding, "acknowledged", "client_reply")
    tracker.transition(open_finding, "resolved", "scan")
    assert open_finding.status == "resolved"

    # Manually set occurrence status to resolved so the DB is consistent
    conn.execute(
        "UPDATE finding_occurrences SET status = 'resolved' WHERE id = ?",
        (occ_id,),
    )
    conn.commit()

    # Now reopen with DB integration
    tracker.reopen(
        open_finding,
        "scan:regression",
        conn=conn,
        occurrence_id=occ_id,
    )

    log_entries = get_status_log(conn, occ_id)
    assert len(log_entries) == 1
    entry = log_entries[0]
    assert entry["from_status"] == "resolved"
    assert entry["to_status"] == "open"
    assert entry["source"] == "scan:regression"

    # Verify occurrence row status was updated
    row = conn.execute(
        "SELECT status FROM finding_occurrences WHERE id = ?", (occ_id,)
    ).fetchone()
    assert row["status"] == "open"


def test_transition_without_db_unchanged(tracker, open_finding):
    """Calling transition() without conn/occurrence_id works as before (no error)."""
    result = tracker.transition(
        open_finding, "acknowledged", "client_reply", "2026-03-22T10:00:00Z"
    )
    assert result.status == "acknowledged"
    assert len(result.status_history) == 2


def test_reopen_without_db_unchanged(tracker, open_finding):
    """Calling reopen() without conn/occurrence_id works as before (no error)."""
    tracker.transition(open_finding, "acknowledged", "client_reply")
    result = tracker.reopen(open_finding, "scan:regression")
    assert result.status == "open"
    assert result.resolved_date is None


def test_full_lifecycle_db_log(tracker, open_finding, db):
    """Walk through the full lifecycle with DB writes, verify 2 log entries."""
    conn, occ_id = db

    steps = [
        ("acknowledged", "client_reply"),
        ("resolved", "scan"),
    ]
    for new_status, source in steps:
        tracker.transition(
            open_finding, new_status, source, conn=conn, occurrence_id=occ_id
        )

    log_entries = get_status_log(conn, occ_id)
    assert len(log_entries) == 2

    expected = [
        ("open", "acknowledged", "client_reply"),
        ("acknowledged", "resolved", "scan"),
    ]
    for entry, (exp_from, exp_to, exp_source) in zip(log_entries, expected):
        assert entry["from_status"] == exp_from
        assert entry["to_status"] == exp_to
        assert entry["source"] == exp_source

    # Final occurrence status should be resolved
    row = conn.execute(
        "SELECT status FROM finding_occurrences WHERE id = ?", (occ_id,)
    ).fetchone()
    assert row["status"] == "resolved"


def test_transition_conn_without_occurrence_id_skips_db(tracker, open_finding, db):
    """Passing conn without occurrence_id does NOT write to DB."""
    conn, _ = db

    tracker.transition(
        open_finding,
        "acknowledged",
        "client_reply",
        conn=conn,
        occurrence_id=None,
    )

    # The occurrence should still be 'open' in DB (no write happened)
    row = conn.execute(
        "SELECT status FROM finding_occurrences WHERE id = 1"
    ).fetchone()
    assert row["status"] == "open"


def test_transition_occurrence_id_without_conn_skips_db(tracker, open_finding):
    """Passing occurrence_id without conn does NOT attempt DB write."""
    # This should not raise -- it just skips the DB path
    result = tracker.transition(
        open_finding,
        "acknowledged",
        "client_reply",
        conn=None,
        occurrence_id=42,
    )
    assert result.status == "acknowledged"
