"""Tests for operator approval flow (src.delivery.approval)."""

from __future__ import annotations

import asyncio

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.db.clients import create_client
from src.db.connection import init_db
from src.db.delivery import log_delivery, update_delivery_status
from src.delivery.approval import (
    _PENDING_MESSAGES_KEY,
    handle_approval_callback,
    request_approval,
    should_require_approval,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def db(tmp_path):
    """Initialised client database with one test client."""
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


@pytest.fixture()
def mock_bot():
    """AsyncMock Telegram Bot whose send_message returns a message with id."""
    bot = AsyncMock()
    msg = MagicMock()
    msg.message_id = 100
    bot.send_message.return_value = msg
    return bot


def _make_callback(data: str, message_text: str = "preview") -> tuple:
    """Build a mock (Update, ContextTypes.DEFAULT_TYPE) for callback tests.

    Returns (update, context) where context.bot sends messages that
    return message_id=200.
    """
    query = AsyncMock()
    query.data = data
    query.message = MagicMock()
    query.message.text = message_text

    update = MagicMock()
    update.callback_query = query

    context = MagicMock()
    context.bot = AsyncMock()
    msg = MagicMock()
    msg.message_id = 200
    context.bot.send_message.return_value = msg
    context.bot_data = {}
    return update, context


# ---------------------------------------------------------------------------
# request_approval
# ---------------------------------------------------------------------------


class TestRequestApproval:
    """Tests for request_approval()."""

    def test_creates_pending_delivery_log(self, db, mock_bot) -> None:
        """Calling request_approval creates a delivery_log entry with status='pending'."""
        delivery_id = asyncio.run(
            request_approval(
                bot=mock_bot,
                operator_chat_id="op_123",
                messages=["Hello, findings here."],
                cvr="12345678",
                domain="test.dk",
                conn=db,
            )
        )

        assert isinstance(delivery_id, int)
        assert delivery_id > 0

        row = db.execute(
            "SELECT * FROM delivery_log WHERE id = ?", (delivery_id,)
        ).fetchone()
        assert row["status"] == "pending"
        assert row["cvr"] == "12345678"
        assert row["channel"] == "telegram"
        assert row["domain"] == "test.dk"
        assert row["message_hash"] is not None

    def test_sends_exact_client_messages_to_operator(self, db, mock_bot) -> None:
        """Operator receives the exact message chunks the client would see."""
        asyncio.run(
            request_approval(
                bot=mock_bot,
                operator_chat_id="op_123",
                messages=["Finding 1", "Finding 2"],
                cvr="12345678",
                domain="test.dk",
                conn=db,
                company_name="Test Restaurant",
            )
        )

        # Two chunks = two send_message calls
        assert mock_bot.send_message.call_count == 2
        first_call = mock_bot.send_message.call_args_list[0]
        assert first_call.kwargs["chat_id"] == "op_123"
        assert first_call.kwargs["text"] == "Finding 1"
        assert first_call.kwargs["parse_mode"] == "HTML"

    def test_approve_reject_buttons_on_last_chunk(self, db, mock_bot) -> None:
        """Approve/Reject buttons are attached to the last message chunk only."""
        delivery_id = asyncio.run(
            request_approval(
                bot=mock_bot,
                operator_chat_id="op_123",
                messages=["Chunk 1", "Chunk 2"],
                cvr="12345678",
                domain="test.dk",
                conn=db,
            )
        )

        # First chunk: no buttons
        first_call = mock_bot.send_message.call_args_list[0]
        assert first_call.kwargs.get("reply_markup") is None

        # Last chunk: has Approve/Reject
        last_call = mock_bot.send_message.call_args_list[-1]
        markup = last_call.kwargs["reply_markup"]
        buttons = markup.inline_keyboard[0]
        assert len(buttons) == 2
        assert "Approve" in buttons[0].text
        assert buttons[0].callback_data == f"approve:{delivery_id}"
        assert "Reject" in buttons[1].text
        assert buttons[1].callback_data == f"reject:{delivery_id}"

    def test_stashes_full_messages_in_bot_data(self, db, mock_bot) -> None:
        """Full message chunks are stored in bot_data for later forwarding."""
        bot_data: dict = {}
        chunks = ["Part 1", "Part 2", "Part 3"]

        delivery_id = asyncio.run(
            request_approval(
                bot=mock_bot,
                operator_chat_id="op_123",
                messages=chunks,
                cvr="12345678",
                domain="test.dk",
                conn=db,
                bot_data=bot_data,
            )
        )

        assert _PENDING_MESSAGES_KEY in bot_data
        stashed = bot_data[_PENDING_MESSAGES_KEY][delivery_id]
        assert stashed["messages"] == chunks
        assert stashed["reply_markup"] is None

    def test_long_message_sent_as_is(self, db, mock_bot) -> None:
        """Long messages are sent exactly as the client would receive them."""
        long_msg = "x" * 5000
        asyncio.run(
            request_approval(
                bot=mock_bot,
                operator_chat_id="op_123",
                messages=[long_msg],
                cvr="12345678",
                domain="test.dk",
                conn=db,
            )
        )

        call_kwargs = mock_bot.send_message.call_args
        text = call_kwargs.kwargs["text"]
        assert text == long_msg

    def test_message_preview_stored_in_db(self, db, mock_bot) -> None:
        """The first 200 chars of the message are stored as message_preview."""
        msg = "A" * 300
        delivery_id = asyncio.run(
            request_approval(
                bot=mock_bot,
                operator_chat_id="op_123",
                messages=[msg],
                cvr="12345678",
                domain="test.dk",
                conn=db,
            )
        )

        row = db.execute(
            "SELECT message_preview FROM delivery_log WHERE id = ?",
            (delivery_id,),
        ).fetchone()
        assert len(row["message_preview"]) == 200

    def test_single_chunk_gets_buttons(self, db, mock_bot) -> None:
        """A single-chunk message gets Approve/Reject buttons directly."""
        asyncio.run(
            request_approval(
                bot=mock_bot,
                operator_chat_id="op_123",
                messages=["Finding"],
                cvr="12345678",
                domain="test.dk",
                conn=db,
                company_name="",
            )
        )

        mock_bot.send_message.assert_called_once()
        call_kwargs = mock_bot.send_message.call_args
        assert call_kwargs.kwargs["text"] == "Finding"
        assert call_kwargs.kwargs["reply_markup"] is not None


# ---------------------------------------------------------------------------
# should_require_approval
# ---------------------------------------------------------------------------


class TestShouldRequireApproval:
    """Tests for the approval toggle."""

    def test_true_by_default(self) -> None:
        """Default config returns True."""
        assert should_require_approval({"require_approval": True}) is True

    def test_true_when_missing_key(self) -> None:
        """Config without the key defaults to True (safe default)."""
        assert should_require_approval({}) is True

    def test_false_when_configured(self) -> None:
        """Explicit False disables approval."""
        assert should_require_approval({"require_approval": False}) is False

    def test_loads_from_file_when_none(self, tmp_path) -> None:
        """When config is None, load_config() is called."""
        with patch(
            "src.delivery.bot.load_config",
            return_value={"require_approval": False},
        ):
            result = should_require_approval(None)
            assert result is False


# ---------------------------------------------------------------------------
# handle_approval_callback — reject
# ---------------------------------------------------------------------------


class TestHandleReject:
    """Tests for the reject path."""

    def test_updates_status_to_rejected(self, db) -> None:
        """Simulated reject callback sets delivery_log.status='rejected'."""
        delivery_id = log_delivery(
            db, cvr="12345678", channel="telegram", message_type="scan_report",
            domain="test.dk",
        )

        update, context = _make_callback(
            f"reject:{delivery_id}", message_text="Preview text"
        )
        context.bot_data["db_conn"] = db

        asyncio.run(handle_approval_callback(update, context))

        row = db.execute(
            "SELECT status FROM delivery_log WHERE id = ?", (delivery_id,)
        ).fetchone()
        assert row["status"] == "rejected"

    def test_edits_operator_message_with_rejected_badge(self, db) -> None:
        """Operator's message is edited to show REJECTED header."""
        delivery_id = log_delivery(
            db, cvr="12345678", channel="telegram", message_type="scan_report",
            domain="test.dk",
        )

        update, context = _make_callback(
            f"reject:{delivery_id}", message_text="Original preview"
        )
        context.bot_data["db_conn"] = db

        asyncio.run(handle_approval_callback(update, context))

        query = update.callback_query
        query.edit_message_text.assert_called_once()
        edited_text = query.edit_message_text.call_args.args[0]
        assert edited_text.startswith("REJECTED")
        assert "Original preview" in edited_text


# ---------------------------------------------------------------------------
# handle_approval_callback — approve
# ---------------------------------------------------------------------------


class TestHandleApprove:
    """Tests for the approve path."""

    def test_sends_to_client_and_updates_status(self, db) -> None:
        """Approve sends message chunks to client, status='sent'."""
        delivery_id = log_delivery(
            db, cvr="12345678", channel="telegram", message_type="scan_report",
            domain="test.dk",
        )

        update, context = _make_callback(
            f"approve:{delivery_id}", message_text="Preview"
        )
        context.bot_data["db_conn"] = db
        context.bot_data[_PENDING_MESSAGES_KEY] = {
            delivery_id: ["Chunk 1", "Chunk 2"],
        }

        asyncio.run(handle_approval_callback(update, context))

        # Verify two messages sent to client's chat_id.
        assert context.bot.send_message.call_count == 2
        first_call = context.bot.send_message.call_args_list[0]
        assert first_call.kwargs["chat_id"] == "999888777"
        assert first_call.kwargs["text"] == "Chunk 1"

        second_call = context.bot.send_message.call_args_list[1]
        assert second_call.kwargs["text"] == "Chunk 2"

        # Verify DB status.
        row = db.execute(
            "SELECT status, external_id FROM delivery_log WHERE id = ?",
            (delivery_id,),
        ).fetchone()
        assert row["status"] == "sent"
        assert row["external_id"] == "200,200"

    def test_edits_operator_message_with_approved_badge(self, db) -> None:
        """Operator's message is edited to show APPROVED header."""
        delivery_id = log_delivery(
            db, cvr="12345678", channel="telegram", message_type="scan_report",
            domain="test.dk",
        )

        update, context = _make_callback(
            f"approve:{delivery_id}", message_text="Preview text"
        )
        context.bot_data["db_conn"] = db
        context.bot_data[_PENDING_MESSAGES_KEY] = {
            delivery_id: ["Message"],
        }

        asyncio.run(handle_approval_callback(update, context))

        query = update.callback_query
        query.edit_message_text.assert_called_once()
        edited_text = query.edit_message_text.call_args.args[0]
        assert edited_text.startswith("APPROVED")

    def test_missing_client_chat_id_fails_gracefully(self, db) -> None:
        """Client without telegram_chat_id results in 'failed' status."""
        # Create a client without a chat_id.
        create_client(db, "99999999", "No Chat Client", status="active")

        delivery_id = log_delivery(
            db, cvr="99999999", channel="telegram", message_type="scan_report",
            domain="nochat.dk",
        )

        update, context = _make_callback(f"approve:{delivery_id}")
        context.bot_data["db_conn"] = db
        context.bot_data[_PENDING_MESSAGES_KEY] = {
            delivery_id: ["Message"],
        }

        asyncio.run(handle_approval_callback(update, context))

        row = db.execute(
            "SELECT status, error_message FROM delivery_log WHERE id = ?",
            (delivery_id,),
        ).fetchone()
        assert row["status"] == "failed"
        assert "telegram_chat_id" in row["error_message"]

        # No messages sent to any client.
        context.bot.send_message.assert_not_called()

    def test_missing_client_record_fails_gracefully(self, db) -> None:
        """Delivery for non-existent CVR results in 'failed' status."""
        delivery_id = log_delivery(
            db, cvr="00000000", channel="telegram", message_type="scan_report",
            domain="ghost.dk",
        )

        update, context = _make_callback(f"approve:{delivery_id}")
        context.bot_data["db_conn"] = db
        context.bot_data[_PENDING_MESSAGES_KEY] = {
            delivery_id: ["Message"],
        }

        asyncio.run(handle_approval_callback(update, context))

        query = update.callback_query
        query.edit_message_text.assert_called_once()
        assert "not found" in query.edit_message_text.call_args.args[0]

    def test_missing_delivery_record_shows_error(self, db) -> None:
        """Approval for non-existent delivery_id shows an error."""
        update, context = _make_callback("approve:99999")
        context.bot_data["db_conn"] = db

        asyncio.run(handle_approval_callback(update, context))

        query = update.callback_query
        query.edit_message_text.assert_called_once()
        assert "not found" in query.edit_message_text.call_args.args[0]

    def test_fallback_to_preview_when_chunks_missing(self, db) -> None:
        """If bot restarted and chunks are gone, falls back to DB preview."""
        delivery_id = log_delivery(
            db, cvr="12345678", channel="telegram", message_type="scan_report",
            domain="test.dk", message_preview="Fallback preview text",
        )

        update, context = _make_callback(f"approve:{delivery_id}")
        context.bot_data["db_conn"] = db
        # No _PENDING_MESSAGES_KEY set -- simulates bot restart.

        asyncio.run(handle_approval_callback(update, context))

        # Should send the fallback preview to the client.
        context.bot.send_message.assert_called_once()
        sent_text = context.bot.send_message.call_args.kwargs["text"]
        assert sent_text == "Fallback preview text"

        row = db.execute(
            "SELECT status FROM delivery_log WHERE id = ?", (delivery_id,)
        ).fetchone()
        assert row["status"] == "sent"

    def test_send_failure_sets_failed_status(self, db) -> None:
        """If bot.send_message raises, delivery status becomes 'failed'."""
        delivery_id = log_delivery(
            db, cvr="12345678", channel="telegram", message_type="scan_report",
            domain="test.dk",
        )

        update, context = _make_callback(f"approve:{delivery_id}")
        context.bot_data["db_conn"] = db
        context.bot_data[_PENDING_MESSAGES_KEY] = {
            delivery_id: ["Message"],
        }
        context.bot.send_message.side_effect = RuntimeError("Telegram API down")

        asyncio.run(handle_approval_callback(update, context))

        row = db.execute(
            "SELECT status, error_message FROM delivery_log WHERE id = ?",
            (delivery_id,),
        ).fetchone()
        assert row["status"] == "failed"
        assert "Telegram API down" in row["error_message"]

    def test_chunks_removed_from_bot_data_after_approval(self, db) -> None:
        """Approved message chunks are removed from in-memory store."""
        delivery_id = log_delivery(
            db, cvr="12345678", channel="telegram", message_type="scan_report",
            domain="test.dk",
        )

        update, context = _make_callback(f"approve:{delivery_id}")
        pending = {delivery_id: ["Message"]}
        context.bot_data["db_conn"] = db
        context.bot_data[_PENDING_MESSAGES_KEY] = pending

        asyncio.run(handle_approval_callback(update, context))

        assert delivery_id not in pending


# ---------------------------------------------------------------------------
# handle_approval_callback — edge cases
# ---------------------------------------------------------------------------


class TestCallbackEdgeCases:
    """Edge cases for the callback handler."""

    def test_invalid_callback_data_ignored(self, db) -> None:
        """Callback data without ':' separator is silently ignored."""
        update, context = _make_callback("garbage")
        context.bot_data["db_conn"] = db

        # Should not raise.
        asyncio.run(handle_approval_callback(update, context))

    def test_non_integer_delivery_id_ignored(self, db) -> None:
        """Callback with non-numeric delivery_id is silently ignored."""
        update, context = _make_callback("approve:abc")
        context.bot_data["db_conn"] = db

        asyncio.run(handle_approval_callback(update, context))

    def test_missing_db_conn_shows_error(self) -> None:
        """If db_conn is not set in bot_data, an error is displayed."""
        update, context = _make_callback("approve:1")
        context.bot_data = {}

        asyncio.run(handle_approval_callback(update, context))

        query = update.callback_query
        query.edit_message_text.assert_called_once()
        assert "database" in query.edit_message_text.call_args.args[0].lower()

    def test_unknown_action_ignored(self, db) -> None:
        """Callback with unrecognised action prefix is silently ignored."""
        update, context = _make_callback("delete:1")
        context.bot_data["db_conn"] = db

        asyncio.run(handle_approval_callback(update, context))

        query = update.callback_query
        # answer() called, but no edit.
        query.edit_message_text.assert_not_called()
