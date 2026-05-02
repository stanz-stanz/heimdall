"""Tests for src.db.audit_context — bind_audit_context context manager.

Stage A.5 spec §4.1.4 + §6.1. Covers:
- Happy path: bind + UPDATE on clients fires trigger with populated actor fields.
- Exception cleanup: context exits cleanly even if the with-block raises.
- TEMP-table isolation: per-connection scope; one connection's bind does not
  leak to another connection on the same DB.
- Bypass detection: a raw UPDATE outside the context manager still fires the
  trigger but with NULL actor columns — forensically detectable.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from src.db.audit_context import bind_audit_context
from src.db.connection import init_db


_NOW = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _seed_client(conn, cvr: str = "12345678") -> None:
    conn.execute(
        "INSERT INTO clients (cvr, company_name, status, created_at, updated_at) "
        "VALUES (?, 'Test ApS', 'prospect', ?, ?)",
        (cvr, _NOW, _NOW),
    )
    conn.commit()


def test_bind_audit_context_populates_trigger_row(tmp_path: Path) -> None:
    conn = init_db(tmp_path / "test.db")
    _seed_client(conn)

    with bind_audit_context(
        conn,
        intent="test.update",
        operator_id=42,
        session_id=7,
        request_id="r-test-1",
    ):
        conn.execute("UPDATE clients SET status = 'active' WHERE cvr = ?", ("12345678",))
        conn.commit()

    row = conn.execute(
        "SELECT table_name, op, target_pk, intent, operator_id, session_id, "
        "request_id, actor_kind FROM config_changes"
    ).fetchone()

    assert row is not None
    assert row["table_name"] == "clients"
    assert row["op"] == "UPDATE"
    assert row["target_pk"] == "12345678"
    assert row["intent"] == "test.update"
    assert row["operator_id"] == 42
    assert row["session_id"] == 7
    assert row["request_id"] == "r-test-1"
    assert row["actor_kind"] == "operator"

    # Type contract: operator_id / session_id land as INTEGER (not TEXT
    # '42' coerced — the UDF returns native int per spec §4.1.10).
    types = conn.execute(
        "SELECT typeof(operator_id) AS op_t, typeof(session_id) AS sess_t, "
        "typeof(request_id) AS rid_t, typeof(intent) AS int_t "
        "FROM config_changes"
    ).fetchone()
    assert types["op_t"] == "integer"
    assert types["sess_t"] == "integer"
    assert types["rid_t"] == "text"
    assert types["int_t"] == "text"
    conn.close()


def test_bind_audit_context_delete_path(tmp_path: Path) -> None:
    """DELETE trigger captures OLD snapshot + actor metadata; new_json NULL."""
    conn = init_db(tmp_path / "test.db")
    _seed_client(conn, cvr="99999999")

    with bind_audit_context(
        conn,
        intent="retention.purge",
        operator_id=5,
        request_id="r-del-1",
    ):
        conn.execute("DELETE FROM clients WHERE cvr = ?", ("99999999",))
        conn.commit()

    row = conn.execute(
        "SELECT op, target_pk, old_json, new_json, intent, operator_id, "
        "request_id, actor_kind FROM config_changes"
    ).fetchone()
    assert row is not None
    assert row["op"] == "DELETE"
    assert row["target_pk"] == "99999999"
    assert row["old_json"] is not None
    assert "99999999" in row["old_json"]
    # DELETE has no NEW row — snapshot is NULL.
    assert row["new_json"] is None
    assert row["intent"] == "retention.purge"
    assert row["operator_id"] == 5
    assert row["request_id"] == "r-del-1"
    assert row["actor_kind"] == "operator"
    conn.close()


def test_bind_audit_context_clears_on_exit(tmp_path: Path) -> None:
    """After the with-block exits, the next mutation reads NULL actor."""
    conn = init_db(tmp_path / "test.db")
    _seed_client(conn)

    with bind_audit_context(
        conn,
        intent="test.update",
        operator_id=42,
        request_id="r-test-1",
    ):
        conn.execute("UPDATE clients SET status = 'active' WHERE cvr = ?", ("12345678",))
        conn.commit()

    # Outside the context manager: bypass path. Trigger fires with NULL actor.
    conn.execute("UPDATE clients SET status = 'paused' WHERE cvr = ?", ("12345678",))
    conn.commit()

    rows = conn.execute(
        "SELECT operator_id, intent, request_id, actor_kind "
        "FROM config_changes ORDER BY id"
    ).fetchall()
    assert len(rows) == 2
    assert rows[0]["intent"] == "test.update"
    assert rows[0]["operator_id"] == 42
    assert rows[1]["intent"] is None
    assert rows[1]["operator_id"] is None
    assert rows[1]["request_id"] is None
    # actor_kind defaults via COALESCE in the trigger when TEMP is empty.
    assert rows[1]["actor_kind"] == "operator"
    conn.close()


def test_bind_audit_context_clears_on_exception(tmp_path: Path) -> None:
    """Even if the with-block raises, the TEMP rows are cleared."""
    conn = init_db(tmp_path / "test.db")
    _seed_client(conn)

    class BoomError(Exception):
        pass

    with pytest.raises(BoomError):
        with bind_audit_context(
            conn,
            intent="test.boom",
            operator_id=99,
            request_id="r-boom",
        ):
            conn.execute("UPDATE clients SET status = 'active' WHERE cvr = ?", ("12345678",))
            conn.commit()
            raise BoomError("simulated handler failure")

    # The first UPDATE landed before the raise — its trigger row should
    # carry the bound context.
    boom_row = conn.execute(
        "SELECT intent, operator_id, request_id FROM config_changes"
    ).fetchone()
    assert boom_row["intent"] == "test.boom"
    assert boom_row["operator_id"] == 99
    assert boom_row["request_id"] == "r-boom"

    # Subsequent unrelated UPDATE on the same connection — TEMP must be empty.
    conn.execute("UPDATE clients SET status = 'paused' WHERE cvr = ?", ("12345678",))
    conn.commit()
    next_row = conn.execute(
        "SELECT intent, operator_id, request_id FROM config_changes "
        "ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert next_row["intent"] is None
    assert next_row["operator_id"] is None
    assert next_row["request_id"] is None
    conn.close()


def test_bind_audit_context_temp_table_is_per_connection(tmp_path: Path) -> None:
    """Conn A binds; Conn B writes; Conn B's row has NULL actor (no leak)."""
    db_path = tmp_path / "test.db"
    conn_a = init_db(db_path)
    conn_b = init_db(db_path)
    _seed_client(conn_a, cvr="11111111")
    _seed_client(conn_a, cvr="22222222")

    # Conn A binds context but does NOT mutate yet.
    with bind_audit_context(
        conn_a,
        intent="conn_a.intent",
        operator_id=1,
        request_id="r-a",
    ):
        # Conn B mutates a DIFFERENT client without binding.
        conn_b.execute(
            "UPDATE clients SET status = 'active' WHERE cvr = ?", ("22222222",)
        )
        conn_b.commit()

    # Conn B's trigger row should have NULL actor — its TEMP table is empty.
    row = conn_b.execute(
        "SELECT target_pk, intent, operator_id, request_id "
        "FROM config_changes WHERE target_pk = ?",
        ("22222222",),
    ).fetchone()
    assert row is not None
    assert row["intent"] is None
    assert row["operator_id"] is None
    assert row["request_id"] is None
    conn_a.close()
    conn_b.close()


