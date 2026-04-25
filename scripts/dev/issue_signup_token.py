"""Issue a fresh signup token for browser testing of /signup/start.

Runs INSIDE the dev `delivery` container (RW client-data mount, has
src.db.signup importable). Launched by ``make signup-issue-token``.

Prints the full URL to paste into a browser:

    http://127.0.0.1:5173/signup/start?t=<TOKEN>

The token is bound to a synthetic CVR (default ``DRYRUN-BROWSER``) so
real client data is never touched. The CVR + token are NOT cleaned up;
re-running the script just issues another token.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from src.db.signup import create_signup_token  # noqa: E402

DB_PATH = "/data/clients/clients.db"
DEFAULT_CVR = "DRYRUN-BROWSER"
DEFAULT_EMAIL = "browser@dev.invalid"
DEFAULT_BASE_URL = "http://127.0.0.1:5173/signup/start"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Issue a fresh signup token and print the browser URL."
    )
    parser.add_argument(
        "--cvr", default=DEFAULT_CVR, help=f"CVR for the token (default {DEFAULT_CVR!r})."
    )
    parser.add_argument(
        "--email",
        default=DEFAULT_EMAIL,
        help=f"Email recorded on the token (default {DEFAULT_EMAIL!r}).",
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"Base URL of /signup/start (default {DEFAULT_BASE_URL!r}).",
    )
    args = parser.parse_args()

    conn = sqlite3.connect(DB_PATH, timeout=10)
    try:
        # The signup_tokens FK does not enforce against clients, but the row
        # is nice to have so the token-issue side mirrors a real prospect.
        conn.execute(
            """
            INSERT INTO clients (cvr, company_name, status, plan, created_at, updated_at)
            VALUES (?, ?, 'prospect', 'watchman', datetime('now'), datetime('now'))
            ON CONFLICT(cvr) DO UPDATE SET updated_at = datetime('now')
            """,
            (args.cvr, "Browser Test"),
        )
        conn.commit()

        result = create_signup_token(conn, cvr=args.cvr, email=args.email)
    finally:
        conn.close()

    token = result["token"]
    print(f"{args.base_url}?t={token}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
