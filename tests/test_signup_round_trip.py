"""End-to-end round trip: SvelteKit validate → Telegram /start activation."""

from __future__ import annotations

import sqlite3
import threading

import pytest

from src.db.onboarding import InvalidSignupToken, activate_watchman_trial

from tests._signup_test_helpers import (
    ORIGIN_DEV_LOCALHOST,
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


class TestRoundTrip:
    def test_validate_does_not_consume_then_activate_does(
        self, client, db_path
    ):
        token = issue_token(db_path)

        # Step 1: validate succeeds, token unchanged
        resp = client.post(
            "/signup/validate",
            json={"token": token},
            headers={"Origin": ORIGIN_DEV_LOCALHOST},
        )
        assert resp.json() == {
            "ok": True,
            "bot_username": "HeimdallSecurityDEVbot",
        }

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT consumed_at FROM signup_tokens WHERE token = ?",
                (token,),
            ).fetchone()
            assert row["consumed_at"] is None
        finally:
            conn.close()

        # Step 2: Telegram /start handler activates
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            client_row = activate_watchman_trial(
                conn, token, "tg_chat_id_123"
            )
        finally:
            conn.close()
        assert client_row["status"] == "watchman_active"
        assert client_row["plan"] == "watchman"
        assert client_row["telegram_chat_id"] == "tg_chat_id_123"

        # Step 3: validate now reports used
        resp = client.post(
            "/signup/validate",
            json={"token": token},
            headers={"Origin": ORIGIN_DEV_LOCALHOST},
        )
        assert resp.json() == {"ok": False, "reason": "used"}

        # Step 4: signup_tokens.email is nulled per Art 5(1)(e)
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT email, consumed_at FROM signup_tokens WHERE token = ?",
                (token,),
            ).fetchone()
            assert row["email"] is None
            assert row["consumed_at"] is not None
        finally:
            conn.close()

        # Step 5: exactly one conversion event
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            count = conn.execute(
                "SELECT COUNT(*) AS n FROM conversion_events "
                "WHERE cvr = ? AND event_type = 'signup'",
                (SEED_CVR,),
            ).fetchone()["n"]
            assert count == 1
        finally:
            conn.close()


class TestActivationRace:
    def test_two_concurrent_activations_one_wins(self, db_path):
        token = issue_token(db_path)
        outcomes: list[str] = []
        barrier = threading.Barrier(2)

        def worker(chat_id: str) -> None:
            conn = sqlite3.connect(db_path, timeout=10)
            conn.row_factory = sqlite3.Row
            try:
                barrier.wait(timeout=2)
                activate_watchman_trial(conn, token, chat_id)
                outcomes.append(f"ok:{chat_id}")
            except InvalidSignupToken:
                outcomes.append(f"raised:{chat_id}")
            finally:
                conn.close()

        t1 = threading.Thread(target=worker, args=("chat_1",))
        t2 = threading.Thread(target=worker, args=("chat_2",))
        t1.start()
        t2.start()
        t1.join(timeout=5)
        t2.join(timeout=5)

        assert sorted(outcomes)[:1][0].startswith("ok:")
        wins = [o for o in outcomes if o.startswith("ok:")]
        losses = [o for o in outcomes if o.startswith("raised:")]
        assert len(wins) == 1
        assert len(losses) == 1
