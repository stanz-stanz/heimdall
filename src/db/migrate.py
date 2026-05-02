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


# New tables added in Stage A.5 (2026-05-01). On a fresh DB the schema
# bundle (docs/architecture/client-db-schema.sql SECTIONS 12-13) already
# installs these via init_db()'s executescript; on a legacy DB that was
# initialised before A.5 landed, these statements add the tables. The
# DDL must stay in lockstep with the bundle. Each entry is a complete,
# idempotent CREATE TABLE statement.
_TABLE_ADDS: list[str] = [
    # SECTION 12 — operator command outcome audit (api INSERT-driven).
    """
    CREATE TABLE IF NOT EXISTS command_audit (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        occurred_at     TEXT NOT NULL,
        command_name    TEXT NOT NULL,
        target_type     TEXT,
        target_id       TEXT,
        outcome         TEXT NOT NULL,
        payload_json    TEXT,
        error_detail    TEXT,
        operator_id     INTEGER,
        session_id      INTEGER,
        request_id      TEXT,
        actor_kind      TEXT NOT NULL DEFAULT 'operator'
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_command_audit_occurred
        ON command_audit(occurred_at DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_command_audit_request
        ON command_audit(request_id) WHERE request_id IS NOT NULL
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_command_audit_command
        ON command_audit(command_name, occurred_at DESC)
    """,
    # SECTION 13 — config_changes audit (trigger-captured).
    """
    CREATE TABLE IF NOT EXISTS config_changes (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        occurred_at     TEXT NOT NULL,
        table_name      TEXT NOT NULL,
        op              TEXT NOT NULL,
        target_pk       TEXT NOT NULL,
        old_json        TEXT,
        new_json        TEXT,
        intent          TEXT,
        operator_id     INTEGER,
        session_id      INTEGER,
        request_id      TEXT,
        actor_kind      TEXT NOT NULL DEFAULT 'operator'
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_config_changes_occurred
        ON config_changes(occurred_at DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_config_changes_table
        ON config_changes(table_name, occurred_at DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_config_changes_request
        ON config_changes(request_id) WHERE request_id IS NOT NULL
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_config_changes_target
        ON config_changes(table_name, target_pk, occurred_at DESC)
    """,
]


