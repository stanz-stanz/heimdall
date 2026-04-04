"""End-to-end Telegram test using Telethon.

Sends a test message from the Heimdall bot, receives it as a user via
Telethon, clicks inline buttons, and verifies the bot's response.

Uses a real brief (from data/output/briefs/) interpreted by the LLM,
not a hardcoded fixture.

First run requires interactive auth (phone + SMS code).
Subsequent runs use the saved session file.

Requirements: pip install telethon

Usage:
    python3 scripts/test_telegram_e2e.py
    python3 scripts/test_telegram_e2e.py --brief data/output/briefs/jellingkro.dk.json
    python3 scripts/test_telegram_e2e.py --click-fix   # test "Can Heimdall fix this?" instead
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
load_dotenv()

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
from src.interpreter.interpreter import interpret_brief  # noqa: E402

from loguru import logger  # noqa: E402
from src.prospecting.logging_config import setup_logging  # noqa: E402

setup_logging(level="INFO")

BRIEFS_DIR = Path("data/output/briefs")


def _pick_richest_brief() -> Path:
    """Return the brief file with the most high/critical findings."""
    best_path = None
    best_count = -1
    for p in BRIEFS_DIR.glob("*.json"):
        try:
            brief = json.loads(p.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        count = sum(
            1 for f in brief.get("findings", [])
            if f.get("severity", "").lower() in ("critical", "high")
        )
        if count > best_count:
            best_count = count
            best_path = p
    if best_path is None:
        print(f"ERROR: No brief files found in {BRIEFS_DIR}")
        sys.exit(1)
    return best_path


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
    logger.info("Message sent, message_id={}", sent.message_id)
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
        "--brief",
        help="Path to a brief JSON file (default: auto-pick richest brief)",
    )
    parser.add_argument(
        "--contact-name",
        default="Martin",
        help="Contact name for greeting (default: Martin)",
    )
    parser.add_argument(
        "--language",
        default=None,
        help="Language override (en/da)",
    )
    parser.add_argument(
        "--click-fix",
        action="store_true",
        help='Click "Can Heimdall fix this?" instead of "Got it"',
    )
    args = parser.parse_args()
    button_index = 1 if args.click_fix else 0
    button_label = "Can Heimdall fix this?" if args.click_fix else "Got it"

    # Load brief
    if args.brief:
        brief_path = Path(args.brief)
    else:
        brief_path = _pick_richest_brief()
    with open(brief_path) as f:
        brief = json.load(f)
    print(f"Brief: {brief_path.name}")

    # Pre-filter to high/critical (same as delivery runner)
    all_findings = brief.get("findings", [])
    actionable = [
        f for f in all_findings
        if f.get("severity", "").lower() in ("critical", "high")
    ]
    brief["findings"] = actionable
    print(f"Findings: {len(all_findings)} total -> {len(actionable)} high/critical")

    if not actionable:
        print("ERROR: No high/critical findings in this brief. Pick another.")
        sys.exit(1)

    # Interpret via LLM
    print("Interpreting via LLM...")
    interpreted = interpret_brief(brief, language=args.language)
    interpreted["contact_name"] = args.contact_name
    print(f"Interpreter returned {len(interpreted.get('findings', []))} findings")

    # Compose message
    domain = brief.get("domain", "unknown")
    messages = compose_telegram(interpreted)
    message_html = messages[0]
    reply_markup = build_client_buttons("00000000", domain)

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
        # Set up listener BEFORE sending so we don't miss the message
        print("Waiting for message via Telethon...")
        listen_task = asyncio.create_task(
            _wait_for_message(client, bot_id, timeout=15.0)
        )
        await asyncio.sleep(0.3)  # let the handler register

        # Send message from bot
        msg_id = await _run_bot(app, message_html, reply_markup)

        msg = await listen_task
        if msg is None:
            print("FAIL: Timed out waiting for bot message (15s)")
            sys.exit(1)

        print(f"Message received (id={msg.id})")

        # Verify message content against what the interpreter actually returned
        text = msg.raw_text or ""
        findings = interpreted.get("findings", [])
        has_confirmed = any(f.get("provenance") == "confirmed" for f in findings)
        has_potential = any(f.get("provenance") != "confirmed" for f in findings)
        has_critical = any(f.get("severity", "").lower() == "critical" for f in findings)
        has_high = any(f.get("severity", "").lower() == "high" for f in findings)

        errors = []
        if has_confirmed and "Confirmed" not in text:
            errors.append('Missing "Confirmed" section')
        if has_potential and "Potential" not in text:
            errors.append('Missing "Potential" section')
        if has_critical and "Critical" not in text:
            errors.append("Missing critical severity indicator")
        if has_high and "High" not in text:
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

        # Verify bot response
        if args.click_fix:
            # Bot should reply with a separate message
            print("Waiting for bot reply...")
            reply = await _wait_for_message(client, bot_id, timeout=10.0)
            if reply is None:
                print("FAIL: No reply from bot after fix-it click")
                sys.exit(1)
            reply_text = reply.raw_text or ""
            expected = "One of our developers will contact you soon."
            if expected not in reply_text:
                print(
                    f'FAIL: Expected "{expected}", '
                    f"got: {reply_text}"
                )
                sys.exit(1)
            print("PASS: Fix-request reply verified")
        else:
            # "Got it" — no visible response, just log silently
            print("PASS: Got-it acknowledged (no visible response expected)")

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
