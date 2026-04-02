"""Tests for the delivery runner (src.delivery.runner).

Verifies the scan-complete -> interpret -> compose -> deliver pipeline
without making real LLM calls or Telegram API requests.
"""

from __future__ import annotations

import asyncio
import json

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.db.clients import add_domain, create_client
from src.db.connection import init_db
from src.db.scans import save_brief_snapshot
from src.delivery.runner import DeliveryRunner


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_BRIEF_DICT = {
    "domain": "test.dk",
    "bucket": "A",
    "company_name": "Test Restaurant",
    "technology": {
        "cms": "WordPress",
        "hosting": "LiteSpeed",
        "server": "Apache",
        "ssl": {"valid": True, "issuer": "LE", "days_remaining": 90},
        "detected_plugins": [],
        "detected_themes": [],
    },
    "findings": [{"severity": "high", "description": "Missing HSTS"}],
    "subdomains": {"count": 0},
}

_INTERPRETED = {
    "findings": [{"title": "Missing HSTS header", "explanation": "...", "action": "Enable HSTS"}],
    "good_news": ["SSL certificate is valid"],
    "summary": "Your site has one issue to address.",
    "domain": "test.dk",
    "company_name": "Test Restaurant",
    "scan_date": "2026-04-02",
    "meta": {"tone": "balanced", "language": "da", "model": "test", "duration_ms": 50},
}

_COMPOSED = ["Security Report -- test.dk (2026-04-02)\n\nTest message content"]


@pytest.fixture()
def db(tmp_path):
    """Initialised client database with one test client + domain + brief."""
    conn = init_db(str(tmp_path / "test.db"))
    create_client(
        conn,
        "12345678",
        "Test Restaurant",
        telegram_chat_id="999888",
        status="active",
    )
    add_domain(conn, "12345678", "test.dk")
    save_brief_snapshot(
        conn, "test.dk", "2026-04-02", _BRIEF_DICT,
        company_name="Test Restaurant", cvr="12345678",
    )
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture()
def db_no_chat_id(tmp_path):
    """Client database with a client that has no telegram_chat_id."""
    conn = init_db(str(tmp_path / "test_nochat.db"))
    create_client(conn, "87654321", "No Chat Co", status="active")
    add_domain(conn, "87654321", "nochat.dk")
    save_brief_snapshot(
        conn, "nochat.dk", "2026-04-02", _BRIEF_DICT,
        company_name="No Chat Co", cvr="87654321",
    )
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture()
def db_no_brief(tmp_path):
    """Client database with a client but no brief snapshot."""
    conn = init_db(str(tmp_path / "test_nobrief.db"))
    create_client(
        conn, "11111111", "No Brief Co",
        telegram_chat_id="111222", status="active",
    )
    add_domain(conn, "11111111", "nobrief.dk")
    conn.commit()
    yield conn
    conn.close()


def _make_runner(conn, config: dict | None = None) -> DeliveryRunner:
    """Create a runner with the test DB connection injected."""
    runner = DeliveryRunner()
    runner._conn = conn
    runner.config = config or {"require_approval": True}
    runner._app = MagicMock()
    runner._app.bot = AsyncMock()
    runner._app.bot_data = {"db_conn": conn}
    return runner


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRunnerInit:
    """DeliveryRunner construction and config loading."""

    def test_runner_init_defaults(self) -> None:
        runner = DeliveryRunner()
        assert runner.redis_url == "redis://localhost:6379/0"
        assert runner.db_path is None
        assert runner._running is False
        assert runner._conn is None
        assert runner._app is None
        assert isinstance(runner.config, dict)

    def test_runner_init_custom_args(self, tmp_path) -> None:
        config_file = tmp_path / "delivery.json"
        config_file.write_text(json.dumps({"require_approval": False}))

        runner = DeliveryRunner(
            redis_url="redis://other:6380/1",
            db_path=str(tmp_path / "custom.db"),
            config_path=str(config_file),
        )
        assert runner.redis_url == "redis://other:6380/1"
        assert runner.db_path == str(tmp_path / "custom.db")
        assert runner.config["require_approval"] is False

    def test_runner_init_missing_config_uses_defaults(self) -> None:
        runner = DeliveryRunner(config_path="/nonexistent/path.json")
        assert runner.config["require_approval"] is True
        assert runner.config["retry_max"] == 3


class TestHandleScanCompleteNoClient:
    """Event for an unknown domain -- no client in DB."""

    @patch("src.delivery.runner.interpret_brief")
    @patch("src.delivery.runner.compose_telegram")
    @patch("src.delivery.runner.send_with_logging", new_callable=AsyncMock)
    @patch("src.delivery.runner.request_approval", new_callable=AsyncMock)
    def test_unknown_domain_no_send(
        self, mock_approval, mock_send, mock_compose, mock_interpret, db,
    ) -> None:
        runner = _make_runner(db)
        event = json.dumps({"domain": "unknown.dk", "job_id": "j-1"})

        asyncio.run(runner._handle_scan_complete(event))

        mock_interpret.assert_not_called()
        mock_compose.assert_not_called()
        mock_approval.assert_not_called()
        mock_send.assert_not_called()


