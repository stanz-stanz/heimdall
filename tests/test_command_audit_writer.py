"""Tests for src.db.audit.write_command_audit_row.

Stage A.5 spec §4.1.6 + §6.1. Covers happy path, NULL columns, payload JSON
serialization, request_id correlation.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from src.db.audit import write_command_audit_row
from src.db.connection import init_db


def test_write_command_audit_row_happy_path(tmp_path: Path) -> None:
    conn = init_db(tmp_path / "test.db")

    rid = write_command_audit_row(
        conn,
        command_name="run-pipeline",
        outcome="ok",
        target_type="pipeline_run",
        target_id="42",
        payload={"campaign": "0526-restaurants", "limit": 100},
        operator_id=1,
        session_id=2,
        request_id="r-cmd-1",
        actor_kind="operator",
    )
    conn.commit()

    assert rid > 0
    row = conn.execute(
        "SELECT command_name, target_type, target_id, outcome, "
        "payload_json, error_detail, operator_id, session_id, "
        "request_id, actor_kind, occurred_at FROM command_audit "
        "WHERE id = ?",
        (rid,),
    ).fetchone()
    assert row is not None
    assert row["command_name"] == "run-pipeline"
    assert row["target_type"] == "pipeline_run"
    assert row["target_id"] == "42"
    assert row["outcome"] == "ok"
    assert json.loads(row["payload_json"]) == {
        "campaign": "0526-restaurants",
        "limit": 100,
    }
    assert row["error_detail"] is None
    assert row["operator_id"] == 1
    assert row["session_id"] == 2
    assert row["request_id"] == "r-cmd-1"
    assert row["actor_kind"] == "operator"
    # occurred_at populated and ISO-8601 with millisecond precision.
    assert row["occurred_at"].endswith("Z")
    assert "T" in row["occurred_at"]
    conn.close()


def test_write_command_audit_row_null_columns(tmp_path: Path) -> None:
    """Optional fields land as NULL when omitted."""
    conn = init_db(tmp_path / "test.db")

    rid = write_command_audit_row(
        conn,
        command_name="probe",
        outcome="ok",
    )
    conn.commit()

    row = conn.execute(
        "SELECT target_type, target_id, payload_json, error_detail, "
        "operator_id, session_id, request_id, actor_kind "
        "FROM command_audit WHERE id = ?",
        (rid,),
    ).fetchone()
    assert row["target_type"] is None
    assert row["target_id"] is None
    assert row["payload_json"] is None
    assert row["error_detail"] is None
    assert row["operator_id"] is None
    assert row["session_id"] is None
    assert row["request_id"] is None
    # actor_kind has a SQL DEFAULT of 'operator' but the writer always
    # supplies it explicitly (default kwarg).
    assert row["actor_kind"] == "operator"
    conn.close()


def test_write_command_audit_row_error_outcome(tmp_path: Path) -> None:
    """Error path populates error_detail; outcome is 'error'."""
    conn = init_db(tmp_path / "test.db")

    rid = write_command_audit_row(
        conn,
        command_name="interpret",
        outcome="error",
        error_detail="claude-api timeout after 30s",
        operator_id=1,
        request_id="r-cmd-err",
    )
    conn.commit()

    row = conn.execute(
        "SELECT outcome, error_detail FROM command_audit WHERE id = ?",
        (rid,),
    ).fetchone()
    assert row["outcome"] == "error"
    assert row["error_detail"] == "claude-api timeout after 30s"
    conn.close()


def test_write_command_audit_row_actor_kind_system(tmp_path: Path) -> None:
    """Cron-driven command runs pass actor_kind='system' with no operator id."""
    conn = init_db(tmp_path / "test.db")

    rid = write_command_audit_row(
        conn,
        command_name="retention.bookkeeping_purge",
        outcome="ok",
        target_type="cvr",
        target_id="12345678",
        actor_kind="system",
    )
    conn.commit()

    row = conn.execute(
        "SELECT operator_id, session_id, request_id, actor_kind "
        "FROM command_audit WHERE id = ?",
        (rid,),
    ).fetchone()
    assert row["operator_id"] is None
    assert row["session_id"] is None
    assert row["request_id"] is None
    assert row["actor_kind"] == "system"
    conn.close()


def test_write_command_audit_row_payload_with_non_serialisable(tmp_path: Path) -> None:
    """``default=str`` fallback handles datetime / Path objects."""
    conn = init_db(tmp_path / "test.db")

    rid = write_command_audit_row(
        conn,
        command_name="send",
        outcome="ok",
        payload={
            "scheduled": datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC),
            "report": Path("/data/reports/2026-05-01.json"),
        },
    )
    conn.commit()

    row = conn.execute(
        "SELECT payload_json FROM command_audit WHERE id = ?", (rid,)
    ).fetchone()
    parsed = json.loads(row["payload_json"])
    # datetime stringifies to "2026-05-01 12:00:00+00:00"
    assert "2026-05-01" in parsed["scheduled"]
    # Path stringifies to its str repr
    assert parsed["report"] == "/data/reports/2026-05-01.json"
    conn.close()


def test_write_command_audit_row_no_implicit_commit(tmp_path: Path) -> None:
    """Helper does NOT commit — caller's transaction is the boundary."""
    conn = init_db(tmp_path / "test.db")
    write_command_audit_row(conn, command_name="probe", outcome="ok")
    # Without commit, a separate connection should NOT see the row
    # (WAL mode permits concurrent reads, but the uncommitted row is
    # only visible on the writer connection).
    other = init_db(tmp_path / "test.db")
    seen = other.execute("SELECT COUNT(*) FROM command_audit").fetchone()[0]
    assert seen == 0
    conn.commit()
    other.close()
    conn.close()
