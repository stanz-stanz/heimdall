"""Tests for src.db.onboarding — signup → Watchman-trial activation."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from src.db.clients import create_client, get_client
from src.db.connection import init_db
from src.db.conversion import list_conversion_events_for_cvr
from src.db.onboarding import (
    WATCHMAN_TRIAL_DAYS,
    InvalidSignupToken,
    activate_watchman_trial,
)
from src.db.signup import (
    consume_signup_token,
    create_signup_token,
    get_signup_token,
)


@pytest.fixture()
def db(tmp_path):
    conn = init_db(tmp_path / "test.db")
    yield conn
    conn.close()


@pytest.fixture()
def prospect(db):
    return create_client(
        db,
        cvr="12345678",
        company_name="Kro Jelling",
        status="prospect",
    )


class TestActivateWatchmanTrial:
    def test_happy_path_existing_prospect(self, db, prospect):
        token = create_signup_token(
            db, cvr=prospect["cvr"], email="owner@kro.dk"
        )

        result = activate_watchman_trial(
            db, token=token["token"], telegram_chat_id="chat-42"
        )

        assert result["cvr"] == prospect["cvr"]
        assert result["status"] == "watchman_active"
        assert result["plan"] == "watchman"
        assert result["telegram_chat_id"] == "chat-42"
        assert result["signup_source"] == "email_reply"
        assert result["trial_started_at"] is not None
        assert result["trial_expires_at"] is not None

    def test_trial_window_is_30_days(self, db, prospect):
        token = create_signup_token(db, cvr=prospect["cvr"])
        result = activate_watchman_trial(
            db, token=token["token"], telegram_chat_id="chat-42"
        )

        started = datetime.strptime(
            result["trial_started_at"], "%Y-%m-%dT%H:%M:%SZ"
        ).replace(tzinfo=UTC)
        expires = datetime.strptime(
            result["trial_expires_at"], "%Y-%m-%dT%H:%M:%SZ"
        ).replace(tzinfo=UTC)

        assert expires - started == timedelta(days=WATCHMAN_TRIAL_DAYS)

    def test_consumes_token(self, db, prospect):
        token = create_signup_token(db, cvr=prospect["cvr"])
        activate_watchman_trial(
            db, token=token["token"], telegram_chat_id="chat-42"
        )

        row = get_signup_token(db, token["token"])
        assert row is not None
        assert row["consumed_at"] is not None

    def test_records_signup_conversion_event(self, db, prospect):
        token = create_signup_token(
            db, cvr=prospect["cvr"], source="operator_manual"
        )
        activate_watchman_trial(
            db, token=token["token"], telegram_chat_id="chat-42"
        )

        events = list_conversion_events_for_cvr(db, prospect["cvr"])
        signup_events = [e for e in events if e["event_type"] == "signup"]
        assert len(signup_events) == 1
        assert signup_events[0]["source"] == "operator_manual"
        payload = json.loads(signup_events[0]["payload_json"])
        assert payload["trial_days"] == WATCHMAN_TRIAL_DAYS

    def test_creates_client_when_absent(self, db):
        # No pre-existing clients row for this CVR.
        token = create_signup_token(db, cvr="99887766")

        result = activate_watchman_trial(
            db,
            token=token["token"],
            telegram_chat_id="chat-99",
            company_name="New Customer ApS",
        )

        assert result["cvr"] == "99887766"
        assert result["company_name"] == "New Customer ApS"
        assert result["status"] == "watchman_active"

        # Verify it's persisted.
        row = get_client(db, "99887766")
        assert row is not None
        assert row["telegram_chat_id"] == "chat-99"

    def test_missing_client_without_company_name_rolls_back(self, db):
        token = create_signup_token(db, cvr="99887766")

        with pytest.raises(ValueError, match="company_name"):
            activate_watchman_trial(
                db, token=token["token"], telegram_chat_id="chat-99"
            )

        # Token must remain unconsumed so the prospect can retry with a
        # follow-up that supplies company_name.
        assert get_signup_token(db, token["token"])["consumed_at"] is None

    def test_invalid_token_raises(self, db, prospect):
        with pytest.raises(InvalidSignupToken):
            activate_watchman_trial(
                db, token="nonexistent", telegram_chat_id="chat-42"
            )

    def test_expired_token_raises(self, db, prospect):
        token = create_signup_token(db, cvr=prospect["cvr"])
        past = (datetime.now(UTC) - timedelta(minutes=5)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        db.execute(
            "UPDATE signup_tokens SET expires_at = ? WHERE token = ?",
            (past, token["token"]),
        )
        db.commit()

        with pytest.raises(InvalidSignupToken):
            activate_watchman_trial(
                db, token=token["token"], telegram_chat_id="chat-42"
            )

        # Client must not have been activated.
        row = get_client(db, prospect["cvr"])
        assert row["status"] == "prospect"

    def test_already_consumed_token_raises(self, db, prospect):
        token = create_signup_token(db, cvr=prospect["cvr"])
        consume_signup_token(db, token["token"])

        with pytest.raises(InvalidSignupToken):
            activate_watchman_trial(
                db, token=token["token"], telegram_chat_id="chat-42"
            )

    def test_clears_onboarding_stage_on_activation(self, db):
        # A pre-existing client row with a stray onboarding_stage from a
        # prior sentinel attempt should be cleared on Watchman activation.
        create_client(
            db,
            cvr="55555555",
            company_name="Returning Co",
            status="watchman_expired",
            onboarding_stage="upgrade_interest",
        )
        token = create_signup_token(db, cvr="55555555")

        result = activate_watchman_trial(
            db, token=token["token"], telegram_chat_id="chat-new"
        )

        assert result["onboarding_stage"] is None
        assert result["status"] == "watchman_active"

    def test_double_activation_with_fresh_tokens_is_idempotent(
        self, db, prospect
    ):
        # Second activation with a fresh token should re-bind chat_id +
        # reset trial window without error.
        token1 = create_signup_token(db, cvr=prospect["cvr"])
        first = activate_watchman_trial(
            db, token=token1["token"], telegram_chat_id="old-chat"
        )
        token2 = create_signup_token(db, cvr=prospect["cvr"])
        second = activate_watchman_trial(
            db, token=token2["token"], telegram_chat_id="new-chat"
        )

        assert first["telegram_chat_id"] == "old-chat"
        assert second["telegram_chat_id"] == "new-chat"
        assert second["status"] == "watchman_active"

        events = list_conversion_events_for_cvr(db, prospect["cvr"])
        assert sum(1 for e in events if e["event_type"] == "signup") == 2
