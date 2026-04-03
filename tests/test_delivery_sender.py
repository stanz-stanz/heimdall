"""Tests for Telegram message sender with retry and DB logging."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram.error import NetworkError, RetryAfter, TimedOut

from src.db.connection import init_db
from src.db.delivery import log_delivery, update_delivery_status
from src.delivery.sender import send_message, send_messages, send_with_logging


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_bot() -> AsyncMock:
    """Telegram Bot mock that returns a message with id=42."""
    bot = AsyncMock()
    msg = MagicMock()
    msg.message_id = 42
    bot.send_message.return_value = msg
    return bot


@pytest.fixture()
def db(tmp_path):
    """Initialised client database with a test client row."""
    conn = init_db(tmp_path / "test.db")
    conn.execute(
        "INSERT INTO clients (cvr, company_name, created_at, updated_at) "
        "VALUES (?, ?, ?, ?)",
        ("12345678", "Test Co", "2026-01-01", "2026-01-01"),
    )
    conn.commit()
    yield conn
    conn.close()


# ---------------------------------------------------------------------------
# send_message
# ---------------------------------------------------------------------------


class TestSendMessage:
    """Single-message sending with retry logic."""

    def test_send_message_success(self, mock_bot: AsyncMock) -> None:
        result = asyncio.run(send_message(mock_bot, "999", "Hello"))
        assert result["success"] is True
        assert result["message_id"] == 42
        assert result["error"] is None
        mock_bot.send_message.assert_awaited_once_with(
            chat_id="999", text="Hello", parse_mode="HTML",
        )

    def test_send_message_retry_after_then_success(
        self, mock_bot: AsyncMock
    ) -> None:
        """First call raises RetryAfter, second succeeds."""
        exc = RetryAfter(retry_after=1)
        msg = MagicMock()
        msg.message_id = 99
        mock_bot.send_message.side_effect = [exc, msg]

        with patch("src.delivery.sender.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            result = asyncio.run(send_message(mock_bot, "999", "Hi"))

        assert result["success"] is True
        assert result["message_id"] == 99
        mock_sleep.assert_awaited_once_with(1)

    def test_send_message_max_retries_exhausted(self, mock_bot: AsyncMock) -> None:
        """All attempts raise TimedOut -- returns failure."""
        mock_bot.send_message.side_effect = TimedOut()

        with patch("src.delivery.sender.asyncio.sleep", new_callable=AsyncMock):
            result = asyncio.run(
                send_message(mock_bot, "999", "Hi", max_retries=3, retry_delay=1.0)
            )

        assert result["success"] is False
        assert result["message_id"] is None
        assert result["error"] == "Max retries exceeded"
        assert mock_bot.send_message.await_count == 3

    def test_send_message_network_error_then_success(
        self, mock_bot: AsyncMock
    ) -> None:
        """First call raises NetworkError, second succeeds."""
        msg = MagicMock()
        msg.message_id = 77
        mock_bot.send_message.side_effect = [NetworkError("conn reset"), msg]

        with patch("src.delivery.sender.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            result = asyncio.run(
                send_message(mock_bot, "999", "Test", retry_delay=2.0)
            )

        assert result["success"] is True
        assert result["message_id"] == 77
        # First attempt: delay = 2.0 * 2^0 = 2.0
        mock_sleep.assert_awaited_once_with(2.0)


# ---------------------------------------------------------------------------
# send_messages
# ---------------------------------------------------------------------------


class TestSendMessages:
    """Multi-message sending with rate limiting."""

    def test_send_messages_rate_limiting(self, mock_bot: AsyncMock) -> None:
        """Verify asyncio.sleep is called between messages for rate limiting."""
        msgs = ["Msg 1", "Msg 2", "Msg 3"]
        with patch("src.delivery.sender.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            results = asyncio.run(
                send_messages(mock_bot, "999", msgs, rate_limit=1.5)
            )

        assert len(results) == 3
        assert all(r["success"] for r in results)
        # Rate-limit sleeps between messages (2 sleeps for 3 messages)
        rate_calls = [c for c in mock_sleep.await_args_list if c.args == (1.5,)]
        assert len(rate_calls) == 2

    def test_send_messages_stops_on_failure(self, mock_bot: AsyncMock) -> None:
        """Second message fails, third should not be attempted."""
        msg_ok = MagicMock()
        msg_ok.message_id = 1
        mock_bot.send_message.side_effect = [msg_ok, TimedOut(), None]

        with patch("src.delivery.sender.asyncio.sleep", new_callable=AsyncMock):
            results = asyncio.run(
                send_messages(
                    mock_bot, "999", ["A", "B", "C"],
                    max_retries=1, retry_delay=0.1,
                )
            )

        # Only 2 results: first success, second failure; third never attempted
        assert len(results) == 2
        assert results[0]["success"] is True
        assert results[1]["success"] is False


# ---------------------------------------------------------------------------
# send_with_logging
# ---------------------------------------------------------------------------


class TestSendWithLogging:
    """Send + DB delivery_log integration."""

    def test_send_with_logging_success(self, mock_bot: AsyncMock, db) -> None:
        """Successful send updates delivery_log to 'sent'."""
        with patch("src.delivery.sender.asyncio.sleep", new_callable=AsyncMock):
            ok = asyncio.run(
                send_with_logging(
                    mock_bot, "999", ["Hello", "World"],
                    conn=db, cvr="12345678", domain="example.dk",
                )
            )

        assert ok is True

        row = db.execute(
            "SELECT * FROM delivery_log WHERE cvr = '12345678'"
        ).fetchone()
        assert row is not None
        assert row["status"] == "sent"
        assert row["error_message"] is None
        assert row["external_id"] == "42,42"
        assert row["sent_at"] is not None

    def test_send_with_logging_failure(self, mock_bot: AsyncMock, db) -> None:
        """All retries fail -- delivery_log shows 'failed' with error."""
        mock_bot.send_message.side_effect = TimedOut()

        with patch("src.delivery.sender.asyncio.sleep", new_callable=AsyncMock):
            ok = asyncio.run(
                send_with_logging(
                    mock_bot, "999", ["Fail msg"],
                    conn=db, cvr="12345678", domain="fail.dk",
                    max_retries=2,
                )
            )

        assert ok is False

        row = db.execute(
            "SELECT * FROM delivery_log WHERE cvr = '12345678'"
        ).fetchone()
        assert row is not None
        assert row["status"] == "failed"
        assert row["error_message"] == "Max retries exceeded"
        assert row["sent_at"] is None

    def test_send_with_logging_preview(self, mock_bot: AsyncMock, db) -> None:
        """Message preview is first 200 chars of the joined message text."""
        long_text = "A" * 300
        with patch("src.delivery.sender.asyncio.sleep", new_callable=AsyncMock):
            asyncio.run(
                send_with_logging(
                    mock_bot, "999", [long_text],
                    conn=db, cvr="12345678",
                )
            )

        row = db.execute(
            "SELECT message_preview FROM delivery_log WHERE cvr = '12345678'"
        ).fetchone()
        assert row is not None
        assert len(row["message_preview"]) == 200
        assert row["message_preview"] == "A" * 200
