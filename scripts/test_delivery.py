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
    "industry": "Restaurant with online booking and webshop",
    "gdpr_sensitive": True,
    "gdpr_reasons": [
        "Data-handling plugins: Woocommerce, Contact Form 7",
        "E-commerce plugin: WooCommerce:9.6.4",
    ],
    "technology": {
        "cms": "WordPress",
        "hosting": "LiteSpeed",
        "server": "LiteSpeed",
        "ssl": {"valid": True, "issuer": "Sectigo Limited", "expiry": "2027-01-21", "days_remaining": 295},
        "detected_plugins": [
            "Woocommerce", "Custom Facebook Feed", "Instagram Feed",
            "Contact Form 7", "Elementor", "Cookie Law Info",
            "Litespeed Cache", "Wordpress Seo",
        ],
        "plugin_versions": {
            "Contact Form 7": "6.0.3",
            "Elementor": "3.27.3",
            "Woocommerce": "9.6.4",
        },
        "detected_themes": [],
        "headers": {
            "x_frame_options": False,
            "content_security_policy": False,
            "strict_transport_security": False,
            "x_content_type_options": False,
        },
    },
    "subdomains": {"count": 0},
    "findings": [
        {
            "severity": "critical",
            "description": "LiteSpeed Cache [litespeed-cache] < 6.4 (CVE-2024-28000)",
            "risk": "CVE-2024-28000: WordPress LiteSpeed Cache Plugin <= 6.3.0.1 is vulnerable to Privilege Escalation",
            "provenance": "twin-derived",
            "provenance_detail": {"source_layer": 1, "twin_scan_tool": "wpvulnerability",
                                  "template_id": "CVE-2024-28000", "confidence": "medium-inference"},
        },
        {
            "severity": "critical",
            "description": "LiteSpeed Cache [litespeed-cache] < 6.5.0.1 (CVE-2024-44000)",
            "risk": "CVE-2024-44000: WordPress LiteSpeed Cache Plugin < 6.5.0.1 is vulnerable to Broken Authentication",
            "provenance": "twin-derived",
            "provenance_detail": {"source_layer": 1, "twin_scan_tool": "wpvulnerability",
                                  "template_id": "CVE-2024-44000", "confidence": "medium-inference"},
        },
        {
            "severity": "high",
            "description": "Data-handling plugins detected: Woocommerce, Contact Form 7",
            "risk": "These plugins collect or process user data (form submissions, payments). If the site or plugin has a vulnerability, this data could be exposed.",
        },
        {
            "severity": "high",
            "description": "Elementor Website Builder [elementor] >= 3.6.0 - <= 3.6.2 (CVE-2022-1329)",
            "risk": "CVE-2022-1329: WordPress Elementor Website Builder plugin <= 3.6.2 - Arbitrary File Upload vulnerability",
            "provenance": "twin-derived",
            "provenance_detail": {"source_layer": 1, "twin_scan_tool": "wpvulnerability",
                                  "template_id": "CVE-2022-1329", "confidence": "high-inference"},
        },
        {
            "severity": "medium",
            "description": "Missing HSTS header (HTTP Strict Transport Security)",
            "risk": "Browsers are not instructed to always use HTTPS.",
        },
        {
            "severity": "medium",
            "description": "Outdated plugin: Contact Form 7 (installed 6.0.3, latest 6.1.5)",
            "risk": "Outdated plugins may contain known vulnerabilities.",
        },
    ],
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

    # Create or update test client — always ensure chat_id and domain are correct
    existing = get_client(conn, "99999999")
    if existing:
        updates = {}
        if existing.get("telegram_chat_id") != chat_id:
            updates["telegram_chat_id"] = chat_id
        if existing.get("contact_name") != "Martin":
            updates["contact_name"] = "Martin"
        if updates:
            update_client(conn, "99999999", updates)
            print(f"Updated test client: {', '.join(updates.keys())}")
        else:
            print("Test client exists with correct settings")
    else:
        create_client(conn, "99999999", "Jelling Kro",
                      telegram_chat_id=chat_id, status="active", plan="watchman",
                      contact_name="Martin")
        print(f"Created test client (CVR 99999999, chat_id={chat_id})")

    # Always ensure domain link exists
    try:
        add_domain(conn, "99999999", "jellingkro.dk")
        print("Added domain link jellingkro.dk -> 99999999")
    except sqlite3.IntegrityError:
        pass  # Already linked
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
