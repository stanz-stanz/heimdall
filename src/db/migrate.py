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
    # Onboarding lifecycle (2026-04-23 — Sentinel onboarding plan)
    ("clients", "trial_started_at", "TEXT"),
    ("clients", "trial_expires_at", "TEXT"),
    ("clients", "onboarding_stage", "TEXT"),
    ("clients", "signup_source", "TEXT"),
    ("clients", "churn_reason", "TEXT"),
    ("clients", "churn_requested_at", "TEXT"),
    ("clients", "churn_purge_at", "TEXT"),
    ("clients", "data_retention_mode", "TEXT NOT NULL DEFAULT 'standard'"),
    # Retention cron claim tracking (2026-04-24 — B5 / architect §6 concurrency)
    ("retention_jobs", "claimed_at", "TEXT"),
    # Payment-events provider column (2026-04-25 — R3 cloud-hosting plan).
    # Default 'betalingsservice' keeps existing INSERTs working unchanged
    # while enabling the (provider, external_id, event_type) partial UNIQUE
    # index applied below in _INDEX_ADDS (must run AFTER this column is
    # added on legacy DBs).
    ("payment_events", "provider", "TEXT NOT NULL DEFAULT 'betalingsservice'"),
]


# Indexes that depend on columns introduced by _COLUMN_ADDS. These run
# AFTER the column-add pass so legacy databases (where the dependent
# column doesn't yet exist) don't fail at the CREATE INDEX step. Each
# entry is a complete, idempotent CREATE INDEX statement.
_INDEX_ADDS: list[str] = [
    # R3 idempotency control for Betalingsservice webhook delivery
    # (2026-04-25 cloud-hosting plan). Partial — only enforces when
    # external_id is set, so reconciliation rows with NULL external_id
    # are exempt (they have no provider-side reference to dedupe against).
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_payment_events_provider_extid_eventtype
        ON payment_events(provider, external_id, event_type)
        WHERE external_id IS NOT NULL
    """,
]


class LegacyDataIntegrityError(RuntimeError):
    """Raised when an existing database holds rows that violate a
    constraint a pending migration is about to introduce.

    The migration refuses to apply rather than silently mutate billing
    data or skip the constraint. Operators must clean up the offending
    rows manually before init_db can complete. The exception message
    includes the diagnostic query so operators can reproduce.
    """


def _check_payment_events_duplicates(conn: sqlite3.Connection) -> None:
    """Refuse to add the partial UNIQUE index if legacy duplicates exist.

    The (provider, external_id, event_type) UNIQUE index introduced in
    R3 (2026-04-25 cloud-hosting plan) enforces webhook idempotency. If
    a pre-migration database already contains duplicate webhook rows for
    the same tuple, ``CREATE UNIQUE INDEX`` would raise
    ``sqlite3.IntegrityError`` — failing init_db without a clear
    operator-facing diagnosis. This pre-flight surfaces the conflict
    explicitly and refuses to proceed; auto-dedupe is intentionally
    excluded because payment_events is bookkeeping-grade (Bogføringsloven
    5y retention) and silent row deletion is not acceptable.

    Pre-pilot reality: zero rows in payment_events on every current
    database, so this check is a no-op. The guard exists for the post-
    Betalingsservice future where webhook duplicates could arrive.
    """
    rows = conn.execute(
        """
        SELECT provider, external_id, event_type, COUNT(*) AS dup_count
          FROM payment_events
         WHERE external_id IS NOT NULL
         GROUP BY provider, external_id, event_type
        HAVING COUNT(*) > 1
        """
    ).fetchall()
    if not rows:
        return

    sample = rows[:5]
    sample_str = ", ".join(
        f"({r['provider']!r}, {r['external_id']!r}, {r['event_type']!r}) ×{r['dup_count']}"
        for r in sample
    )
    raise LegacyDataIntegrityError(
        f"Cannot create uq_payment_events_provider_extid_eventtype: "
        f"{len(rows)} duplicate (provider, external_id, event_type) tuple(s) "
        f"already in payment_events. Sample: {sample_str}. "
        "Resolve manually before re-running init_db. Diagnostic query: "
        "SELECT provider, external_id, event_type, COUNT(*) FROM payment_events "
        "WHERE external_id IS NOT NULL GROUP BY provider, external_id, event_type "
        "HAVING COUNT(*) > 1;"
    )


def apply_pending_migrations(conn: sqlite3.Connection) -> list[str]:
    """Apply ALTER TABLE ADD COLUMN + dependent CREATE INDEX migrations.

    Three phases: (1) add any missing columns from ``_COLUMN_ADDS``,
    (2) run pre-flight integrity checks for indexes that introduce
    constraints, (3) create any missing indexes from ``_INDEX_ADDS``
    that may reference those columns. All passes are idempotent — safe
    to call on every ``init_db``.

    Raises:
        LegacyDataIntegrityError: A pre-flight check found rows that
            would violate a constraint a pending index is about to
            introduce. The message includes a diagnostic query so the
            operator can identify and manually resolve the conflict.

    Returns the list of column-add migrations that landed this run
    (empty if schema already up to date). Index creations are not
    enumerated in the return value because ``CREATE INDEX IF NOT EXISTS``
    silently no-ops, and the operator log line below logs the column
    diff which is what callers actually need to see.
    """
    added: list[str] = []
    for table, col, col_def in _COLUMN_ADDS:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        existing = {r[1] for r in rows}
        if col in existing:
            continue
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_def}")
        added.append(f"{table}.{col}")

    # Pre-flight: refuse to add the UNIQUE index if existing rows would
    # violate it. Fails fast with a diagnostic message rather than
    # silently mutating bookkeeping data.
    _check_payment_events_duplicates(conn)

    # Indexes run AFTER columns + pre-flight so a legacy DB that just
    # got `provider` added in the loop above can immediately have the
    # index built on it (provided no duplicates exist).
    for index_sql in _INDEX_ADDS:
        conn.execute(index_sql)

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
