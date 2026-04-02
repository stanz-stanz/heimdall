"""Quick delivery test — seeds a client, saves a brief, publishes event.

Run inside the delivery container or on the Pi5 host:

    python3 scripts/test_delivery.py [--redis-url redis://redis:6379/0] [--db-path data/clients/clients.db]

What it does:
    1. Creates a test client (CVR 99999999) with YOUR operator chat ID
    2. Saves a realistic brief for jellingkro.dk
    3. Publishes a scan-complete event on Redis

After running, check your Telegram — you should see an approval request.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import redis

from src.db.connection import init_db
from src.db.clients import create_client, add_domain, get_client
from src.db.scans import save_brief_snapshot


SAMPLE_BRIEF = {
    "domain": "jellingkro.dk",
    "bucket": "A",
    "company_name": "Jelling Kro",
    "scan_date": "2026-04-02",
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


def main():
    parser = argparse.ArgumentParser(description="Test delivery pipeline end-to-end")
    parser.add_argument("--redis-url", default=os.environ.get("REDIS_URL", "redis://localhost:6379/0"))
    parser.add_argument("--db-path", default="data/clients/clients.db")
    args = parser.parse_args()

    chat_id = os.environ.get("TELEGRAM_OPERATOR_CHAT_ID", "")
    if not chat_id:
        print("ERROR: TELEGRAM_OPERATOR_CHAT_ID not set in environment")
        sys.exit(1)

    # Seed DB
    conn = init_db(args.db_path)

    if get_client(conn, "99999999"):
        print("Test client already exists, skipping seed")
    else:
        create_client(conn, "99999999", "Jelling Kro",
                      telegram_chat_id=chat_id, status="active", plan="watchman")
        add_domain(conn, "99999999", "jellingkro.dk")
        print(f"Created test client (CVR 99999999, chat_id={chat_id})")

    save_brief_snapshot(conn, "jellingkro.dk", "2026-04-02", SAMPLE_BRIEF,
                        company_name="Jelling Kro", cvr="99999999")
    conn.commit()
    print("Saved brief for jellingkro.dk")

    # Publish event
    r = redis.from_url(args.redis_url, decode_responses=True)
    event = {"domain": "jellingkro.dk", "job_id": "test-001",
             "client_id": "99999999", "status": "completed"}
    r.publish("scan-complete", json.dumps(event))
    print("Published scan-complete event — check your Telegram")


if __name__ == "__main__":
    main()
