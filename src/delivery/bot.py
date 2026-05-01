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
import os
from pathlib import Path

from loguru import logger
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from src.core.secrets import get_secret
from src.db.audit_context import bind_audit_context
from src.db.connection import init_db
from src.db.onboarding import InvalidSignupToken, activate_watchman_trial

_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "delivery.json"

_DEFAULT_CONFIG: dict = {
    "require_approval": True,
    "retry_max": 3,
    "retry_delay_seconds": 5,
    "rate_limit_per_second": 1,
}

# ---------------------------------------------------------------------------
# /start command copy
# ---------------------------------------------------------------------------
#
# Source of truth: /Users/fsaf/.claude/plans/i-need-you-to-logical-pebble.md
# ("Message 1 — Watchman trial kickoff", Telegram variant). EN copy
# approved by Federico 2026-04-24.
#
# We intentionally do not substitute {{first_name}} / {{domain}} at /start
# time — those live in the composer layer (later message) and the trial
# kickoff is the same for every client.

_MSG1_WATCHMAN_KICKOFF_DA = (
    "Hej — forbindelsen er oppe.\n\n"
    "Første scanning kører i nat. Du hører fra mig i morgen tidlig, "
    "hvis der er noget at sige. Ellers holder jeg stille.\n\n"
    "Prøven er gratis i 30 dage. Den stopper af sig selv."
)

_MSG1_WATCHMAN_KICKOFF_EN = (
    "Hi — your Watchman connection is live.\n\n"
    "The first scan runs tonight. I'll message you tomorrow morning if "
    "there's anything worth saying. Otherwise I'll stay quiet.\n\n"
    "The trial is free for 30 days. It ends on its own."
)

# Generic "link is invalid / expired" copy. Default language is English
# per project convention (feedback_default_language_english.md): EN is
# the fallback; DA is a per-client override. Error paths don't have a
# client row yet, so we reply in EN.
_MSG_INVALID_LINK_EN = (
    "The link has expired or is no longer valid. "
    "Reply to the email and I'll send a new one."
)

# Neutral fallback when activation blows up for non-token reasons
# (e.g. missing company_name for a never-seen CVR).
_MSG_ACTIVATION_FAILED_EN = (
    "We couldn't start the trial right now. "
    "Reply to the email and I'll help you get going."
)


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
        with open(path, encoding="utf-8") as f:
            file_config = json.load(f)
        if isinstance(file_config, dict):
            config.update(file_config)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        logger.warning("delivery_config_not_found, using defaults")
    return config


def get_bot_token() -> str:
    """Get bot token from the compose secret or env fallback.

    Raises:
        RuntimeError: If ``TELEGRAM_BOT_TOKEN`` is not set or empty.
    """
    token = get_secret("telegram_bot_token", "TELEGRAM_BOT_TOKEN")
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
    logger.info("telegram_application_created")
    return app


# ---------------------------------------------------------------------------
# /start — Watchman-trial magic-link redemption
# ---------------------------------------------------------------------------


def _kickoff_message_for(language: str | None) -> str:
    """Pick the Message 1 (Watchman kickoff) body for ``language``.

    Defaults to English when ``language`` is falsy or unrecognised.
    """
    if (language or "").lower() == "da":
        return _MSG1_WATCHMAN_KICKOFF_DA
    return _MSG1_WATCHMAN_KICKOFF_EN


async def handle_start_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle ``/start <token>`` — redeem magic link and send kickoff.

    Flow:
        1. Parse the single token argument. Missing → generic "invalid
           link" reply in EN (default language, no client row yet).
        2. Open the client DB and call ``activate_watchman_trial``.
        3. On ``InvalidSignupToken`` → generic "invalid link" reply (EN).
        4. On ``ValueError`` (missing company_name for new CVR) → log
           WARNING + neutral "please reply to the email" reply (EN).
        5. On success → send Message 1 in the client's preferred
           language (default EN).

    The token is never echoed back to the user. All diagnostic detail
    goes to the logger, not to the Telegram reply.
    """
    chat = update.effective_chat
    if chat is None:  # pragma: no cover — defensive, Telegram always supplies
        logger.warning("start_command_without_chat")
        return

    args = context.args or []
    if not args:
        logger.bind(context={"chat_id": chat.id}).info("start_without_token")
        await context.bot.send_message(chat_id=chat.id, text=_MSG_INVALID_LINK_EN)
        return

    token = args[0]
    db_path = context.application.bot_data.get("db_path")

    # Use the in-memory/injected connection when a test or caller has
    # pre-populated it; otherwise open a fresh connection to the
    # configured client DB. Never close an injected connection — ownership
    # stays with the caller.
    injected_conn = context.application.bot_data.get("db_conn")
    owns_conn = injected_conn is None
    conn = injected_conn if injected_conn is not None else init_db(db_path) if db_path else init_db()

    try:
        try:
            # Stage A.5 spec §4.1.5: wrap the signup_token consume +
            # clients UPDATE/INSERT under one ``trial.activated`` intent.
            # actor_kind='system' because the Telegram bot is not an
            # operator — the audit row attribution stays clean. The
            # trigger on signup_tokens (UPDATE consumed_at) and clients
            # (UPDATE/INSERT status/plan/...) both inherit this stamp.
            with bind_audit_context(
                conn,
                intent="trial.activated",
                actor_kind="system",
            ):
                client = activate_watchman_trial(
                    conn, token=token, telegram_chat_id=str(chat.id)
                )
        except InvalidSignupToken:
            logger.bind(context={"chat_id": chat.id}).info(
                "start_token_invalid_or_expired"
            )
            await context.bot.send_message(
                chat_id=chat.id, text=_MSG_INVALID_LINK_EN
            )
            return
        except ValueError:
            # New CVR with no company_name attached to the token row.
            # Surface loudly in the log so the operator can follow up.
            logger.bind(context={"chat_id": chat.id}).warning(
                "start_activation_missing_company_name"
            )
            await context.bot.send_message(
                chat_id=chat.id, text=_MSG_ACTIVATION_FAILED_EN
            )
            return

        language = client.get("preferred_language")
        body = _kickoff_message_for(language)
        await context.bot.send_message(chat_id=chat.id, text=body)
        logger.bind(context={
            "chat_id": chat.id,
            "cvr": client.get("cvr"),
            "language": language,
        }).info("watchman_trial_activated")
    finally:
        if owns_conn:
            try:
                conn.close()
            except Exception:  # pragma: no cover — best-effort cleanup
                logger.opt(exception=True).debug("start_conn_close_failed")


def register_start_handler(app: Application) -> None:
    """Register the ``/start`` command handler on ``app``.

    Callers should invoke this alongside the existing callback-query
    handler registrations (see ``src.delivery.runner``). Kept separate
    from :func:`create_application` so tests can build an Application,
    register only the handlers they need, and skip network setup.
    """
    app.add_handler(CommandHandler("start", handle_start_command))
    logger.info("start_command_handler_registered")