class TestHandleScanCompleteNoChatId:
    """Client exists but has no telegram_chat_id."""

    @patch("src.delivery.runner.interpret_brief")
    @patch("src.delivery.runner.compose_telegram")
    @patch("src.delivery.runner.send_with_logging", new_callable=AsyncMock)
    @patch("src.delivery.runner.request_approval", new_callable=AsyncMock)
    def test_no_chat_id_no_send(
        self, mock_approval, mock_send, mock_compose, mock_interpret,
        db_no_chat_id,
    ) -> None:
        runner = _make_runner(db_no_chat_id)
        event = json.dumps({"domain": "nochat.dk", "job_id": "j-2"})

        asyncio.run(runner._handle_scan_complete(event))

        mock_interpret.assert_not_called()
        mock_compose.assert_not_called()
        mock_approval.assert_not_called()
        mock_send.assert_not_called()


class TestHandleScanCompleteApproval:
    """Client with chat_id, require_approval=True -- routes through approval."""

    @patch("src.delivery.runner.interpret_brief", return_value=_INTERPRETED)
    @patch("src.delivery.runner.compose_telegram", return_value=_COMPOSED)
    @patch("src.delivery.runner.request_approval", new_callable=AsyncMock)
    @patch("src.delivery.runner.get_operator_chat_id", return_value="op-123")
    def test_routes_through_approval(
        self, mock_op_id, mock_approval, mock_compose, mock_interpret, db,
    ) -> None:
        runner = _make_runner(db, config={"require_approval": True})
        event = json.dumps({"domain": "test.dk", "job_id": "j-3"})

        asyncio.run(runner._handle_scan_complete(event))

        mock_interpret.assert_called_once()
        mock_compose.assert_called_once_with(_INTERPRETED)
        mock_approval.assert_called_once()

        call_kwargs = mock_approval.call_args
        assert call_kwargs.args[1] == "op-123"  # operator_chat_id
        assert call_kwargs.kwargs["domain"] == "test.dk"
        assert call_kwargs.kwargs["cvr"] == "12345678"
        assert call_kwargs.kwargs["company_name"] == "Test Restaurant"


class TestHandleScanCompleteAutoSend:
    """require_approval=False -- sends directly to client."""

    @patch("src.delivery.runner.interpret_brief", return_value=_INTERPRETED)
    @patch("src.delivery.runner.compose_telegram", return_value=_COMPOSED)
    @patch("src.delivery.runner.send_with_logging", new_callable=AsyncMock)
    def test_auto_send_direct(
        self, mock_send, mock_compose, mock_interpret, db,
    ) -> None:
        runner = _make_runner(db, config={"require_approval": False})
        event = json.dumps({"domain": "test.dk", "job_id": "j-4"})

        asyncio.run(runner._handle_scan_complete(event))

        mock_interpret.assert_called_once()
        mock_compose.assert_called_once_with(_INTERPRETED)
        mock_send.assert_called_once()

        call_kwargs = mock_send.call_args
        assert call_kwargs.args[1] == "999888"  # client chat_id
        assert call_kwargs.kwargs["cvr"] == "12345678"
        assert call_kwargs.kwargs["domain"] == "test.dk"
        assert call_kwargs.kwargs["approved_by"] == "auto"


class TestHandleScanCompleteInvalidJson:
    """Malformed event data -- no crash, no send."""

    @patch("src.delivery.runner.interpret_brief")
    def test_invalid_json_no_crash(self, mock_interpret, db) -> None:
        runner = _make_runner(db)

        asyncio.run(runner._handle_scan_complete("not valid json {{{"))

        mock_interpret.assert_not_called()

    @patch("src.delivery.runner.interpret_brief")
    def test_empty_string_no_crash(self, mock_interpret, db) -> None:
        runner = _make_runner(db)

        asyncio.run(runner._handle_scan_complete(""))

        mock_interpret.assert_not_called()

    @patch("src.delivery.runner.interpret_brief")
    def test_missing_domain_no_crash(self, mock_interpret, db) -> None:
        runner = _make_runner(db)
        event = json.dumps({"job_id": "j-5", "status": "completed"})

        asyncio.run(runner._handle_scan_complete(event))

        mock_interpret.assert_not_called()


class TestHandleScanCompleteNoBrief:
    """Valid event but no brief in DB -- no send."""

    @patch("src.delivery.runner.interpret_brief")
    @patch("src.delivery.runner.send_with_logging", new_callable=AsyncMock)
    def test_no_brief_no_send(self, mock_send, mock_interpret, db_no_brief) -> None:
        runner = _make_runner(db_no_brief)
        event = json.dumps({"domain": "nobrief.dk", "job_id": "j-6"})

        asyncio.run(runner._handle_scan_complete(event))

        mock_interpret.assert_not_called()
        mock_send.assert_not_called()


class TestMainEntryPoint:
    """Verify the __main__.py entry point imports correctly."""

    def test_main_function_exists(self) -> None:
        from src.delivery.runner import main
        assert callable(main)

    def test_dunder_main_imports(self) -> None:
        from src.delivery.__main__ import main
        assert callable(main)
