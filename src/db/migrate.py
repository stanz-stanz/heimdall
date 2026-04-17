"""Apply the latest schema to an existing clients.db.

Usage inside Docker:
    python -m src.db.migrate [--db-path /data/clients/clients.db]

Safe to run multiple times — all CREATE statements use IF NOT EXISTS
and ALTER TABLE ADD COLUMN is guarded by a PRAGMA table_info check.
"""

import argparse
import os
import sqlite3
import sys

from src.db.connection import init_db

# Columns to add to existing tables that cannot live in CREATE TABLE IF NOT EXISTS.
# Each entry: (table, column_name, column_def)
_COLUMN_ADDS: list[tuple[str, str, str]] = [
    ("clients", "monitoring_enabled", "INTEGER NOT NULL DEFAULT 0"),
    ("clients", "ct_last_polled_at", "TEXT"),
]


def apply_pending_migrations(conn: sqlite3.Connection) -> list[str]:
    """Apply ALTER TABLE ADD COLUMN for any missing columns listed in _COLUMN_ADDS.

    Returns the list of columns added this run (empty if schema already up to date).
    """
    added: list[str] = []
    for table, col, col_def in _COLUMN_ADDS:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        existing = {r[1] for r in rows}
        if col in existing:
            continue
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_def}")
        added.append(f"{table}.{col}")
    return added


# Backwards-compatible alias. Keep for one release so existing callers
# (tests/test_ct_monitor.py, tests/test_scheduler_monitor_handler.py,
# scripts/dev/cert_change_dry_run.py) continue to work unchanged.
_add_missing_columns = apply_pending_migrations


def main():
    parser = argparse.ArgumentParser(description="Apply schema migrations to clients.db")
    parser.add_argument(
        "--db-path",
        default=os.environ.get(
            "DB_PATH",
            os.path.join(os.environ.get("CLIENT_DATA_DIR", "data/clients"), "clients.db"),
        ),
        help="Path to the SQLite database file",
    )
    args = parser.parse_args()

    if not os.path.exists(args.db_path):
        print(f"Database not found: {args.db_path}")
        sys.exit(1)

    conn = init_db(args.db_path)
    added = apply_pending_migrations(conn)
    if added:
        print(f"Added columns: {', '.join(added)}")
    # Checkpoint WAL so immutable=1 readers can see the new tables
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.close()
    print(f"Schema applied and WAL checkpointed: {args.db_path}")


if __name__ == "__main__":
    main()
