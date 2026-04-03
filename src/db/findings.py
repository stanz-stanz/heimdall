"""CRUD operations for finding_definitions, finding_occurrences, and finding_status_log.

Follows the enrichment/db.py pattern: plain functions, sqlite3.Row dicts,
explicit commits, _now() for timestamps.
"""

from __future__ import annotations

import sqlite3

from src.db.connection import _now


# ---------------------------------------------------------------------------
# Finding definitions — immutable lookup table
# ---------------------------------------------------------------------------


def upsert_definition(
    conn: sqlite3.Connection,
    finding_hash: str,
    severity: str,
    description: str,
    risk: str = "",
    cve_id: str | None = None,
    plugin_slug: str | None = None,
    provenance: str | None = None,
    category: str | None = None,
    first_seen_at: str | None = None,
) -> None:
    """INSERT OR IGNORE a finding definition. Definitions are immutable.

    If a definition with the same ``finding_hash`` already exists, this is a
    no-op — the existing row is never updated.

    Args:
        conn: Read-write database connection.
        finding_hash: SHA-256 prefix used as dedup key.
        severity: One of critical|high|medium|low|info.
        description: Human-readable finding description.
        risk: Risk explanation text.
        cve_id: CVE identifier if applicable (e.g. "CVE-2024-28000").
        plugin_slug: WordPress plugin slug if applicable.
        provenance: Origin marker ("confirmed" or "unconfirmed").
        category: Finding type (cve|outdated_plugin|missing_header|ssl|exposure|info).
        first_seen_at: ISO-8601 date when first encountered globally.
            Defaults to ``_now()`` if not provided.
    """
    if first_seen_at is None:
        first_seen_at = _now()

    conn.execute(
        "INSERT OR IGNORE INTO finding_definitions "
        "(finding_hash, severity, description, risk, cve_id, plugin_slug, "
        "provenance, category, first_seen_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            finding_hash,
            severity,
            description,
            risk,
            cve_id,
            plugin_slug,
            provenance,
            category,
            first_seen_at,
        ),
    )
    conn.commit()


def get_definition(conn: sqlite3.Connection, finding_hash: str) -> dict | None:
    """Fetch a finding definition by hash.

    Args:
        conn: Database connection.
        finding_hash: The definition's primary key.

    Returns:
        A dict with all definition columns, or ``None`` if not found.
    """
    row = conn.execute(
        "SELECT * FROM finding_definitions WHERE finding_hash = ?",
        (finding_hash,),
    ).fetchone()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# Finding occurrences — per-domain lifecycle
# ---------------------------------------------------------------------------


def upsert_occurrence(
    conn: sqlite3.Connection,
    cvr: str,
    domain: str,
    finding_hash: str,
    confidence: str | None = None,
    status: str = "open",
    first_seen_at: str | None = None,
    last_seen_at: str | None = None,
    first_scan_id: str | None = None,
    last_scan_id: str | None = None,
) -> int:
    """Insert or update a finding occurrence.

    On conflict ``(domain, finding_hash)``: bumps ``last_seen_at``,
    ``scan_count``, and ``last_scan_id``. Does not overwrite status or
    confidence — those are managed explicitly via ``update_occurrence_status``
    and ``resolve_occurrence``.

    Args:
        conn: Read-write database connection.
        cvr: Client CVR number.
        domain: The domain where the finding was detected.
        finding_hash: FK to ``finding_definitions.finding_hash``.
        confidence: confirmed|potential|NULL.
        status: Initial status for new rows (default "open").
        first_seen_at: ISO-8601 timestamp. Defaults to ``_now()``.
        last_seen_at: ISO-8601 timestamp. Defaults to ``_now()``.
        first_scan_id: ``scan_history.scan_id`` of the first detection.
        last_scan_id: ``scan_history.scan_id`` of the current detection.

    Returns:
        The ``id`` (primary key) of the inserted or updated occurrence row.
    """
    now = _now()
    if first_seen_at is None:
        first_seen_at = now
    if last_seen_at is None:
        last_seen_at = now

    cursor = conn.execute(
        "INSERT INTO finding_occurrences "
        "(cvr, domain, finding_hash, confidence, status, "
        "first_seen_at, last_seen_at, first_scan_id, last_scan_id, scan_count) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1) "
        "ON CONFLICT(domain, finding_hash) DO UPDATE SET "
        "last_seen_at = excluded.last_seen_at, "
        "scan_count = scan_count + 1, "
        "last_scan_id = excluded.last_scan_id",
        (
            cvr,
            domain,
            finding_hash,
            confidence,
            status,
            first_seen_at,
            last_seen_at,
            first_scan_id,
            last_scan_id,
        ),
    )
    conn.commit()

    # Retrieve the id (works for both INSERT and UPDATE via CONFLICT)
    row = conn.execute(
        "SELECT id FROM finding_occurrences WHERE domain = ? AND finding_hash = ?",
        (domain, finding_hash),
    ).fetchone()
    return row["id"]


