"""Docker healthcheck for the CT collector service.

Verifies the database is receiving recent data by checking that the most
recent ``seen_at`` timestamp is within 5 minutes.
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime, timedelta

from .db import open_readonly


def check(db_path: str = "/data/ct/certificates.db", max_age_minutes: int = 5) -> bool:
    """Return True if the CT database has data within the last *max_age_minutes*.

    Degrades gracefully: returns False if the database cannot be opened.
    """
    try:
        conn = open_readonly(db_path)
    except Exception:
        return False

    try:
        row = conn.execute("SELECT MAX(seen_at) as newest FROM certificates").fetchone()
        if row is None or row[0] is None:
            return False

        newest = row[0]
        # Parse ISO format timestamp
        newest_dt = datetime.fromisoformat(newest.replace("Z", "+00:00"))
        cutoff = datetime.now(UTC) - timedelta(minutes=max_age_minutes)
        return newest_dt >= cutoff
    except Exception:
        return False
    finally:
        conn.close()


def main() -> None:
    """Docker healthcheck entry point: exit 0 (healthy) or 1 (unhealthy)."""
    db_path = os.environ.get("CT_DB_PATH", "/data/ct/certificates.db")
    healthy = check(db_path=db_path)
    sys.exit(0 if healthy else 1)


if __name__ == "__main__":
    main()
