"""Tests for src.db.subscriptions — Sentinel billing lifecycle."""

from __future__ import annotations

import json

import pytest

from src.db.connection import init_db
from src.db.subscriptions import (
    VALID_PAYMENT_EVENT_TYPES,
    VALID_SUBSCRIPTION_STATUSES,
    create_subscription,
    get_active_subscription,
    list_past_due,
    list_payment_events_for_cvr,
    list_payment_events_for_subscription,
    list_subscriptions_by_cvr,
    record_payment_event,
    update_subscription_status,
)


SENTINEL_MONTHLY = 39900  # 399.00 kr. in øre
SENTINEL_ANNUAL_MONTHLY = 33900  # 339.00 kr. in øre


@pytest.fixture()
def db(tmp_path):
    conn = init_db(tmp_path / "test.db")
    yield conn
    conn.close()


# ---------------------------------------------------------------------------
# Subscription creation + retrieval
# ---------------------------------------------------------------------------


class TestCreateSubscription:
    def test_defaults_monthly_sentinel_pending_payment(self, db):
        sub = create_subscription(db, cvr="12345678", amount_dkk_ore=SENTINEL_MONTHLY)
        assert sub["cvr"] == "12345678"
        assert sub["plan"] == "sentinel"
        assert sub["status"] == "pending_payment"
        assert sub["billing_period"] == "monthly"
        assert sub["amount_dkk"] == SENTINEL_MONTHLY
        assert sub["id"] is not None
        assert sub["started_at"] is not None
        assert sub["cancelled_at"] is None

    def test_rejects_non_integer_amount(self, db):
        with pytest.raises(ValueError, match="positive integer"):
            create_subscription(db, cvr="12345678", amount_dkk_ore=399.00)  # type: ignore[arg-type]

    def test_rejects_zero_or_negative_amount(self, db):
        with pytest.raises(ValueError, match="positive integer"):
            create_subscription(db, cvr="12345678", amount_dkk_ore=0)
        with pytest.raises(ValueError, match="positive integer"):
            create_subscription(db, cvr="12345678", amount_dkk_ore=-100)

    def test_rejects_invalid_status(self, db):
        with pytest.raises(ValueError, match="Invalid subscription status"):
            create_subscription(
                db,
                cvr="12345678",
                amount_dkk_ore=SENTINEL_MONTHLY,
                status="wonky",
            )

    def test_rejects_invalid_billing_period(self, db):
        with pytest.raises(ValueError, match="Invalid billing_period"):
            create_subscription(
                db,
                cvr="12345678",
                amount_dkk_ore=SENTINEL_MONTHLY,
                billing_period="quarterly",
            )

    def test_accepts_annual_billing(self, db):
        sub = create_subscription(
            db,
            cvr="12345678",
            amount_dkk_ore=SENTINEL_ANNUAL_MONTHLY,
            billing_period="annual",
        )
        assert sub["billing_period"] == "annual"
        assert sub["amount_dkk"] == SENTINEL_ANNUAL_MONTHLY


class TestStatusTransitions:
    def test_activates_from_pending_payment(self, db):
        sub = create_subscription(db, cvr="12345678", amount_dkk_ore=SENTINEL_MONTHLY)
        updated = update_subscription_status(db, sub["id"], "active")
        assert updated["status"] == "active"

    def test_cancelled_records_cancelled_at(self, db):
        sub = create_subscription(
            db,
            cvr="12345678",
            amount_dkk_ore=SENTINEL_MONTHLY,
            status="active",
        )
        updated = update_subscription_status(
            db, sub["id"], "cancelled", cancelled_at="2026-05-01T12:00:00Z"
        )
        assert updated["status"] == "cancelled"
        assert updated["cancelled_at"] == "2026-05-01T12:00:00Z"

    def test_rejects_unknown_status(self, db):
        sub = create_subscription(db, cvr="12345678", amount_dkk_ore=SENTINEL_MONTHLY)
        with pytest.raises(ValueError, match="Invalid subscription status"):
            update_subscription_status(db, sub["id"], "exploded")

    def test_missing_subscription_raises_key_error(self, db):
        with pytest.raises(KeyError):
            update_subscription_status(db, 99999, "active")


class TestQueries:
    def test_get_active_returns_latest_when_multiple(self, db):
        # Two actives (integrity-bug scenario) — should still return a row.
        create_subscription(
            db,
            cvr="12345678",
            amount_dkk_ore=SENTINEL_MONTHLY,
            status="active",
            started_at="2026-01-01T00:00:00Z",
        )
        newer = create_subscription(
            db,
            cvr="12345678",
            amount_dkk_ore=SENTINEL_MONTHLY,
            status="active",
            started_at="2026-02-01T00:00:00Z",
        )
        result = get_active_subscription(db, "12345678")
        assert result is not None
        assert result["id"] == newer["id"]

    def test_get_active_none_when_cancelled(self, db):
        sub = create_subscription(db, cvr="12345678", amount_dkk_ore=SENTINEL_MONTHLY)
        update_subscription_status(db, sub["id"], "cancelled")
        assert get_active_subscription(db, "12345678") is None

    def test_list_by_cvr_ordered_newest_first(self, db):
        a = create_subscription(
            db,
            cvr="12345678",
            amount_dkk_ore=SENTINEL_MONTHLY,
            started_at="2026-01-01T00:00:00Z",
        )
        b = create_subscription(
            db,
            cvr="12345678",
            amount_dkk_ore=SENTINEL_MONTHLY,
            started_at="2026-02-01T00:00:00Z",
        )
        rows = list_subscriptions_by_cvr(db, "12345678")
        assert [r["id"] for r in rows] == [b["id"], a["id"]]

    def test_list_past_due(self, db):
        sub = create_subscription(
            db,
            cvr="12345678",
            amount_dkk_ore=SENTINEL_MONTHLY,
            status="active",
        )
        create_subscription(
            db,
            cvr="87654321",
            amount_dkk_ore=SENTINEL_MONTHLY,
            status="past_due",
        )
        update_subscription_status(db, sub["id"], "past_due")

        rows = list_past_due(db)

        assert {r["cvr"] for r in rows} == {"12345678", "87654321"}


