"""Apply the latest schema to an existing clients.db (adds missing tables/views).

Usage:
    python -m scripts.migrate_db [--db-path /data/clients/clients.db]

Safe to run multiple times — all CREATE statements use IF NOT EXISTS.
"""

import argparse
import os
import sys

from src.db.connection import init_db


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
    conn.close()
    print(f"Schema applied to {args.db_path}")


if __name__ == "__main__":
    main()
