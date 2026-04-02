"""CRUD operations for the delivery log.

Follows the enrichment/db.py pattern: plain functions, Row dicts, _now() timestamps.
"""

from __future__ import annotations

import sqlite3

from src.db.connection import _now


def log_delivery(
    conn: sqlite3.Connection,
    cvr: str,
    channel: str,
    message_type: str,
    domain: str | None = None,
    scan_id: str | None = None,
    approved_by: str = "",
    message_preview: str | None = None,
    message_hash: str | None = None,
) -> int:
    """Create a delivery_log entry with status='pending'.

    Args:
        conn: Database connection.
        cvr: Danish CVR number for the recipient.
        channel: Delivery channel (telegram | email | whatsapp).
        message_type: Type of message (scan_report | alert | follow_up | welcome | custom).
        domain: Optional domain this message concerns.
        scan_id: Optional FK to scan_history.
        approved_by: Who approved the message (e.g. "federico").
        message_preview: First 200 chars of message text for log readability.
        message_hash: SHA-256 hash of message text for dedup.

    Returns:
        The id of the newly created delivery_log entry.
    """
    now = _now()
    cursor = conn.execute(
        "INSERT INTO delivery_log ("
        "cvr, domain, channel, message_type, scan_id, "
        "approved_by, message_hash, message_preview, "
        "status, created_at"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)",
        (cvr, domain, channel, message_type, scan_id,
         approved_by, message_hash, message_preview, now),
    )
    conn.commit()
    return cursor.lastrowid  # type: ignore[return-value]


def update_delivery_status(
    conn: sqlite3.Connection,
    delivery_id: int,
    status: str,
    error_message: str | None = None,
    external_id: str | None = None,
) -> None:
    """Update delivery status with timestamp tracking.

    Sets sent_at when status='sent', delivered_at when status='delivered'.

    Args:
        conn: Database connection.
        delivery_id: Primary key of the delivery_log entry.
        status: New status (sent | delivered | failed | rejected).
        error_message: Error details if status is 'failed'.
        external_id: External message ID (e.g. Telegram message_id).
    """
    now = _now()
    sent_at_clause = ", sent_at = ?" if status == "sent" else ""
    delivered_at_clause = ", delivered_at = ?" if status == "delivered" else ""

    sql = (
        f"UPDATE delivery_log SET status = ?, error_message = ?, external_id = ?"
        f"{sent_at_clause}{delivered_at_clause} "
        f"WHERE id = ?"
    )

    params: list = [status, error_message, external_id]
    if status == "sent":
        params.append(now)
    if status == "delivered":
        params.append(now)
    params.append(delivery_id)

    conn.execute(sql, params)
    conn.commit()


def get_pending_deliveries(
    conn: sqlite3.Connection,
) -> list[dict]:
    """Get all pending deliveries.

    Args:
        conn: Database connection.

    Returns:
        List of row dicts with status='pending', ordered by created_at ASC.
    """
    rows = conn.execute(
        "SELECT * FROM delivery_log WHERE status = 'pending' "
        "ORDER BY created_at ASC"
    ).fetchall()
    return [dict(r) for r in rows]


def get_delivery_history(
    conn: sqlite3.Connection,
    cvr: str,
    limit: int = 20,
) -> list[dict]:
    """Get delivery history for a client, ordered by created_at DESC.

    Args:
        conn: Database connection.
        cvr: Danish CVR number.
        limit: Maximum number of rows to return.

    Returns:
        List of row dicts, newest first.
    """
    rows = conn.execute(
        "SELECT * FROM delivery_log WHERE cvr = ? "
        "ORDER BY created_at DESC LIMIT ?",
        (cvr, limit),
    ).fetchall()
    return [dict(r) for r in rows]
