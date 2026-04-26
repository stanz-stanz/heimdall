"""Conversion funnel + onboarding stage log helpers.

Two tables, one module:

- ``conversion_events`` — append-only log of every touchpoint on the
  Watchman → Sentinel funnel (signups, CTA clicks, invoice opens, consent
  signs, cancellations). Feeds the operator console funnel dashboard (V5)
  and "stuck on X" queries.
- ``onboarding_stage_log`` — append-only audit trail for
  ``clients.onboarding_stage`` transitions. Mirrors the
  ``finding_status_log`` pattern: not load-bearing for product logic,
  but needed for post-hoc debugging of the Sentinel onboarding funnel.

:func:`transition_onboarding_stage` is the canonical way to move a client
through the onboarding substates — it updates ``clients.onboarding_stage``
and appends the log row in the same transaction so the two never diverge.

See the 2026-04-23 entry in ``docs/decisions/log.md`` and the schema in
``docs/architecture/client-db-schema.sql``.
"""

from __future__ import annotations

import json
import sqlite3

from src.db.clients import VALID_ONBOARDING_STAGES, get_client
from src.db.connection import _now

VALID_CONVERSION_EVENT_TYPES: set[str] = {
    # Funnel / prospect → trialist
    "signup",
    "cta_click",
    "upgrade_reply",
    "invoice_opened",
    "consent_opened",
    "consent_signed",
    "payment_intent",
    "scope_confirmed",
    "abandoned",
    "cancellation",
    # Sentinel consent + scope audit trail (2026-04-23 plan, 7-row trail).
    # Written at onboarding by the onboarding handlers; surviving at
    # retention time via the conversion_events table (not consent_records,
    # which is cascaded at purge).
    "contract_signed",
    "scanning_authorisation_signed",
    "scope_declared",
    "authorisation_file_written",
    "valdi_gate2_first_pass",
    # Retention lifecycle markers. Written by the retention cron runner
    # at start/end of anonymise / purge. ``authorisation_revoked`` must be
    # inserted BEFORE the cascade deletes consent_records — the audit
    # record survives in conversion_events, which retention at purge also
    # deletes, but the *scheduling* is what matters: the row exists until
    # its own CVR cascade runs, giving operator-console visibility while
    # retention is in flight.
    "offboarding_triggered",
    "authorisation_revoked",
}

# Stage-log source labels. Free-form at the schema level, but we constrain
# writes to these values so the funnel dashboard can group reliably.
VALID_STAGE_LOG_SOURCES: set[str] = {"webhook", "operator", "cron", "system"}

# Conversion-funnel events that signal the trialist is engaging with the
# Sentinel upgrade flow. The operator-console "Trial expiring" view (V1)
# uses this to filter out clients who are already in motion — no point
# nudging someone who has already replied to the upgrade email.
#
# Excludes:
#   - 'signup'   — every Watchman row carries this; it's not engagement.
#   - 'abandoned' / 'cancellation' — terminal markers; client is gone.
#   - 'offboarding_triggered' / 'authorisation_revoked' — retention
#     lifecycle, not conversion intent.
#
# When a new event-type is added to VALID_CONVERSION_EVENT_TYPES, decide
# whether it belongs here. The 'noise filter' membership test below
# guarantees every member exists in VALID — drift produces ImportError
# at module load.
SENTINEL_CONVERSION_INTENT_EVENTS: frozenset[str] = frozenset(
    {
        "cta_click",
        "upgrade_reply",
        "invoice_opened",
        "consent_opened",
        "consent_signed",
        "payment_intent",
        "scope_confirmed",
        "contract_signed",
        "scanning_authorisation_signed",
        "scope_declared",
        "authorisation_file_written",
        "valdi_gate2_first_pass",
    }
)
assert SENTINEL_CONVERSION_INTENT_EVENTS <= VALID_CONVERSION_EVENT_TYPES, (
    "SENTINEL_CONVERSION_INTENT_EVENTS drifted from VALID_CONVERSION_EVENT_TYPES; "
    "every intent event must be a known conversion event_type."
)


# ---------------------------------------------------------------------------
# Conversion events
# ---------------------------------------------------------------------------


def _validate_conversion_event_type(event_type: str) -> None:
    if event_type not in VALID_CONVERSION_EVENT_TYPES:
        raise ValueError(
            f"Invalid conversion event_type {event_type!r}. "
            f"Must be one of: {sorted(VALID_CONVERSION_EVENT_TYPES)}"
        )


