"""End-to-end Telegram test using Telethon.

Sends a test message from the Heimdall bot, receives it as a user via
Telethon, clicks inline buttons, and verifies the bot's response.

First run requires interactive auth (phone + SMS code).
Subsequent runs use the saved session file.

Requirements: pip install telethon

Usage:
    python3 scripts/test_telegram_e2e.py
    python3 scripts/test_telegram_e2e.py --click-fix   # test "Can Heimdall fix this?" instead
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys

# ---------------------------------------------------------------------------
# Env-var check (fail fast before any heavy imports)
# ---------------------------------------------------------------------------

_REQUIRED_ENV = {
    "TELEGRAM_BOT_TOKEN": "Bot token from @BotFather",
    "TELEGRAM_OPERATOR_CHAT_ID": "Chat ID where the bot sends test messages",
    "TELETHON_API_ID": "API ID from my.telegram.org",
    "TELETHON_API_HASH": "API hash from my.telegram.org",
}

_missing = [k for k in _REQUIRED_ENV if not os.environ.get(k)]
if _missing:
    print("Missing required environment variables:\n")
    for k in _missing:
        print(f"  {k} — {_REQUIRED_ENV[k]}")
    print("\nSet them and retry.")
    sys.exit(1)

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = int(os.environ["TELEGRAM_OPERATOR_CHAT_ID"])
API_ID = int(os.environ["TELETHON_API_ID"])
API_HASH = os.environ["TELETHON_API_HASH"]
SESSION = os.environ.get("TELETHON_SESSION", "test_session")

# ---------------------------------------------------------------------------
# Heavy imports (only after env check passes)
# ---------------------------------------------------------------------------

from telegram import Bot  # noqa: E402
from telegram.ext import (  # noqa: E402
    Application,
    CallbackQueryHandler,
)
from telethon import TelegramClient  # noqa: E402
from telethon.events import NewMessage  # noqa: E402

# Project imports
from src.composer.telegram import compose_telegram  # noqa: E402
from src.delivery.buttons import (  # noqa: E402
    build_client_buttons,
    handle_client_callback,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Static fixture — no LLM needed
# ---------------------------------------------------------------------------

SAMPLE_INTERPRETED = {
    "domain": "test.example.dk",
    "company_name": "Test Company",
    "contact_name": "Martin",
    "scan_date": "2026-04-03",
    "findings": [
        {
            "title": "Your website login is exposed to the internet",
            "severity": "critical",
            "explanation": (
                "Anyone can access the admin login page, making it a target "
                "for automated attacks."
            ),
            "action": (
                "Restrict wp-login.php access by IP or add two-factor "
                "authentication."
            ),
            "who": "developer",
            "provenance": "confirmed",
        },
        {
            "title": "A component on your website may have a known security flaw",
            "severity": "high",
            "explanation": (
                "The detected version of a website component is known to be "
                "associated with a security vulnerability."
            ),
            "action": (
                "Update LiteSpeed Cache plugin to version 6.5.0.1 or later "
                "(CVE-2024-44000)."
            ),
            "who": "developer",
            "provenance": "unconfirmed",
        },
    ],
}


# ---------------------------------------------------------------------------
# Bot side — PTB Application with callback handler
# ---------------------------------------------------------------------------


async def _run_bot(app: Application, message_html: str, reply_markup) -> int:
    """Start the bot, send the test message, and return the message ID."""
    bot: Bot = app.bot

    print("Sending test message...")
    sent = await bot.send_message(
        chat_id=CHAT_ID,
        text=message_html,
        parse_mode="HTML",
        reply_markup=reply_markup,
    )
    log.info("Message sent, message_id=%d", sent.message_id)
    return sent.message_id


# ---------------------------------------------------------------------------
# Client side — Telethon listener
# ---------------------------------------------------------------------------


async def _wait_for_message(
    client: TelegramClient,
    bot_id: int,
    timeout: float = 15.0,
):
    """Wait for a new message from the bot. Returns the Telethon message."""
    future: asyncio.Future = asyncio.get_event_loop().create_future()

    @client.on(NewMessage(from_users=bot_id))
    async def _handler(event):
        if not future.done():
            future.set_result(event.message)

    try:
        return await asyncio.wait_for(future, timeout=timeout)
    except asyncio.TimeoutError:
        return None
    finally:
        client.remove_event_handler(_handler)


# ---------------------------------------------------------------------------
# Main flow
# ---------------------------------------------------------------------------


async def main() -> None:
    parser = argparse.ArgumentParser(description="Telegram E2E test")
    parser.add_argument(
        "--click-fix",
        action="store_true",
        help='Click "Can Heimdall fix this?" instead of "Got it"',
    )
    args = parser.parse_args()
    button_index = 1 if args.click_fix else 0
    button_label = "Can Heimdall fix this?" if args.click_fix else "Got it"

    # Compose message
    messages = compose_telegram(SAMPLE_INTERPRETED)
    message_html = messages[0]
    reply_markup = build_client_buttons("00000000", "test.example.dk")

    # Build PTB Application (with callback handler for button presses)
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )
    app.add_handler(
        CallbackQueryHandler(handle_client_callback, pattern=r"^(got_it|fix_it):")
    )

    # Initialise and start polling so the bot can receive callback queries
    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)

    # Telethon client
    client = TelegramClient(SESSION, API_ID, API_HASH)
    await client.start()

    bot_user = await app.bot.get_me()
    bot_id = bot_user.id

    ok = False
    try:
        # Send message from bot
        msg_id = await _run_bot(app, message_html, reply_markup)

        # Wait for message via Telethon
        print("Waiting for message via Telethon...")
        msg = await _wait_for_message(client, bot_id, timeout=15.0)
        if msg is None:
            print("FAIL: Timed out waiting for bot message (15s)")
            sys.exit(1)

        print(f"Message received (id={msg.id})")

        # Verify message content
        text = msg.raw_text or ""
        errors = []
        if "Confirmed issues" not in text:
            errors.append('Missing "Confirmed issues" section')
        if "Potential issues" not in text:
            errors.append('Missing "Potential issues" section')
        if "\U0001f534" not in text and "Critical" not in text:
            errors.append("Missing critical severity indicator")
        if "\U0001f7e0" not in text and "High" not in text:
            errors.append("Missing high severity indicator")

        # Check buttons exist
        if not msg.buttons:
            errors.append("No inline buttons found on message")
        else:
            button_texts = [b.text for row in msg.buttons for b in row]
            if "Got it" not in " ".join(button_texts):
                errors.append('"Got it" button not found')

        if errors:
            print("FAIL: Content verification errors:")
            for e in errors:
                print(f"  - {e}")
            sys.exit(1)

        print("Content verified OK")

        # Click button
        print(f'Clicking button [{button_index}]: "{button_label}"...')
        await msg.click(button_index)

        # Wait for bot to edit the message
        print("Waiting 3s for bot to process callback...")
        await asyncio.sleep(3)

        # Re-fetch the message to see edits
        edited = await client.get_messages(CHAT_ID, ids=msg.id)
        if edited is None:
            print("FAIL: Could not re-fetch message after button click")
            sys.exit(1)

        edited_text = edited.raw_text or ""
        if args.click_fix:
            expected = "We'll be in touch"
            if expected not in edited_text:
                print(
                    f'FAIL: Expected "{expected}" in edited message, '
                    f"got:\n{edited_text[-200:]}"
                )
                sys.exit(1)
            print("PASS: Fix-request response verified")
        else:
            expected = "Acknowledged"
            if expected not in edited_text:
                print(
                    f'FAIL: Expected "{expected}" in edited message, '
                    f"got:\n{edited_text[-200:]}"
                )
                sys.exit(1)
            print("PASS: Button response verified")

        ok = True

    finally:
        # Cleanup
        print("Cleaning up...")
        try:
            await app.updater.stop()
            await app.stop()
            await app.shutdown()
        except Exception:
            pass
        await client.disconnect()

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    asyncio.run(main())
