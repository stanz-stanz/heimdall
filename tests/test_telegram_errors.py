"""Tests for permanent Telegram failure handling (Forbidden, BadRequest).

Covers Fix 1: sender.py Forbidden/BadRequest — permanent failure, no retry.
Covers Fix 2: approval.py — operator send failure is caught and logged.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram.error import BadRequest, Forbidden

from src.db.clients import create_client
from src.db.connection import init_db
from src.delivery.approval import request_approval
from src.delivery.sender import send_message


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_bot_forbidden():
    """Bot whose send_message always raises Forbidden."""
    bot = AsyncMock()
    bot.send_message.side_effect = Forbidden("bot was blocked by the user")
    return bot


@pytest.fixture()
def mock_bot_bad_request():
    """Bot whose send_message always raises BadRequest."""
    bot = AsyncMock()
    bot.send_message.side_effect = BadRequest("chat not found")
    return bot


@pytest.fixture()
def db(tmp_path):
    """Initialised client database with a test client."""
    conn = init_db(tmp_path / "test.db")
    create_client(
        conn,
        "12345678",
        "Test Restaurant",
        telegram_chat_id="999888777",
        status="active",
    )
    yield conn
    conn.close()


# ---------------------------------------------------------------------------
# Fix 1: sender.py — Forbidden / BadRequest permanent failures
# ---------------------------------------------------------------------------


class TestForbiddenPermanentFailure:
    """Forbidden errors are permanent — no retry, immediate failure result."""

    def test_forbidden_returns_permanent_failure(self, mock_bot_forbidden):
        """Forbidden exception returns success=False with descriptive error."""
        result = asyncio.run(
            send_message(mock_bot_forbidden, "999", "Hello", max_retries=3)
        )

        assert result["success"] is False
        assert result["message_id"] is None
        assert "Permanently failed" in result["error"]
        assert "blocked" in result["error"].lower()

    def test_forbidden_not_retried(self, mock_bot_forbidden):
        """send_message is called exactly once — Forbidden must not retry."""
        asyncio.run(
            send_message(mock_bot_forbidden, "999", "Hello", max_retries=3)
        )

        mock_bot_forbidden.send_message.assert_awaited_once()

    def test_forbidden_no_sleep(self, mock_bot_forbidden):
        """No asyncio.sleep call on Forbidden — immediate exit."""
        with patch(
            "src.delivery.sender.asyncio.sleep", new_callable=AsyncMock
        ) as mock_sleep:
            asyncio.run(
                send_message(mock_bot_forbidden, "999", "Hello", max_retries=3)
            )

        mock_sleep.assert_not_awaited()


class TestBadRequestPermanentFailure:
    """BadRequest errors are permanent — no retry, immediate failure result."""

    def test_bad_request_returns_permanent_failure(self, mock_bot_bad_request):
        """BadRequest exception returns success=False with descriptive error."""
        result = asyncio.run(
            send_message(mock_bot_bad_request, "999", "Hello", max_retries=3)
        )

        assert result["success"] is False
        assert result["message_id"] is None
        assert "Permanently failed" in result["error"]

    def test_bad_request_not_retried(self, mock_bot_bad_request):
        """send_message is called exactly once — BadRequest must not retry."""
        asyncio.run(
            send_message(mock_bot_bad_request, "999", "Hello", max_retries=3)
        )

        mock_bot_bad_request.send_message.assert_awaited_once()


# ---------------------------------------------------------------------------
# Fix 2: approval.py — operator send failure is caught, delivery_id returned
# ---------------------------------------------------------------------------


class TestApprovalOperatorSendFailure:
    """If operator Telegram send fails, request_approval logs and returns."""

    def test_network_error_returns_delivery_id(self, db):
        """Even when operator send raises, delivery_id is returned (not None)."""
        bot = AsyncMock()
        bot.send_message.side_effect = Exception("Network unreachable")

        delivery_id = asyncio.run(
            request_approval(
                bot=bot,
                operator_chat_id="bad_id",
                messages=["Finding chunk"],
                cvr="12345678",
                domain="test.dk",
                conn=db,
            )
        )

        assert isinstance(delivery_id, int)
        assert delivery_id > 0

    def test_forbidden_operator_does_not_propagate(self, db):
        """Forbidden on operator send does not propagate — returns delivery_id."""
        bot = AsyncMock()
        bot.send_message.side_effect = Forbidden("bot blocked by operator")

        # Should not raise.
        delivery_id = asyncio.run(
            request_approval(
                bot=bot,
                operator_chat_id="op_bad",
                messages=["Finding"],
                cvr="12345678",
                domain="test.dk",
                conn=db,
            )
        )

        assert isinstance(delivery_id, int)

    def test_delivery_log_entry_exists_even_after_send_failure(self, db):
        """delivery_log row is created before the send attempt; it survives failure."""
        bot = AsyncMock()
        bot.send_message.side_effect = Exception("Operator unreachable")

        delivery_id = asyncio.run(
            request_approval(
                bot=bot,
                operator_chat_id="op_bad",
                messages=["Finding"],
                cvr="12345678",
                domain="test.dk",
                conn=db,
            )
        )

        row = db.execute(
            "SELECT status FROM delivery_log WHERE id = ?", (delivery_id,)
        ).fetchone()
        # Row must exist — it was created before the send attempt.
        assert row is not None
        # Status remains 'pending' (failure was on the notify side, not DB side).
        assert row["status"] == "pending"

    def test_partial_chunk_send_failure_caught(self, db):
        """If the second chunk of a multi-chunk message fails, it is caught."""
        msg = MagicMock()
        msg.message_id = 1
        bot = AsyncMock()
        bot.send_message.side_effect = [msg, Exception("send failed on chunk 2")]

        # Should not raise.
        delivery_id = asyncio.run(
            request_approval(
                bot=bot,
                operator_chat_id="op_123",
                messages=["Chunk 1", "Chunk 2"],
                cvr="12345678",
                domain="test.dk",
                conn=db,
            )
        )

        assert isinstance(delivery_id, int)
