"""Tests for the Telegram bot ``/start <token>`` handler.

Covers the Watchman-trial magic-link redemption flow:

- happy path (EN / DA language selection)
- invalid / consumed / expired tokens → generic reply, no side effects
- missing token argument → invalid-link reply, DB untouched
- missing company_name for a never-seen CVR → neutral failure reply
  (rolled back by :func:`src.db.onboarding.activate_watchman_trial`,
  token remains unconsumed)

Follows the project convention (see ``tests/test_telegram_errors.py``)
of driving async handlers via :func:`asyncio.run` instead of the
pytest-asyncio marker. Telegram interaction is fully mocked — no network.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.db.clients import create_client, get_client
from src.db.connection import init_db
from src.db.signup import create_signup_token, get_signup_token
from src.delivery.bot import (
    _MSG1_WATCHMAN_KICKOFF_DA,
    _MSG1_WATCHMAN_KICKOFF_EN,
    _MSG_ACTIVATION_FAILED_EN,
    _MSG_INVALID_LINK_EN,
    handle_start_command,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture()
def db(tmp_path):
    conn = init_db(tmp_path / "test.db")
    yield conn
    conn.close()


@pytest.fixture()
def prospect(db):
    """DA-preferring prospect already in the clients table."""
    return create_client(
        db,
        cvr="12345678",
        company_name="Kro Jelling",
        status="prospect",
        preferred_language="da",
    )


def _make_update(chat_id: int = 42) -> MagicMock:
    """Build a minimal ``telegram.Update`` stand-in with an ``effective_chat``."""
    update = MagicMock(name="Update")
    update.effective_chat = MagicMock(name="Chat")
    update.effective_chat.id = chat_id
    return update


def _make_context(db_conn, args: list[str] | None) -> MagicMock:
    """Build a minimal PTB ``ContextTypes.DEFAULT_TYPE`` stand-in.

    The handler reads ``context.args``, ``context.bot.send_message`` (async),
    and ``context.application.bot_data`` — nothing else. We inject the DB
    connection through ``bot_data['db_conn']`` so the handler never tries
    to open a fresh one.
    """
    context = MagicMock(name="Context")
    context.args = args
    context.bot = MagicMock(name="Bot")
    context.bot.send_message = AsyncMock(name="send_message")
    context.application = MagicMock(name="Application")
    context.application.bot_data = {"db_conn": db_conn}
    return context


def _run_start(update: MagicMock, context: MagicMock) -> None:
    """Drive ``handle_start_command`` on a fresh event loop."""
    asyncio.run(handle_start_command(update, context))


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestStartCommandHappyPath:
    def test_valid_token_activates_client_and_sends_da_kickoff(
        self, db, prospect
    ):
        token = create_signup_token(db, cvr=prospect["cvr"], email="owner@kro.dk")
        update = _make_update(chat_id=4242)
        context = _make_context(db, args=[token["token"]])

        _run_start(update, context)

        # DB side effects
        client = get_client(db, prospect["cvr"])
        assert client["status"] == "watchman_active"
        assert client["plan"] == "watchman"
        assert client["telegram_chat_id"] == "4242"

        # Token was consumed
        assert get_signup_token(db, token["token"])["consumed_at"] is not None

        # Exactly one Telegram message sent, with the DA kickoff body
        context.bot.send_message.assert_awaited_once()
        call = context.bot.send_message.await_args
        assert call.kwargs["chat_id"] == 4242
        assert call.kwargs["text"] == _MSG1_WATCHMAN_KICKOFF_DA

    def test_valid_token_defaults_to_en_for_english_clients(self, db):
        # preferred_language defaults to 'en' per the schema.
        client = create_client(
            db, cvr="87654321", company_name="English Pub ApS", status="prospect"
        )
        assert client["preferred_language"] == "en"
        token = create_signup_token(db, cvr="87654321")
        update = _make_update(chat_id=9001)
        context = _make_context(db, args=[token["token"]])

        _run_start(update, context)

        context.bot.send_message.assert_awaited_once()
        call = context.bot.send_message.await_args
        assert call.kwargs["text"] == _MSG1_WATCHMAN_KICKOFF_EN

    def test_language_da_vs_en_pick_different_bodies(self):
        # Sanity check on the constants themselves — the happy-path tests
        # above rely on these being meaningfully distinct.
        assert _MSG1_WATCHMAN_KICKOFF_DA != _MSG1_WATCHMAN_KICKOFF_EN
        assert "gratis" in _MSG1_WATCHMAN_KICKOFF_DA
        assert "free" in _MSG1_WATCHMAN_KICKOFF_EN


# ---------------------------------------------------------------------------
# Invalid inputs
# ---------------------------------------------------------------------------


class TestStartCommandInvalidInput:
    def test_missing_token_argument_replies_invalid_link(self, db, prospect):
        update = _make_update(chat_id=42)
        context = _make_context(db, args=[])

        _run_start(update, context)

        # Generic "invalid link" reply in EN (default language), no DB mutation
        context.bot.send_message.assert_awaited_once()
        assert (
            context.bot.send_message.await_args.kwargs["text"] == _MSG_INVALID_LINK_EN
        )
        assert get_client(db, prospect["cvr"])["status"] == "prospect"

    def test_unknown_token_replies_generic_error(self, db, prospect):
        update = _make_update(chat_id=42)
        context = _make_context(db, args=["this-token-does-not-exist"])

        _run_start(update, context)

        context.bot.send_message.assert_awaited_once()
        assert (
            context.bot.send_message.await_args.kwargs["text"] == _MSG_INVALID_LINK_EN
        )
        # Client untouched
        assert get_client(db, prospect["cvr"])["status"] == "prospect"

    def test_expired_token_replies_generic_error(self, db, prospect):
        from datetime import UTC, datetime, timedelta

        token = create_signup_token(db, cvr=prospect["cvr"])
        past = (datetime.now(UTC) - timedelta(minutes=5)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        db.execute(
            "UPDATE signup_tokens SET expires_at = ? WHERE token = ?",
            (past, token["token"]),
        )
        db.commit()

        update = _make_update(chat_id=42)
        context = _make_context(db, args=[token["token"]])

        _run_start(update, context)

        context.bot.send_message.assert_awaited_once()
        assert (
            context.bot.send_message.await_args.kwargs["text"] == _MSG_INVALID_LINK_EN
        )
        assert get_client(db, prospect["cvr"])["status"] == "prospect"
        # Expired token stays unconsumed (the transaction rolls back).
        assert get_signup_token(db, token["token"])["consumed_at"] is None

    def test_already_consumed_token_replies_generic_error(self, db, prospect):
        token = create_signup_token(db, cvr=prospect["cvr"])
        # First redemption: succeed.
        first_update = _make_update(chat_id=1)
        first_context = _make_context(db, args=[token["token"]])
        _run_start(first_update, first_context)

        # Second redemption with the same (now-consumed) token.
        second_update = _make_update(chat_id=2)
        second_context = _make_context(db, args=[token["token"]])
        _run_start(second_update, second_context)

        second_context.bot.send_message.assert_awaited_once()
        assert (
            second_context.bot.send_message.await_args.kwargs["text"]
            == _MSG_INVALID_LINK_EN
        )
        # Client chat_id should still reflect the first redemption only.
        client = get_client(db, prospect["cvr"])
        assert client["telegram_chat_id"] == "1"

    def test_missing_company_name_for_new_cvr_replies_activation_failed(
        self, db
    ):
        # No prospect pre-seeded — token points to a CVR that isn't in
        # clients. ``activate_watchman_trial`` raises ValueError because
        # company_name wasn't supplied. The handler surfaces the neutral
        # "please reply to the email" copy.
        token = create_signup_token(db, cvr="99887766")
        update = _make_update(chat_id=42)
        context = _make_context(db, args=[token["token"]])

        _run_start(update, context)

        context.bot.send_message.assert_awaited_once()
        assert (
            context.bot.send_message.await_args.kwargs["text"]
            == _MSG_ACTIVATION_FAILED_EN
        )
        # Token must not have been consumed — onboarding rolls back.
        assert get_signup_token(db, token["token"])["consumed_at"] is None
        # No client row created.
        assert get_client(db, "99887766") is None
