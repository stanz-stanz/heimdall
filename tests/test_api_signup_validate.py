"""Tests for src.api.signup.validate — read-only magic-link token check."""

from __future__ import annotations

import sqlite3
import threading
from datetime import UTC, datetime, timedelta

import pytest

from src.db.signup import consume_signup_token

from tests._signup_test_helpers import (
    BAD_ORIGIN,
    ORIGIN_DEV_LOCALHOST,
    ORIGIN_DEV_LOOPBACK,
    ORIGIN_PROD,
    SEED_CVR,
    init_seeded_db,
    issue_token,
    make_client,
)


@pytest.fixture
def db_path(tmp_path):
    db_file = tmp_path / "clients.db"
    init_seeded_db(str(db_file))
    return str(db_file)


@pytest.fixture
def client(db_path, tmp_path, monkeypatch):
    with make_client(db_path, tmp_path, monkeypatch) as tc:
        yield tc


@pytest.fixture
def issued_token(db_path):
    return issue_token(db_path, email="owner@test-restaurant.dk")


class TestValidateHappyPath:
    def test_valid_token_returns_ok_and_bot_username(self, client, issued_token):
        resp = client.post(
            "/signup/validate",
            json={"token": issued_token},
            headers={"Origin": ORIGIN_DEV_LOCALHOST},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["bot_username"] == "HeimdallSecurityDEVbot"


class TestValidateReasons:
    def test_unknown_token_returns_invalid(self, client):
        resp = client.post(
            "/signup/validate",
            json={"token": "nonexistent-token-abc123"},
            headers={"Origin": ORIGIN_DEV_LOCALHOST},
        )
        assert resp.status_code == 200
        assert resp.json() == {"ok": False, "reason": "invalid"}

    def test_consumed_token_returns_used(self, client, issued_token, db_path):
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            consume_signup_token(conn, issued_token)
        finally:
            conn.close()

        resp = client.post(
            "/signup/validate",
            json={"token": issued_token},
            headers={"Origin": ORIGIN_DEV_LOCALHOST},
        )
        assert resp.status_code == 200
        assert resp.json() == {"ok": False, "reason": "used"}

    def test_expired_token_returns_expired(self, client, db_path):
        past = (datetime.now(UTC) - timedelta(minutes=5)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        conn = sqlite3.connect(db_path)
        try:
            conn.execute(
                """
                INSERT INTO signup_tokens
                  (token, cvr, email, source, expires_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    "expired-token-xyz",
                    SEED_CVR,
                    None,
                    "email_reply",
                    past,
                    "2026-04-25T09:00:00Z",
                ),
            )
            conn.commit()
        finally:
            conn.close()

        resp = client.post(
            "/signup/validate",
            json={"token": "expired-token-xyz"},
            headers={"Origin": ORIGIN_DEV_LOCALHOST},
        )
        assert resp.status_code == 200
        assert resp.json() == {"ok": False, "reason": "expired"}

    def test_both_dev_origins_accepted(self, client, issued_token):
        for origin in (ORIGIN_DEV_LOCALHOST, ORIGIN_DEV_LOOPBACK, ORIGIN_PROD):
            resp = client.post(
                "/signup/validate",
                json={"token": issued_token},
                headers={"Origin": origin},
            )
            assert resp.status_code == 200, f"Origin {origin} failed"
            assert resp.json()["ok"] is True


class TestValidateGuards:
    def test_bad_origin_is_403(self, client, issued_token):
        resp = client.post(
            "/signup/validate",
            json={"token": issued_token},
            headers={"Origin": BAD_ORIGIN},
        )
        assert resp.status_code == 403

    def test_missing_origin_is_403(self, client, issued_token):
        resp = client.post(
            "/signup/validate",
            json={"token": issued_token},
        )
        assert resp.status_code == 403

    def test_missing_bot_username_is_503(
        self, client, issued_token, monkeypatch
    ):
        monkeypatch.delenv("TELEGRAM_BOT_USERNAME", raising=False)
        resp = client.post(
            "/signup/validate",
            json={"token": issued_token},
            headers={"Origin": ORIGIN_DEV_LOCALHOST},
        )
        assert resp.status_code == 503

    def test_missing_db_path_is_503(self, client, issued_token):
        # Strip db_path from app.state so _open_clients_db hits its
        # 503 guard. We restore it after the assertion so the fixture
        # teardown doesn't see a half-broken app.
        app = client.app
        original = getattr(app.state, "db_path", None)
        try:
            app.state.db_path = None
            resp = client.post(
                "/signup/validate",
                json={"token": issued_token},
                headers={"Origin": ORIGIN_DEV_LOCALHOST},
            )
            assert resp.status_code == 503
        finally:
            app.state.db_path = original

    def test_validate_does_not_mutate_token(
        self, client, issued_token, db_path
    ):
        client.post(
            "/signup/validate",
            json={"token": issued_token},
            headers={"Origin": ORIGIN_DEV_LOCALHOST},
        )
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT consumed_at, email FROM signup_tokens WHERE token = ?",
                (issued_token,),
            ).fetchone()
        finally:
            conn.close()
        assert row["consumed_at"] is None
        assert row["email"] == "owner@test-restaurant.dk"

    def test_concurrent_validates_both_succeed_and_dont_consume(
        self, client, issued_token, db_path
    ):
        """Per spec: two truly-concurrent validate calls must both
        succeed AND the DB token state must be unchanged after both.

        TestClient is thread-safe (httpx underneath); we use a
        threading.Barrier so the requests fire as close to
        simultaneously as the kernel allows.
        """
        results: list[dict] = []
        results_lock = threading.Lock()
        barrier = threading.Barrier(2, timeout=2)

        def worker():
            barrier.wait(timeout=2)
            r = client.post(
                "/signup/validate",
                json={"token": issued_token},
                headers={"Origin": ORIGIN_DEV_LOCALHOST},
            )
            with results_lock:
                results.append({"status": r.status_code, "body": r.json()})

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert len(results) == 2
        assert all(r["status"] == 200 for r in results)
        assert all(r["body"]["ok"] is True for r in results)

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT consumed_at, email FROM signup_tokens WHERE token = ?",
                (issued_token,),
            ).fetchone()
            count = conn.execute(
                "SELECT COUNT(*) AS n FROM signup_tokens WHERE token = ?",
                (issued_token,),
            ).fetchone()["n"]
        finally:
            conn.close()
        assert row["consumed_at"] is None
        assert row["email"] == "owner@test-restaurant.dk"
        assert count == 1
