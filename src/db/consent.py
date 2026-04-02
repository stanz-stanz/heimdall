"""CRUD operations for consent records.

Follows the enrichment/db.py pattern: plain functions, Row dicts, _now() timestamps.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date

from src.db.connection import _now


def create_consent_record(
    conn: sqlite3.Connection,
    cvr: str,
    authorised_domains: list[str],
    consent_date: str,
    consent_expiry: str,
    consent_document: str,
    authorised_by_name: str,
    authorised_by_role: str,
    authorised_by_email: str,
    **kwargs: str,
) -> dict:
    """Create a consent record.

    Args:
        conn: Database connection.
        cvr: Danish CVR number for the consenting company.
        authorised_domains: List of domains covered by this consent.
        consent_date: ISO-8601 date when consent was granted.
        consent_expiry: ISO-8601 date when consent expires.
        consent_document: Relative path to the signed consent document.
        authorised_by_name: Name of the person granting consent.
        authorised_by_role: Role/title of the person granting consent.
        authorised_by_email: Email of the person granting consent.
        **kwargs: Optional fields -- consent_type, status, notes.

    Returns:
        Row dict with all columns for the newly created record.
    """
    now = _now()
    consent_type = kwargs.get("consent_type", "written")
    status = kwargs.get("status", "active")
    notes = kwargs.get("notes")

    conn.execute(
        "INSERT INTO consent_records ("
        "cvr, authorised_domains, consent_type, "
        "consent_date, consent_expiry, consent_document, "
        "authorised_by_name, authorised_by_role, authorised_by_email, "
        "status, notes, created_at, updated_at"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            cvr,
            json.dumps(authorised_domains),
            consent_type,
            consent_date,
            consent_expiry,
            consent_document,
            authorised_by_name,
            authorised_by_role,
            authorised_by_email,
            status,
            notes,
            now,
            now,
        ),
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM consent_records WHERE id = last_insert_rowid()"
    ).fetchone()
    return dict(row)


def get_active_consent(
    conn: sqlite3.Connection,
    cvr: str,
) -> dict | None:
    """Get the most recent active, non-expired consent for a CVR.

    Args:
        conn: Database connection.
        cvr: Danish CVR number.

    Returns:
        Row dict for the active consent, or None if no valid consent exists.
    """
    today = date.today().isoformat()
    row = conn.execute(
        "SELECT * FROM consent_records "
        "WHERE cvr = ? AND status = 'active' AND consent_expiry >= ? "
        "ORDER BY consent_date DESC LIMIT 1",
        (cvr, today),
    ).fetchone()
    return dict(row) if row else None


def revoke_consent(
    conn: sqlite3.Connection,
    consent_id: int,
) -> None:
    """Set status='revoked' and update timestamp.

    Args:
        conn: Database connection.
        consent_id: Primary key of the consent record to revoke.
    """
    conn.execute(
        "UPDATE consent_records SET status = 'revoked', updated_at = ? WHERE id = ?",
        (_now(), consent_id),
    )
    conn.commit()


def check_consent_status(
    conn: sqlite3.Connection,
    cvr: str,
) -> bool:
    """Check if an active, non-expired consent exists for a CVR.

    Args:
        conn: Database connection.
        cvr: Danish CVR number.

    Returns:
        True if active + non-expired consent exists, False otherwise.
    """
    return get_active_consent(conn, cvr) is not None
