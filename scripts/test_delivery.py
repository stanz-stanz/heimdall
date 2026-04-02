"""Quick delivery test — seeds a client, saves a brief, publishes event.

Run inside the delivery container:

    python3 scripts/test_delivery.py

What it does:
    1. Creates or updates a test client (CVR 99999999) with YOUR operator chat ID
    2. Saves a realistic brief for jellingkro.dk
    3. Publishes a scan-complete event on Redis

After running, check your Telegram — you should see an approval request.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import uuid
from datetime import date

import redis

from src.db.connection import init_db
from src.db.clients import create_client, add_domain, get_client, update_client
from src.db.scans import save_brief_snapshot


SAMPLE_BRIEF = {
    "domain": "jellingkro.dk",
    "bucket": "A",
    "company_name": "Jelling Kro",
    "industry": "Restaurant",
    "technology": {
        "cms": "WordPress",
        "hosting": "LiteSpeed",
        "server": "LiteSpeed/6.0",
        "ssl": {"valid": True, "issuer": "Let's Encrypt", "days_remaining": 45},
        "detected_plugins": ["yoast-seo", "woocommerce", "contact-form-7"],
        "detected_themes": ["flavor"],
    },
    "findings": [
        {"severity": "high", "description": "Missing HSTS header", "risk": "Browser connections not forced to HTTPS"},
        {"severity": "medium", "description": "Missing Content-Security-Policy header"},
        {"severity": "info", "description": "Server version disclosed: LiteSpeed/6.0"},
    ],
    "subdomains": {"count": 2},
}


def _detect_defaults():
    """Auto-detect paths based on whether we're inside Docker or on the host."""
    if os.path.isdir("/data/clients"):
        return "/data/clients/clients.db", "redis://redis:6379/0"
    return "data/clients/clients.db", os.environ.get("REDIS_URL", "redis://localhost:6379/0")


def main():
    default_db, default_redis = _detect_defaults()

    parser = argparse.ArgumentParser(description="Test delivery pipeline end-to-end")
    parser.add_argument("--redis-url", default=os.environ.get("REDIS_URL", default_redis))
    parser.add_argument("--db-path", default=default_db)
    args = parser.parse_args()

    chat_id = os.environ.get("TELEGRAM_OPERATOR_CHAT_ID", "")
    if not chat_id:
        print("ERROR: TELEGRAM_OPERATOR_CHAT_ID not set in environment")
        sys.exit(1)

    conn = init_db(args.db_path)

    # Create or update test client — always ensure chat_id is correct
    existing = get_client(conn, "99999999")
    if existing:
        if existing.get("telegram_chat_id") != chat_id:
            update_client(conn, "99999999", {"telegram_chat_id": chat_id})
            print(f"Updated test client chat_id to {chat_id}")
        else:
            print("Test client exists with correct chat_id")
    else:
        create_client(conn, "99999999", "Jelling Kro",
                      telegram_chat_id=chat_id, status="active", plan="watchman")
        add_domain(conn, "99999999", "jellingkro.dk")
        print(f"Created test client (CVR 99999999, chat_id={chat_id})")

    # Save brief — use unique scan_date to avoid UNIQUE constraint
    scan_date = date.today().isoformat()
    brief = dict(SAMPLE_BRIEF)
    brief["scan_date"] = scan_date
    try:
        save_brief_snapshot(conn, "jellingkro.dk", scan_date, brief,
                            company_name="Jelling Kro", cvr="99999999")
    except sqlite3.IntegrityError:
        # Already exists for today — that's fine
        pass
    conn.commit()
    print(f"Brief ready for jellingkro.dk ({scan_date})")

    # Publish event
    r = redis.from_url(args.redis_url, decode_responses=True)
    event = {"domain": "jellingkro.dk", "job_id": f"test-{uuid.uuid4().hex[:6]}",
             "client_id": "99999999", "status": "completed"}
    r.publish("scan-complete", json.dumps(event))
    print("Published scan-complete event — check your Telegram")


if __name__ == "__main__":
    main()