# ---------------------------------------------------------------------------
# Payment events
# ---------------------------------------------------------------------------


class TestRecordPaymentEvent:
    def test_records_invoice_issued(self, db):
        event = record_payment_event(
            db,
            cvr="12345678",
            event_type="invoice_issued",
            amount_dkk_ore=SENTINEL_MONTHLY,
            external_id="INV-2026-001",
        )
        assert event["cvr"] == "12345678"
        assert event["event_type"] == "invoice_issued"
        assert event["amount_dkk"] == SENTINEL_MONTHLY
        assert event["external_id"] == "INV-2026-001"

    def test_rejects_invalid_event_type(self, db):
        with pytest.raises(ValueError, match="Invalid payment event_type"):
            record_payment_event(
                db,
                cvr="12345678",
                event_type="invoked",
                amount_dkk_ore=100,
            )

    def test_negative_amount_permitted_for_refund(self, db):
        event = record_payment_event(
            db,
            cvr="12345678",
            event_type="refund",
            amount_dkk_ore=-SENTINEL_MONTHLY,
        )
        assert event["amount_dkk"] == -SENTINEL_MONTHLY

    def test_non_integer_amount_rejected(self, db):
        with pytest.raises(ValueError, match="integer"):
            record_payment_event(
                db,
                cvr="12345678",
                event_type="payment_succeeded",
                amount_dkk_ore=399.00,  # type: ignore[arg-type]
            )

    def test_payload_stored_as_json(self, db):
        event = record_payment_event(
            db,
            cvr="12345678",
            event_type="payment_failed",
            amount_dkk_ore=SENTINEL_MONTHLY,
            payload={"reason": "insufficient_funds", "bank_code": "0023"},
        )
        assert event["payload_json"] is not None
        parsed = json.loads(event["payload_json"])
        assert parsed["reason"] == "insufficient_funds"


class TestPaymentEventQueries:
    def test_list_for_cvr_newest_first(self, db):
        record_payment_event(
            db,
            cvr="12345678",
            event_type="invoice_issued",
            amount_dkk_ore=SENTINEL_MONTHLY,
            occurred_at="2026-04-01T00:00:00Z",
        )
        record_payment_event(
            db,
            cvr="12345678",
            event_type="payment_succeeded",
            amount_dkk_ore=SENTINEL_MONTHLY,
            occurred_at="2026-04-02T00:00:00Z",
        )

        rows = list_payment_events_for_cvr(db, "12345678")

        assert [r["event_type"] for r in rows] == [
            "payment_succeeded",
            "invoice_issued",
        ]

    def test_list_for_cvr_respects_limit(self, db):
        for i in range(5):
            record_payment_event(
                db,
                cvr="12345678",
                event_type="invoice_issued",
                amount_dkk_ore=SENTINEL_MONTHLY,
                occurred_at=f"2026-04-{i + 1:02d}T00:00:00Z",
            )

        rows = list_payment_events_for_cvr(db, "12345678", limit=2)
        assert len(rows) == 2

    def test_list_for_subscription(self, db):
        sub = create_subscription(
            db, cvr="12345678", amount_dkk_ore=SENTINEL_MONTHLY
        )
        record_payment_event(
            db,
            cvr="12345678",
            event_type="invoice_issued",
            amount_dkk_ore=SENTINEL_MONTHLY,
            subscription_id=sub["id"],
        )
        record_payment_event(
            db,
            cvr="12345678",
            event_type="payment_succeeded",
            amount_dkk_ore=SENTINEL_MONTHLY,
            subscription_id=sub["id"],
        )
        # Unrelated event for a different subscription.
        record_payment_event(
            db,
            cvr="12345678",
            event_type="invoice_issued",
            amount_dkk_ore=SENTINEL_MONTHLY,
        )

        rows = list_payment_events_for_subscription(db, sub["id"])
        assert len(rows) == 2


class TestEnumCoverage:
    """Guard against silent enum drift."""

    def test_subscription_statuses_expected(self):
        assert VALID_SUBSCRIPTION_STATUSES == {
            "pending_payment",
            "active",
            "past_due",
            "cancelled",
            "refunded",
        }

    def test_payment_event_types_expected(self):
        assert VALID_PAYMENT_EVENT_TYPES == {
            "invoice_issued",
            "mandate_registered",
            "payment_succeeded",
            "payment_failed",
            "refund",
            "chargeback",
            "mandate_cancelled",
        }