def get_open_occurrences(conn: sqlite3.Connection, domain: str) -> list[dict]:
    """Get all non-resolved occurrences for a domain, joined to definitions.

    Args:
        conn: Database connection.
        domain: The domain to query.

    Returns:
        List of dicts with occurrence + definition columns (severity,
        description, risk, cve_id, plugin_slug, category, provenance).
    """
    rows = conn.execute(
        "SELECT fo.*, fd.severity, fd.description, fd.risk, fd.cve_id, "
        "fd.plugin_slug, fd.category, fd.provenance "
        "FROM finding_occurrences fo "
        "JOIN finding_definitions fd ON fo.finding_hash = fd.finding_hash "
        "WHERE fo.domain = ? AND fo.status != 'resolved' "
        "ORDER BY fo.first_seen_at",
        (domain,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_occurrences_by_cvr(conn: sqlite3.Connection, cvr: str) -> list[dict]:
    """Get all occurrences for a client (by CVR), joined to definitions.

    Args:
        conn: Database connection.
        cvr: Client CVR number.

    Returns:
        List of dicts with occurrence + definition columns.
    """
    rows = conn.execute(
        "SELECT fo.*, fd.severity, fd.description, fd.risk, fd.cve_id, "
        "fd.plugin_slug, fd.category, fd.provenance "
        "FROM finding_occurrences fo "
        "JOIN finding_definitions fd ON fo.finding_hash = fd.finding_hash "
        "WHERE fo.cvr = ? "
        "ORDER BY fo.domain, fo.first_seen_at",
        (cvr,),
    ).fetchall()
    return [dict(r) for r in rows]


def resolve_occurrence(
    conn: sqlite3.Connection,
    occurrence_id: int,
    resolved_at: str,
    scan_id: str | None = None,
) -> None:
    """Set an occurrence to resolved.

    Args:
        conn: Read-write database connection.
        occurrence_id: PK of the occurrence to resolve.
        resolved_at: ISO-8601 timestamp of resolution.
        scan_id: The scan that confirmed the resolution.
    """
    conn.execute(
        "UPDATE finding_occurrences "
        "SET status = 'resolved', resolved_at = ?, last_scan_id = ? "
        "WHERE id = ?",
        (resolved_at, scan_id, occurrence_id),
    )
    conn.commit()


def update_occurrence_status(
    conn: sqlite3.Connection,
    occurrence_id: int,
    new_status: str,
) -> None:
    """Update an occurrence's status (for remediation transitions).

    Args:
        conn: Read-write database connection.
        occurrence_id: PK of the occurrence.
        new_status: The new status value (open|acknowledged|in_progress|resolved).
    """
    conn.execute(
        "UPDATE finding_occurrences SET status = ? WHERE id = ?",
        (new_status, occurrence_id),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Finding status log — audit trail
# ---------------------------------------------------------------------------


def log_status_transition(
    conn: sqlite3.Connection,
    occurrence_id: int,
    from_status: str | None,
    to_status: str,
    source: str,
) -> None:
    """Write a status transition to the audit log.

    Args:
        conn: Read-write database connection.
        occurrence_id: FK to ``finding_occurrences.id``.
        from_status: Previous status (``None`` for initial creation).
        to_status: New status.
        source: What triggered the change (e.g. "scan", "operator", "client").
    """
    conn.execute(
        "INSERT INTO finding_status_log "
        "(occurrence_id, from_status, to_status, source, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (occurrence_id, from_status, to_status, source, _now()),
    )
    conn.commit()


def get_status_log(conn: sqlite3.Connection, occurrence_id: int) -> list[dict]:
    """Get the status audit trail for an occurrence, ordered chronologically.

    Args:
        conn: Database connection.
        occurrence_id: FK to ``finding_occurrences.id``.

    Returns:
        List of dicts with ``from_status``, ``to_status``, ``source``,
        ``created_at``, ordered by ``created_at ASC``.
    """
    rows = conn.execute(
        "SELECT * FROM finding_status_log "
        "WHERE occurrence_id = ? "
        "ORDER BY created_at ASC, id ASC",
        (occurrence_id,),
    ).fetchall()
    return [dict(r) for r in rows]
