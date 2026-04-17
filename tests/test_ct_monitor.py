"""Unit tests for src.client_memory.ct_monitor.

Covers: fetch + normalize, diff classification (all three change types),
dedupe window, snapshot upsert, and Redis event emission. Uses
httpx.MockTransport so no real network calls.
"""

from __future__ import annotations

import json
import sqlite3
from unittest.mock import MagicMock

import httpx
import pytest

from src.client_memory import ct_monitor
from src.db.connection import init_db
from src.db.migrate import _add_missing_columns


def _mk_db(tmp_path) -> sqlite3.Connection:
    db = init_db(tmp_path / "clients.db")
    _add_missing_columns(db)
    db.execute(
        """
        INSERT INTO clients (cvr, company_name, plan, status, created_at, updated_at, monitoring_enabled)
        VALUES ('123', 'Test ApS', 'sentinel', 'active', '2026-04-12T00:00:00Z', '2026-04-12T00:00:00Z', 1)
        """
    )
    db.commit()
    return db


def _mock_client(issuances_pages: list[list[dict]]) -> httpx.Client:
    """httpx.Client that returns the given pages in order then empty."""
    call_counter = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        n = call_counter["n"]
        call_counter["n"] += 1
        if n < len(issuances_pages):
            return httpx.Response(200, json=issuances_pages[n])
        return httpx.Response(200, json=[])

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_first_poll_baselines_without_emitting_changes(tmp_path, monkeypatch) -> None:
    db = _mk_db(tmp_path)
    redis = MagicMock()

    issuances = [
        {
            "id": "1",
            "cert_sha256": "aaa",
            "dns_names": ["foo.dk"],
            "issuer": {"friendly_name": "Let's Encrypt"},
            "not_before": "2026-04-01",
            "not_after": "2026-07-01",
        }
    ]
    client = _mock_client([issuances])
    monkeypatch.setattr(ct_monitor, "_fetch_issuances", lambda *a, **k: issuances)

    summary = ct_monitor.poll_and_diff_client("123", "foo.dk", db, redis)

    assert summary["issuances"] == 1
    assert summary["new_snapshots"] == 1
    assert summary["changes"] == 0  # first poll = baseline, no alerts
    assert not redis.publish.called

    rows = db.execute("SELECT * FROM client_cert_snapshots").fetchall()
    assert len(rows) == 1
    assert rows[0]["cert_sha256"] == "aaa"


def test_new_cert_detected_on_second_poll(tmp_path, monkeypatch) -> None:
    db = _mk_db(tmp_path)
    redis = MagicMock()

    # First poll: baseline
    baseline = [
        {
            "id": "1",
            "cert_sha256": "aaa",
            "dns_names": ["foo.dk"],
            "issuer": {"friendly_name": "Let's Encrypt"},
        }
    ]
    monkeypatch.setattr(ct_monitor, "_fetch_issuances", lambda *a, **k: baseline)
    ct_monitor.poll_and_diff_client("123", "foo.dk", db, redis)

    # Second poll: baseline + new cert with same SANs, same CA
    second = baseline + [
        {
            "id": "2",
            "cert_sha256": "bbb",
            "dns_names": ["foo.dk"],
            "issuer": {"friendly_name": "Let's Encrypt"},
        }
    ]
    monkeypatch.setattr(ct_monitor, "_fetch_issuances", lambda *a, **k: second)
    summary = ct_monitor.poll_and_diff_client("123", "foo.dk", db, redis)

    assert summary["changes"] == 1
    changes = db.execute("SELECT * FROM client_cert_changes").fetchall()
    assert len(changes) == 1
    assert changes[0]["change_type"] == "new_cert"
    redis.publish.assert_called()


def test_new_san_detected(tmp_path, monkeypatch) -> None:
    db = _mk_db(tmp_path)
    redis = MagicMock()

    baseline = [
        {
            "id": "1",
            "cert_sha256": "aaa",
            "dns_names": ["foo.dk"],
            "issuer": {"friendly_name": "Let's Encrypt"},
        }
    ]
    monkeypatch.setattr(ct_monitor, "_fetch_issuances", lambda *a, **k: baseline)
    ct_monitor.poll_and_diff_client("123", "foo.dk", db, redis)

    second = baseline + [
        {
            "id": "2",
            "cert_sha256": "bbb",
            "dns_names": ["foo.dk", "admin.foo.dk"],
            "issuer": {"friendly_name": "Let's Encrypt"},
        }
    ]
    monkeypatch.setattr(ct_monitor, "_fetch_issuances", lambda *a, **k: second)
    summary = ct_monitor.poll_and_diff_client("123", "foo.dk", db, redis)

    assert summary["changes"] == 1
    change = db.execute("SELECT * FROM client_cert_changes").fetchone()
    assert change["change_type"] == "new_san"


