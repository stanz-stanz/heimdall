"""Tests for src.db.delivery — delivery log CRUD."""

from __future__ import annotations

import pytest

from src.db.connection import init_db
from src.db.delivery import (
    get_delivery_history,
    get_pending_deliveries,
    log_delivery,
    update_delivery_status,
)


@pytest.fixture()
def db(tmp_path):
    """Initialised client database connection."""
    conn = init_db(tmp_path / "test.db")
    yield conn
    conn.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_log_delivery(db):
    """Create a delivery log entry, verify status='pending' + created_at set."""
    delivery_id = log_delivery(
        db, cvr="12345678", channel="telegram", message_type="scan_report",
        domain="example.dk", scan_id="scan-001",
        approved_by="federico", message_preview="Critical findings...",
        message_hash="abc123",
    )

    assert isinstance(delivery_id, int)
    assert delivery_id > 0

    row = db.execute(
        "SELECT * FROM delivery_log WHERE id = ?", (delivery_id,)
    ).fetchone()

    assert row["cvr"] == "12345678"
    assert row["channel"] == "telegram"
    assert row["message_type"] == "scan_report"
    assert row["domain"] == "example.dk"
    assert row["scan_id"] == "scan-001"
    assert row["approved_by"] == "federico"
    assert row["message_preview"] == "Critical findings..."
    assert row["message_hash"] == "abc123"
    assert row["status"] == "pending"
    assert row["created_at"] is not None
    assert row["sent_at"] is None
    assert row["delivered_at"] is None


def test_update_delivery_sent(db):
    """Update to 'sent', verify sent_at is set."""
    delivery_id = log_delivery(
        db, cvr="12345678", channel="telegram", message_type="scan_report",
    )

    update_delivery_status(db, delivery_id, "sent", external_id="tg-msg-42")

    row = db.execute(
        "SELECT * FROM delivery_log WHERE id = ?", (delivery_id,)
    ).fetchone()

    assert row["status"] == "sent"
    assert row["sent_at"] is not None
    assert row["delivered_at"] is None
    assert row["external_id"] == "tg-msg-42"


def test_update_delivery_delivered(db):
    """Update to 'delivered', verify delivered_at is set."""
    delivery_id = log_delivery(
        db, cvr="12345678", channel="telegram", message_type="scan_report",
    )

    update_delivery_status(db, delivery_id, "delivered")

    row = db.execute(
        "SELECT * FROM delivery_log WHERE id = ?", (delivery_id,)
    ).fetchone()

    assert row["status"] == "delivered"
    assert row["delivered_at"] is not None


def test_update_delivery_failed(db):
    """Update to 'failed', verify error_message stored."""
    delivery_id = log_delivery(
        db, cvr="12345678", channel="telegram", message_type="scan_report",
    )

    update_delivery_status(db, delivery_id, "failed", error_message="Telegram API timeout")

    row = db.execute(
        "SELECT * FROM delivery_log WHERE id = ?", (delivery_id,)
    ).fetchone()

    assert row["status"] == "failed"
    assert row["error_message"] == "Telegram API timeout"
    assert row["sent_at"] is None
    assert row["delivered_at"] is None


def test_get_pending_deliveries(db):
    """Create 2 pending + 1 sent, returns only 2 pending."""
    id1 = log_delivery(db, cvr="11111111", channel="telegram", message_type="scan_report")
    id2 = log_delivery(db, cvr="22222222", channel="telegram", message_type="alert")
    id3 = log_delivery(db, cvr="33333333", channel="email", message_type="follow_up")

    # Mark one as sent
    update_delivery_status(db, id3, "sent")

    pending = get_pending_deliveries(db)
    assert len(pending) == 2

    pending_ids = {p["id"] for p in pending}
    assert id1 in pending_ids
    assert id2 in pending_ids
    assert id3 not in pending_ids


def test_get_delivery_history(db):
    """Create 3 deliveries, verify ordered DESC + limit works."""
    ids = []
    for i in range(3):
        delivery_id = log_delivery(
            db, cvr="12345678", channel="telegram",
            message_type=f"type-{i}",
        )
        ids.append(delivery_id)

    history = get_delivery_history(db, "12345678")
    assert len(history) == 3

    # Verify all three deliveries are present
    history_ids = {h["id"] for h in history}
    assert history_ids == set(ids)

    # Verify created_at is non-decreasing when traversing the list (DESC order)
    for i in range(len(history) - 1):
        assert history[i]["created_at"] >= history[i + 1]["created_at"]

    # Test limit
    limited = get_delivery_history(db, "12345678", limit=2)
    assert len(limited) == 2

    # Non-existent CVR returns empty
    assert get_delivery_history(db, "99999999") == []
