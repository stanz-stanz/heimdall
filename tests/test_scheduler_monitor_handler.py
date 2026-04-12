"""Unit tests for _handle_monitor_clients in scheduler daemon.

Verifies tier gating (Watchman skipped, Sentinel polled) and that the
handler delegates to ct_monitor.poll_and_diff_client per eligible client.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.db.connection import init_db
from src.db.migrate import _add_missing_columns
from src.scheduler.daemon import _handle_monitor_clients


def _setup_db(tmp_path):
    db = init_db(tmp_path / "clients.db")
    _add_missing_columns(db)
    # Watchman — must be skipped
    db.execute(
        """INSERT INTO clients
        (cvr, company_name, plan, status, created_at, updated_at, monitoring_enabled)
        VALUES ('100', 'Watchman Co', 'watchman', 'active', '2026-04-12T00:00:00Z', '2026-04-12T00:00:00Z', 0)"""
    )
    db.execute(
        """INSERT INTO client_domains (cvr, domain, is_primary, added_at)
        VALUES ('100', 'watchman.dk', 1, '2026-04-12T00:00:00Z')"""
    )
    # Sentinel with monitoring enabled — must be polled
    db.execute(
        """INSERT INTO clients
        (cvr, company_name, plan, status, created_at, updated_at, monitoring_enabled)
        VALUES ('200', 'Sentinel Co', 'sentinel', 'active', '2026-04-12T00:00:00Z', '2026-04-12T00:00:00Z', 1)"""
    )
    db.execute(
        """INSERT INTO client_domains (cvr, domain, is_primary, added_at)
        VALUES ('200', 'sentinel.dk', 1, '2026-04-12T00:00:00Z')"""
    )
    # Sentinel with monitoring disabled — must be skipped
    db.execute(
        """INSERT INTO clients
        (cvr, company_name, plan, status, created_at, updated_at, monitoring_enabled)
        VALUES ('300', 'Opted Out', 'sentinel', 'active', '2026-04-12T00:00:00Z', '2026-04-12T00:00:00Z', 0)"""
    )
    db.execute(
        """INSERT INTO client_domains (cvr, domain, is_primary, added_at)
        VALUES ('300', 'opted-out.dk', 1, '2026-04-12T00:00:00Z')"""
    )
    db.commit()
    return db


def test_only_sentinel_with_monitoring_enabled_is_polled(tmp_path, monkeypatch) -> None:
    db = _setup_db(tmp_path)
    db.close()
    monkeypatch.setenv("DB_PATH", str(tmp_path / "clients.db"))

    redis_conn = MagicMock()
    poll_mock = MagicMock(return_value={"issuances": 0, "new_snapshots": 0, "changes": 0})

    with patch("src.client_memory.ct_monitor.poll_and_diff_client", poll_mock):
        _handle_monitor_clients(redis_conn, {})

    assert poll_mock.call_count == 1
    args, _ = poll_mock.call_args
    assert args[0] == "200"  # Sentinel with monitoring enabled
    assert args[1] == "sentinel.dk"


def test_no_sentinel_clients_publishes_completed_with_zero(tmp_path, monkeypatch) -> None:
    db = init_db(tmp_path / "clients.db")
    _add_missing_columns(db)
    db.close()
    monkeypatch.setenv("DB_PATH", str(tmp_path / "clients.db"))

    redis_conn = MagicMock()

    with patch("src.client_memory.ct_monitor.poll_and_diff_client") as poll_mock:
        _handle_monitor_clients(redis_conn, {})
    poll_mock.assert_not_called()
    # At least one publish for the "No eligible clients" result
    assert redis_conn.publish.called


def test_missing_db_emits_error_result(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DB_PATH", str(tmp_path / "missing.db"))
    redis_conn = MagicMock()
    _handle_monitor_clients(redis_conn, {})
    # Should publish an error result to the command-results channel
    assert redis_conn.publish.called