def test_ca_change_detected(tmp_path, monkeypatch) -> None:
    db = _mk_db(tmp_path)
    redis = MagicMock()

    baseline = [
        {
            "id": "1",
            "cert_sha256": "aaa",
            "dns_names": ["foo.dk"],
            "issuer": {"friendly_name": "Let's Encrypt"},
        }
    ]
    monkeypatch.setattr(ct_monitor, "_fetch_issuances", lambda *a, **k: baseline)
    ct_monitor.poll_and_diff_client("123", "foo.dk", db, redis)

    second = baseline + [
        {
            "id": "2",
            "cert_sha256": "bbb",
            "dns_names": ["foo.dk"],
            "issuer": {"friendly_name": "DigiCert"},
        }
    ]
    monkeypatch.setattr(ct_monitor, "_fetch_issuances", lambda *a, **k: second)
    summary = ct_monitor.poll_and_diff_client("123", "foo.dk", db, redis)

    assert summary["changes"] == 1
    change = db.execute("SELECT * FROM client_cert_changes").fetchone()
    assert change["change_type"] == "ca_change"


def test_dedupe_window_suppresses_repeat_alerts(tmp_path, monkeypatch) -> None:
    db = _mk_db(tmp_path)
    redis = MagicMock()

    baseline = [
        {"id": "1", "cert_sha256": "aaa", "dns_names": ["foo.dk"], "issuer": {"friendly_name": "LE"}}
    ]
    monkeypatch.setattr(ct_monitor, "_fetch_issuances", lambda *a, **k: baseline)
    ct_monitor.poll_and_diff_client("123", "foo.dk", db, redis)

    # First new cert — emit change
    second = baseline + [
        {"id": "2", "cert_sha256": "bbb", "dns_names": ["foo.dk"], "issuer": {"friendly_name": "LE"}}
    ]
    monkeypatch.setattr(ct_monitor, "_fetch_issuances", lambda *a, **k: second)
    ct_monitor.poll_and_diff_client("123", "foo.dk", db, redis)

    # Third poll with another new cert — should dedupe (same type within window)
    third = second + [
        {"id": "3", "cert_sha256": "ccc", "dns_names": ["foo.dk"], "issuer": {"friendly_name": "LE"}}
    ]
    monkeypatch.setattr(ct_monitor, "_fetch_issuances", lambda *a, **k: third)
    summary = ct_monitor.poll_and_diff_client("123", "foo.dk", db, redis)

    assert summary["changes"] == 0  # deduped
    changes = db.execute("SELECT COUNT(*) FROM client_cert_changes").fetchone()[0]
    assert changes == 1  # only the first new_cert row


def test_ct_last_polled_at_updated(tmp_path, monkeypatch) -> None:
    db = _mk_db(tmp_path)
    redis = MagicMock()
    monkeypatch.setattr(ct_monitor, "_fetch_issuances", lambda *a, **k: [])

    ct_monitor.poll_and_diff_client("123", "foo.dk", db, redis)
    row = db.execute("SELECT ct_last_polled_at FROM clients WHERE cvr = '123'").fetchone()
    assert row["ct_last_polled_at"] is not None


class _CommitTrackingConn:
    """Proxy around sqlite3.Connection that flips a flag on commit().

    sqlite3.Connection is a C type and its ``commit`` attribute is read-only,
    so we cannot monkeypatch it directly. A thin proxy is enough: the module
    under test only calls ``.execute()`` and ``.commit()`` on the connection.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self.committed = False

    def execute(self, *args, **kwargs):
        return self._conn.execute(*args, **kwargs)

    def commit(self) -> None:
        self._conn.commit()
        self.committed = True


def test_publish_happens_after_commit(tmp_path, monkeypatch) -> None:
    """Regression: Redis publish must fire AFTER db_conn.commit() so the
    delivery runner never races the SELECT on client_cert_changes.

    We wrap the connection to flip a flag on commit(), and give the MagicMock
    redis a publish side_effect that records the commit flag value at the
    moment publish is invoked. The top-level assertion then inspects that
    recorded value — kept outside the production code's try/except so a
    swallowed AssertionError can't mask the regression.
    """
    real_db = _mk_db(tmp_path)

    # Seed a baseline directly on the real connection so the second poll's
    # new cert actually produces a change.
    baseline = [
        {
            "id": "1",
            "cert_sha256": "aaa",
            "dns_names": ["foo.dk"],
            "issuer": {"friendly_name": "Let's Encrypt"},
        }
    ]
    monkeypatch.setattr(ct_monitor, "_fetch_issuances", lambda *a, **k: baseline)
    ct_monitor.poll_and_diff_client("123", "foo.dk", real_db, MagicMock())

    # Now wrap the connection for the assertion-under-test on the second poll.
    tracked = _CommitTrackingConn(real_db)

    # Record the commit flag state at each publish call. The production code
    # wraps publish in `try: ... except Exception:`, so an AssertionError
    # raised from inside this side_effect would be silently swallowed. We
    # therefore only record here and assert at test scope.
    publish_order: list[bool] = []

    def asserting_publish(channel, data):
        publish_order.append(tracked.committed)

    redis = MagicMock()
    redis.publish.side_effect = asserting_publish

    second = [
        *baseline,
        {
            "id": "2",
            "cert_sha256": "bbb",
            "dns_names": ["foo.dk"],
            "issuer": {"friendly_name": "Let's Encrypt"},
        },
    ]
    monkeypatch.setattr(ct_monitor, "_fetch_issuances", lambda *a, **k: second)
    summary = ct_monitor.poll_and_diff_client("123", "foo.dk", tracked, redis)

    assert summary["changes"] == 1
    assert tracked.committed is True
    redis.publish.assert_called_once()
    assert publish_order == [True], (
        f"redis.publish fired with committed={publish_order} — "
        "pre-commit race reintroduced"
    )