def record_conversion_event(
    conn: sqlite3.Connection,
    cvr: str,
    event_type: str,
    *,
    source: str | None = None,
    payload: dict | None = None,
    occurred_at: str | None = None,
) -> dict:
    """Append a conversion-funnel event row.

    Args:
        conn: Database connection.
        cvr: Client CVR. No FK enforcement at this layer — prospects who
            have not yet been created in ``clients`` may still emit events
            (e.g. ``signup`` fires before the client row is fully upserted).
        event_type: One of :data:`VALID_CONVERSION_EVENT_TYPES`.
        source: Free-text provenance (``'email_click'``, ``'telegram_reply'``,
            ``'signup_form'``, ...). Not constrained.
        payload: Optional JSON-serialisable context blob.
        occurred_at: ISO-8601 UTC timestamp; defaults to now.

    Raises:
        ValueError: If ``event_type`` is not recognised.
    """
    _validate_conversion_event_type(event_type)

    now = _now()
    occurred = occurred_at or now
    payload_json = json.dumps(payload) if payload is not None else None

    cursor = conn.execute(
        """
        INSERT INTO conversion_events
            (cvr, event_type, source, payload_json, occurred_at, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (cvr, event_type, source, payload_json, occurred, now),
    )
    conn.commit()

    row = conn.execute(
        "SELECT * FROM conversion_events WHERE id = ?", (cursor.lastrowid,)
    ).fetchone()
    return dict(row)


def list_conversion_events_for_cvr(
    conn: sqlite3.Connection, cvr: str, limit: int | None = None
) -> list[dict]:
    """Conversion events for ``cvr``, newest first."""
    sql = """
        SELECT * FROM conversion_events
         WHERE cvr = ?
         ORDER BY occurred_at DESC
    """
    params: tuple = (cvr,)
    if limit is not None:
        sql += " LIMIT ?"
        params = (cvr, limit)

    rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def list_conversion_events_by_type(
    conn: sqlite3.Connection, event_type: str, limit: int | None = None
) -> list[dict]:
    """All conversion events of a given type, newest first.

    Used by the funnel dashboard to compute conversion rates
    (e.g. ``signup`` count → ``consent_signed`` count).
    """
    _validate_conversion_event_type(event_type)

    sql = """
        SELECT * FROM conversion_events
         WHERE event_type = ?
         ORDER BY occurred_at DESC
    """
    params: tuple = (event_type,)
    if limit is not None:
        sql += " LIMIT ?"
        params = (event_type, limit)

    rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Onboarding stage log
# ---------------------------------------------------------------------------


def _validate_stage(stage: str | None) -> None:
    if stage not in VALID_ONBOARDING_STAGES:
        valid = sorted(s for s in VALID_ONBOARDING_STAGES if s is not None)
        raise ValueError(
            f"Invalid onboarding_stage {stage!r}. Must be one of: {valid} or None"
        )


def _validate_stage_log_source(source: str | None) -> None:
    if source is not None and source not in VALID_STAGE_LOG_SOURCES:
        raise ValueError(
            f"Invalid stage-log source {source!r}. "
            f"Must be one of: {sorted(VALID_STAGE_LOG_SOURCES)} or None"
        )


def record_stage_transition(
    conn: sqlite3.Connection,
    cvr: str,
    from_stage: str | None,
    to_stage: str | None,
    *,
    source: str | None = None,
    note: str | None = None,
) -> dict:
    """Append a raw stage-log row.

    Prefer :func:`transition_onboarding_stage` in product code — that
    helper keeps ``clients.onboarding_stage`` in sync with the log.
    Use this function directly only for back-fill or reconciliation.

    Raises:
        ValueError: If stage names or source are not recognised.
    """
    _validate_stage(from_stage)
    _validate_stage(to_stage)
    _validate_stage_log_source(source)

    now = _now()
    cursor = conn.execute(
        """
        INSERT INTO onboarding_stage_log
            (cvr, from_stage, to_stage, source, note, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (cvr, from_stage, to_stage, source, note, now),
    )
    conn.commit()

    row = conn.execute(
        "SELECT * FROM onboarding_stage_log WHERE id = ?", (cursor.lastrowid,)
    ).fetchone()
    return dict(row)


def transition_onboarding_stage(
    conn: sqlite3.Connection,
    cvr: str,
    to_stage: str | None,
    *,
    source: str | None = None,
    note: str | None = None,
) -> dict:
    """Move a client to ``to_stage`` and log the transition atomically.

    Reads the current ``clients.onboarding_stage``, updates it, and
    appends an ``onboarding_stage_log`` row — in a single transaction so
    the column and the log stay consistent even under concurrent callers.

    If the client is already at ``to_stage`` the call is a no-op:
    no update, no log row written, returns the existing client unchanged.
    This keeps webhook retries idempotent.

    Returns:
        The client row (as a dict) after the transition.

    Raises:
        ValueError: If ``to_stage`` or ``source`` is invalid.
        KeyError: If the client does not exist.
    """
    _validate_stage(to_stage)
    _validate_stage_log_source(source)

    client = get_client(conn, cvr)
    if client is None:
        raise KeyError(f"Client with CVR {cvr!r} not found")

    from_stage = client.get("onboarding_stage")
    if from_stage == to_stage:
        return client

    now = _now()
    try:
        conn.execute("BEGIN")
        conn.execute(
            "UPDATE clients SET onboarding_stage = ?, updated_at = ? WHERE cvr = ?",
            (to_stage, now, cvr),
        )
        conn.execute(
            """
            INSERT INTO onboarding_stage_log
                (cvr, from_stage, to_stage, source, note, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (cvr, from_stage, to_stage, source, note, now),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    return get_client(conn, cvr)  # type: ignore[return-value]


def list_stage_log_for_cvr(
    conn: sqlite3.Connection, cvr: str, limit: int | None = None
) -> list[dict]:
    """Stage-log entries for ``cvr``, newest first."""
    sql = """
        SELECT * FROM onboarding_stage_log
         WHERE cvr = ?
         ORDER BY created_at DESC, id DESC
    """
    params: tuple = (cvr,)
    if limit is not None:
        sql += " LIMIT ?"
        params = (cvr, limit)

    rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]