# Triggers installed by Stage A.5. Same source-of-truth duality as
# _TABLE_ADDS (bundle for fresh DBs, _TRIGGER_ADDS for legacy upgrade).
# Six tier-1 tables × 2 ops (UPDATE + DELETE) = 12 triggers. INSERT
# triggers are intentionally not installed (spec §4.1.3 rationale).
# Trigger bodies read from the per-connection TEMP table _audit_context
# (see src/db/audit_context.py).
_TRIGGER_ADDS: list[str] = [
    # clients
    """
    CREATE TRIGGER IF NOT EXISTS trg_clients_audit_update
    AFTER UPDATE ON clients
    FOR EACH ROW
    WHEN (
        OLD.cvr               IS NOT NEW.cvr               OR
        OLD.status            IS NOT NEW.status            OR
        OLD.plan              IS NOT NEW.plan              OR
        OLD.consent_granted   IS NOT NEW.consent_granted   OR
        OLD.monitoring_enabled IS NOT NEW.monitoring_enabled OR
        OLD.data_retention_mode IS NOT NEW.data_retention_mode OR
        OLD.churn_reason      IS NOT NEW.churn_reason      OR
        OLD.churn_purge_at    IS NOT NEW.churn_purge_at    OR
        OLD.onboarding_stage  IS NOT NEW.onboarding_stage  OR
        OLD.trial_started_at  IS NOT NEW.trial_started_at  OR
        OLD.trial_expires_at  IS NOT NEW.trial_expires_at  OR
        OLD.signup_source     IS NOT NEW.signup_source     OR
        OLD.churn_requested_at IS NOT NEW.churn_requested_at
    )
    BEGIN
        INSERT INTO config_changes (
            occurred_at, table_name, op, target_pk,
            old_json, new_json,
            intent, operator_id, session_id, request_id, actor_kind
        )
        VALUES (
            strftime('%Y-%m-%dT%H:%M:%fZ', 'now'),
            'clients',
            'UPDATE',
            NEW.cvr,
            json_object(
                'cvr', OLD.cvr, 'status', OLD.status, 'plan', OLD.plan,
                'consent_granted', OLD.consent_granted,
                'monitoring_enabled', OLD.monitoring_enabled,
                'data_retention_mode', OLD.data_retention_mode,
                'churn_reason', OLD.churn_reason,
                'churn_purge_at', OLD.churn_purge_at,
                'onboarding_stage', OLD.onboarding_stage,
                'trial_started_at', OLD.trial_started_at,
                'trial_expires_at', OLD.trial_expires_at,
                'signup_source', OLD.signup_source,
                'churn_requested_at', OLD.churn_requested_at
            ),
            json_object(
                'cvr', NEW.cvr, 'status', NEW.status, 'plan', NEW.plan,
                'consent_granted', NEW.consent_granted,
                'monitoring_enabled', NEW.monitoring_enabled,
                'data_retention_mode', NEW.data_retention_mode,
                'churn_reason', NEW.churn_reason,
                'churn_purge_at', NEW.churn_purge_at,
                'onboarding_stage', NEW.onboarding_stage,
                'trial_started_at', NEW.trial_started_at,
                'trial_expires_at', NEW.trial_expires_at,
                'signup_source', NEW.signup_source,
                'churn_requested_at', NEW.churn_requested_at
            ),
            audit_context('intent'),
            audit_context('operator_id'),
            audit_context('session_id'),
            audit_context('request_id'),
            COALESCE(audit_context('actor_kind'), 'operator')
        );
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_clients_audit_delete
    AFTER DELETE ON clients
    FOR EACH ROW
    BEGIN
        INSERT INTO config_changes (
            occurred_at, table_name, op, target_pk,
            old_json, new_json,
            intent, operator_id, session_id, request_id, actor_kind
        )
        VALUES (
            strftime('%Y-%m-%dT%H:%M:%fZ', 'now'),
            'clients',
            'DELETE',
            OLD.cvr,
            json_object(
                'cvr', OLD.cvr, 'status', OLD.status, 'plan', OLD.plan,
                'consent_granted', OLD.consent_granted,
                'monitoring_enabled', OLD.monitoring_enabled,
                'data_retention_mode', OLD.data_retention_mode,
                'churn_reason', OLD.churn_reason,
                'churn_purge_at', OLD.churn_purge_at,
                'onboarding_stage', OLD.onboarding_stage,
                'trial_started_at', OLD.trial_started_at,
                'trial_expires_at', OLD.trial_expires_at,
                'signup_source', OLD.signup_source,
                'churn_requested_at', OLD.churn_requested_at
            ),
            NULL,
            audit_context('intent'),
            audit_context('operator_id'),
            audit_context('session_id'),
            audit_context('request_id'),
            COALESCE(audit_context('actor_kind'), 'operator')
        );
    END
    """,
    # subscriptions
    """
    CREATE TRIGGER IF NOT EXISTS trg_subscriptions_audit_update
    AFTER UPDATE ON subscriptions
    FOR EACH ROW
    WHEN (
        OLD.status             IS NOT NEW.status             OR
        OLD.current_period_end IS NOT NEW.current_period_end OR
        OLD.cancelled_at       IS NOT NEW.cancelled_at       OR
        OLD.invoice_ref        IS NOT NEW.invoice_ref        OR
        OLD.amount_dkk         IS NOT NEW.amount_dkk         OR
        OLD.billing_period     IS NOT NEW.billing_period     OR
        OLD.mandate_id         IS NOT NEW.mandate_id         OR
        OLD.plan               IS NOT NEW.plan               OR
        OLD.started_at         IS NOT NEW.started_at
    )
    BEGIN
        INSERT INTO config_changes (
            occurred_at, table_name, op, target_pk,
            old_json, new_json,
            intent, operator_id, session_id, request_id, actor_kind
        )
        VALUES (
            strftime('%Y-%m-%dT%H:%M:%fZ', 'now'),
            'subscriptions',
            'UPDATE',
            NEW.cvr,
            json_object(
                'cvr', OLD.cvr, 'plan', OLD.plan, 'status', OLD.status,
                'started_at', OLD.started_at,
                'current_period_end', OLD.current_period_end,
                'cancelled_at', OLD.cancelled_at,
                'invoice_ref', OLD.invoice_ref,
                'amount_dkk', OLD.amount_dkk,
                'billing_period', OLD.billing_period,
                'mandate_id', OLD.mandate_id
            ),
            json_object(
                'cvr', NEW.cvr, 'plan', NEW.plan, 'status', NEW.status,
                'started_at', NEW.started_at,
                'current_period_end', NEW.current_period_end,
                'cancelled_at', NEW.cancelled_at,
                'invoice_ref', NEW.invoice_ref,
                'amount_dkk', NEW.amount_dkk,
                'billing_period', NEW.billing_period,
                'mandate_id', NEW.mandate_id
            ),
            audit_context('intent'),
            audit_context('operator_id'),
            audit_context('session_id'),
            audit_context('request_id'),
            COALESCE(audit_context('actor_kind'), 'operator')
        );
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_subscriptions_audit_delete
    AFTER DELETE ON subscriptions
    FOR EACH ROW
    BEGIN
        INSERT INTO config_changes (
            occurred_at, table_name, op, target_pk,
            old_json, new_json,
            intent, operator_id, session_id, request_id, actor_kind
        )
        VALUES (
            strftime('%Y-%m-%dT%H:%M:%fZ', 'now'),
            'subscriptions',
            'DELETE',
            OLD.cvr,
            json_object(
                'cvr', OLD.cvr, 'plan', OLD.plan, 'status', OLD.status,
                'started_at', OLD.started_at,
                'current_period_end', OLD.current_period_end,
                'cancelled_at', OLD.cancelled_at,
                'invoice_ref', OLD.invoice_ref,
                'amount_dkk', OLD.amount_dkk,
                'billing_period', OLD.billing_period,
                'mandate_id', OLD.mandate_id
            ),
            NULL,
            audit_context('intent'),
            audit_context('operator_id'),
            audit_context('session_id'),
            audit_context('request_id'),
            COALESCE(audit_context('actor_kind'), 'operator')
        );
    END
    """,
    # consent_records (Valdí §263 PII preservation)
    """
    CREATE TRIGGER IF NOT EXISTS trg_consent_records_audit_update
    AFTER UPDATE ON consent_records
    FOR EACH ROW
    WHEN (
        OLD.authorised_domains  IS NOT NEW.authorised_domains  OR
        OLD.consent_type        IS NOT NEW.consent_type        OR
        OLD.consent_date        IS NOT NEW.consent_date        OR
        OLD.consent_expiry      IS NOT NEW.consent_expiry      OR
        OLD.consent_document    IS NOT NEW.consent_document    OR
        OLD.authorised_by_name  IS NOT NEW.authorised_by_name  OR
        OLD.authorised_by_role  IS NOT NEW.authorised_by_role  OR
        OLD.authorised_by_email IS NOT NEW.authorised_by_email OR
        OLD.status              IS NOT NEW.status              OR
        OLD.notes               IS NOT NEW.notes
    )
    BEGIN
        INSERT INTO config_changes (
            occurred_at, table_name, op, target_pk,
            old_json, new_json,
            intent, operator_id, session_id, request_id, actor_kind
        )
        VALUES (
            strftime('%Y-%m-%dT%H:%M:%fZ', 'now'),
            'consent_records',
            'UPDATE',
            NEW.cvr,
            json_object(
                'cvr', OLD.cvr,
                'authorised_domains', OLD.authorised_domains,
                'consent_type', OLD.consent_type,
                'consent_date', OLD.consent_date,
                'consent_expiry', OLD.consent_expiry,
                'consent_document', OLD.consent_document,
                'authorised_by_name', OLD.authorised_by_name,
                'authorised_by_role', OLD.authorised_by_role,
                'authorised_by_email', OLD.authorised_by_email,
                'status', OLD.status,
                'notes', OLD.notes
            ),
            json_object(
                'cvr', NEW.cvr,
                'authorised_domains', NEW.authorised_domains,
                'consent_type', NEW.consent_type,
                'consent_date', NEW.consent_date,
                'consent_expiry', NEW.consent_expiry,
                'consent_document', NEW.consent_document,
                'authorised_by_name', NEW.authorised_by_name,
                'authorised_by_role', NEW.authorised_by_role,
                'authorised_by_email', NEW.authorised_by_email,
                'status', NEW.status,
                'notes', NEW.notes
            ),
            audit_context('intent'),
            audit_context('operator_id'),
            audit_context('session_id'),
            audit_context('request_id'),
            COALESCE(audit_context('actor_kind'), 'operator')
        );
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_consent_records_audit_delete
    AFTER DELETE ON consent_records
    FOR EACH ROW
    BEGIN
        INSERT INTO config_changes (
            occurred_at, table_name, op, target_pk,
            old_json, new_json,
            intent, operator_id, session_id, request_id, actor_kind
        )
        VALUES (
            strftime('%Y-%m-%dT%H:%M:%fZ', 'now'),
            'consent_records',
            'DELETE',
            OLD.cvr,
            json_object(
                'cvr', OLD.cvr,
                'authorised_domains', OLD.authorised_domains,
                'consent_type', OLD.consent_type,
                'consent_date', OLD.consent_date,
                'consent_expiry', OLD.consent_expiry,
                'consent_document', OLD.consent_document,
                'authorised_by_name', OLD.authorised_by_name,
                'authorised_by_role', OLD.authorised_by_role,
                'authorised_by_email', OLD.authorised_by_email,
                'status', OLD.status,
                'notes', OLD.notes
            ),
            NULL,
            audit_context('intent'),
            audit_context('operator_id'),
            audit_context('session_id'),
            audit_context('request_id'),
            COALESCE(audit_context('actor_kind'), 'operator')
        );
    END
    """,
    # signup_tokens
    """
    CREATE TRIGGER IF NOT EXISTS trg_signup_tokens_audit_update
    AFTER UPDATE ON signup_tokens
    FOR EACH ROW
    WHEN (
        OLD.consumed_at IS NOT NEW.consumed_at OR
        OLD.expires_at  IS NOT NEW.expires_at  OR
        OLD.email       IS NOT NEW.email       OR
        OLD.cvr         IS NOT NEW.cvr         OR
        OLD.source      IS NOT NEW.source
    )
    BEGIN
        INSERT INTO config_changes (
            occurred_at, table_name, op, target_pk,
            old_json, new_json,
            intent, operator_id, session_id, request_id, actor_kind
        )
        VALUES (
            strftime('%Y-%m-%dT%H:%M:%fZ', 'now'),
            'signup_tokens',
            'UPDATE',
            NEW.token,
            json_object(
                'token', OLD.token, 'cvr', OLD.cvr, 'email', OLD.email,
                'source', OLD.source, 'expires_at', OLD.expires_at,
                'consumed_at', OLD.consumed_at
            ),
            json_object(
                'token', NEW.token, 'cvr', NEW.cvr, 'email', NEW.email,
                'source', NEW.source, 'expires_at', NEW.expires_at,
                'consumed_at', NEW.consumed_at
            ),
            audit_context('intent'),
            audit_context('operator_id'),
            audit_context('session_id'),
            audit_context('request_id'),
            COALESCE(audit_context('actor_kind'), 'operator')
        );
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_signup_tokens_audit_delete
    AFTER DELETE ON signup_tokens
    FOR EACH ROW
    BEGIN
        INSERT INTO config_changes (
            occurred_at, table_name, op, target_pk,
            old_json, new_json,
            intent, operator_id, session_id, request_id, actor_kind
        )
        VALUES (
            strftime('%Y-%m-%dT%H:%M:%fZ', 'now'),
            'signup_tokens',
            'DELETE',
            OLD.token,
            json_object(
                'token', OLD.token, 'cvr', OLD.cvr, 'email', OLD.email,
                'source', OLD.source, 'expires_at', OLD.expires_at,
                'consumed_at', OLD.consumed_at
            ),
            NULL,
            audit_context('intent'),
            audit_context('operator_id'),
            audit_context('session_id'),
            audit_context('request_id'),
            COALESCE(audit_context('actor_kind'), 'operator')
        );
    END
    """,
    # client_domains
    """
    CREATE TRIGGER IF NOT EXISTS trg_client_domains_audit_update
    AFTER UPDATE ON client_domains
    FOR EACH ROW
    WHEN (
        OLD.cvr        IS NOT NEW.cvr        OR
        OLD.domain     IS NOT NEW.domain     OR
        OLD.is_primary IS NOT NEW.is_primary
    )
    BEGIN
        INSERT INTO config_changes (
            occurred_at, table_name, op, target_pk,
            old_json, new_json,
            intent, operator_id, session_id, request_id, actor_kind
        )
        VALUES (
            strftime('%Y-%m-%dT%H:%M:%fZ', 'now'),
            'client_domains',
            'UPDATE',
            CAST(NEW.id AS TEXT),
            json_object(
                'id', OLD.id, 'cvr', OLD.cvr, 'domain', OLD.domain,
                'is_primary', OLD.is_primary, 'added_at', OLD.added_at
            ),
            json_object(
                'id', NEW.id, 'cvr', NEW.cvr, 'domain', NEW.domain,
                'is_primary', NEW.is_primary, 'added_at', NEW.added_at
            ),
            audit_context('intent'),
            audit_context('operator_id'),
            audit_context('session_id'),
            audit_context('request_id'),
            COALESCE(audit_context('actor_kind'), 'operator')
        );
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_client_domains_audit_delete
    AFTER DELETE ON client_domains
    FOR EACH ROW
    BEGIN
        INSERT INTO config_changes (
            occurred_at, table_name, op, target_pk,
            old_json, new_json,
            intent, operator_id, session_id, request_id, actor_kind
        )
        VALUES (
            strftime('%Y-%m-%dT%H:%M:%fZ', 'now'),
            'client_domains',
            'DELETE',
            CAST(OLD.id AS TEXT),
            json_object(
                'id', OLD.id, 'cvr', OLD.cvr, 'domain', OLD.domain,
                'is_primary', OLD.is_primary, 'added_at', OLD.added_at
            ),
            NULL,
            audit_context('intent'),
            audit_context('operator_id'),
            audit_context('session_id'),
            audit_context('request_id'),
            COALESCE(audit_context('actor_kind'), 'operator')
        );
    END
    """,
    # retention_jobs (joined tier 1 per fork (f), 2026-05-01)
    """
    CREATE TRIGGER IF NOT EXISTS trg_retention_jobs_audit_update
    AFTER UPDATE ON retention_jobs
    FOR EACH ROW
    WHEN (
        OLD.action        IS NOT NEW.action        OR
        OLD.scheduled_for IS NOT NEW.scheduled_for OR
        OLD.claimed_at    IS NOT NEW.claimed_at    OR
        OLD.executed_at   IS NOT NEW.executed_at   OR
        OLD.status        IS NOT NEW.status        OR
        OLD.notes         IS NOT NEW.notes
    )
    BEGIN
        INSERT INTO config_changes (
            occurred_at, table_name, op, target_pk,
            old_json, new_json,
            intent, operator_id, session_id, request_id, actor_kind
        )
        VALUES (
            strftime('%Y-%m-%dT%H:%M:%fZ', 'now'),
            'retention_jobs',
            'UPDATE',
            CAST(NEW.id AS TEXT),
            json_object(
                'id', OLD.id, 'cvr', OLD.cvr, 'action', OLD.action,
                'scheduled_for', OLD.scheduled_for,
                'claimed_at', OLD.claimed_at,
                'executed_at', OLD.executed_at,
                'status', OLD.status, 'notes', OLD.notes
            ),
            json_object(
                'id', NEW.id, 'cvr', NEW.cvr, 'action', NEW.action,
                'scheduled_for', NEW.scheduled_for,
                'claimed_at', NEW.claimed_at,
                'executed_at', NEW.executed_at,
                'status', NEW.status, 'notes', NEW.notes
            ),
            audit_context('intent'),
            audit_context('operator_id'),
            audit_context('session_id'),
            audit_context('request_id'),
            COALESCE(audit_context('actor_kind'), 'operator')
        );
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_retention_jobs_audit_delete
    AFTER DELETE ON retention_jobs
    FOR EACH ROW
    BEGIN
        INSERT INTO config_changes (
            occurred_at, table_name, op, target_pk,
            old_json, new_json,
            intent, operator_id, session_id, request_id, actor_kind
        )
        VALUES (
            strftime('%Y-%m-%dT%H:%M:%fZ', 'now'),
            'retention_jobs',
            'DELETE',
            CAST(OLD.id AS TEXT),
            json_object(
                'id', OLD.id, 'cvr', OLD.cvr, 'action', OLD.action,
                'scheduled_for', OLD.scheduled_for,
                'claimed_at', OLD.claimed_at,
                'executed_at', OLD.executed_at,
                'status', OLD.status, 'notes', OLD.notes
            ),
            NULL,
            audit_context('intent'),
            audit_context('operator_id'),
            audit_context('session_id'),
            audit_context('request_id'),
            COALESCE(audit_context('actor_kind'), 'operator')
        );
    END
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

    Five phases: (1) add any missing columns from ``_COLUMN_ADDS``,
    (2) run pre-flight integrity checks for indexes that introduce
    constraints, (3) create any missing indexes from ``_INDEX_ADDS``
    that may reference those columns, (4) install A.5 audit tables
    (``_TABLE_ADDS``) for legacy DBs that pre-date the bundle's
    SECTIONS 12-13, (5) install A.5 ``config_changes`` triggers
    (``_TRIGGER_ADDS``) which read from the per-connection TEMP table
    ``_audit_context`` (see ``src/db/audit_context.py``). All passes
    are idempotent — safe to call on every ``init_db``.

    On a fresh DB, the schema bundle's executescript already creates
    everything; phases 4-5 no-op via ``CREATE TABLE / TRIGGER IF NOT
    EXISTS``. On a legacy DB initialised before A.5 landed, phases
    4-5 install the new surface.

    Raises:
        LegacyDataIntegrityError: A pre-flight check found rows that
            would violate a constraint a pending index is about to
            introduce. The message includes a diagnostic query so the
            operator can identify and manually resolve the conflict.

    Returns the list of column-add migrations that landed this run
    (empty if schema already up to date). Index / table / trigger
    creations are not enumerated in the return value because the
    ``IF NOT EXISTS`` guards make them silent no-ops on the steady
    state.
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

    # A.5 audit tables (legacy-DB upgrade path; no-op on fresh DBs).
    for table_sql in _TABLE_ADDS:
        conn.execute(table_sql)

    # A.5 config_changes triggers — must run AFTER tables, since the
    # trigger bodies reference config_changes.
    for trigger_sql in _TRIGGER_ADDS:
        conn.execute(trigger_sql)

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