def test_bind_audit_context_actor_kind_system(tmp_path: Path) -> None:
    """Cron-path callers pass actor_kind='system' with no operator id."""
    conn = init_db(tmp_path / "test.db")
    _seed_client(conn)

    with bind_audit_context(
        conn,
        intent="retention.claim",
        actor_kind="system",
    ):
        conn.execute("UPDATE clients SET status = 'churned' WHERE cvr = ?", ("12345678",))
        conn.commit()

    row = conn.execute(
        "SELECT operator_id, session_id, request_id, intent, actor_kind "
        "FROM config_changes"
    ).fetchone()
    assert row["operator_id"] is None
    assert row["session_id"] is None
    assert row["request_id"] is None
    assert row["intent"] == "retention.claim"
    assert row["actor_kind"] == "system"
    conn.close()


def test_bind_audit_context_bypass_writes_null_actor(tmp_path: Path) -> None:
    """Direct UPDATE (no with-block) still fires the trigger; actor NULL."""
    conn = init_db(tmp_path / "test.db")
    _seed_client(conn)

    # No bind_audit_context — bypass path.
    conn.execute("UPDATE clients SET status = 'active' WHERE cvr = ?", ("12345678",))
    conn.commit()

    row = conn.execute(
        "SELECT table_name, op, target_pk, operator_id, session_id, "
        "request_id, intent, actor_kind FROM config_changes"
    ).fetchone()
    assert row is not None, "trigger must fire even on wrapper bypass"
    assert row["table_name"] == "clients"
    assert row["op"] == "UPDATE"
    assert row["target_pk"] == "12345678"
    assert row["operator_id"] is None
    assert row["session_id"] is None
    assert row["request_id"] is None
    assert row["intent"] is None
    # COALESCE default in trigger.
    assert row["actor_kind"] == "operator"
    conn.close()
