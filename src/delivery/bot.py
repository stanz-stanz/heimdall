"""Telegram bot setup and configuration.

The delivery bot sends scan report messages to clients and handles
operator approval callbacks. It runs as a separate process from the
scan worker.

Configuration:
    TELEGRAM_BOT_TOKEN -- env var (required)
    TELEGRAM_OPERATOR_CHAT_ID -- env var (required for approval flow)
    config/delivery.json -- approval toggle, retry settings
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from telegram import Bot
from telegram.ext import Application, CallbackQueryHandler

log = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "delivery.json"

_DEFAULT_CONFIG: dict = {
    "require_approval": True,
    "retry_max": 3,
    "retry_delay_seconds": 5,
    "rate_limit_per_second": 1,
}


def load_config(config_path: Path | str | None = None) -> dict:
    """Load delivery config from JSON file, with defaults.

    Args:
        config_path: Override path to a JSON config file.
            Falls back to ``config/delivery.json`` in the project root.

    Returns:
        Merged config dict (file values override defaults).
    """
    path = Path(config_path) if config_path else _CONFIG_PATH
    config = dict(_DEFAULT_CONFIG)
    try:
        with open(path, "r", encoding="utf-8") as f:
            file_config = json.load(f)
        if isinstance(file_config, dict):
            config.update(file_config)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        log.warning("delivery_config_not_found, using defaults")
    return config


def get_bot_token() -> str:
    """Get bot token from environment.

    Raises:
        RuntimeError: If ``TELEGRAM_BOT_TOKEN`` is not set or empty.
    """
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN not set. "
            "Set it in your environment or .env file."
        )
    return token


def get_operator_chat_id() -> str:
    """Get operator's Telegram chat ID from environment.

    Raises:
        RuntimeError: If ``TELEGRAM_OPERATOR_CHAT_ID`` is not set or empty.
    """
    chat_id = os.environ.get("TELEGRAM_OPERATOR_CHAT_ID", "")
    if not chat_id:
        raise RuntimeError(
            "TELEGRAM_OPERATOR_CHAT_ID not set. "
            "Start a conversation with the bot and set the chat ID."
        )
    return chat_id


def create_application(token: str | None = None) -> Application:
    """Create a Telegram Application (bot + dispatcher).

    The Application manages the bot lifecycle, handler registration,
    and the polling loop. Handlers for approval callbacks are registered
    by the approval module.

    Args:
        token: Bot token override. Reads from env if not provided.

    Returns:
        Configured ``telegram.ext.Application`` instance, not yet started.
    """
    bot_token = token or get_bot_token()
    app = Application.builder().token(bot_token).build()
    log.info("telegram_application_created")
    return app
