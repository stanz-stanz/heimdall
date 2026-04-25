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


# ---------------------------------------------------------------------------
# Webhook idempotency: payment_events provider/external_id/event_type uniqueness
# (R3 from the 2026-04-25 cloud-hosting plan)
# ---------------------------------------------------------------------------


class TestPaymentEventIdempotency:
    """Partial UNIQUE index on (provider, external_id, event_type).

    Webhook delivery is at-least-once; NETS may retry the same event
    multiple times after a delivery timeout. The partial UNIQUE index
    enforces deduplication at the storage layer so the application
    cannot accidentally double-credit a payment, even if the webhook
    handler is invoked twice. Reconciliation rows with NULL external_id
    are exempt — they have no provider-side reference to dedupe against.
    """

    def test_unique_index_exists_after_init_db(self, db):
        rows = db.execute(
            "PRAGMA index_list(payment_events)"
        ).fetchall()
        index_names = {r[1] for r in rows}
        assert "uq_payment_events_provider_extid_eventtype" in index_names
        # Confirm it is a UNIQUE index (column 2 of index_list = unique flag).
        unique_flags = {r[1]: bool(r[2]) for r in rows}
        assert unique_flags["uq_payment_events_provider_extid_eventtype"] is True

    def test_provider_column_default_is_betalingsservice(self, db):
        sub = create_subscription(db, cvr="12345678", amount_dkk_ore=SENTINEL_MONTHLY)
        evt = record_payment_event(
            db,
            cvr="12345678",
            subscription_id=sub["id"],
            event_type="payment_succeeded",
            amount_dkk_ore=SENTINEL_MONTHLY,
            external_id="NETS-REF-1",
        )
        # Existing record_payment_event INSERT does not name `provider`;
        # the column default keeps the call site working unchanged.
        assert evt["provider"] == "betalingsservice"

    def test_duplicate_provider_extid_eventtype_rejected(self, db):
        import sqlite3
        sub = create_subscription(db, cvr="12345678", amount_dkk_ore=SENTINEL_MONTHLY)
        record_payment_event(
            db,
            cvr="12345678",
            subscription_id=sub["id"],
            event_type="payment_succeeded",
            amount_dkk_ore=SENTINEL_MONTHLY,
            external_id="NETS-REF-DUP",
        )
        with pytest.raises(sqlite3.IntegrityError):
            record_payment_event(
                db,
                cvr="12345678",
                subscription_id=sub["id"],
                event_type="payment_succeeded",
                amount_dkk_ore=SENTINEL_MONTHLY,
                external_id="NETS-REF-DUP",
            )

    def test_same_extid_different_event_type_allowed(self, db):
        # mandate_registered + payment_succeeded share an external_id —
        # both rows should land. The (provider, external_id, event_type)
        # tuple still differs.
        sub = create_subscription(db, cvr="12345678", amount_dkk_ore=SENTINEL_MONTHLY)
        record_payment_event(
            db,
            cvr="12345678",
            subscription_id=sub["id"],
            event_type="mandate_registered",
            amount_dkk_ore=0,
            external_id="NETS-REF-SHARED",
        )
        record_payment_event(
            db,
            cvr="12345678",
            subscription_id=sub["id"],
            event_type="payment_succeeded",
            amount_dkk_ore=SENTINEL_MONTHLY,
            external_id="NETS-REF-SHARED",
        )
        events = list_payment_events_for_cvr(db, "12345678")
        assert len(events) == 2

    def test_null_external_id_exempt_from_unique(self, db):
        # Reconciliation entries with no NETS reference must coexist
        # even when the (provider, event_type) tuple repeats. The
        # partial index excludes external_id IS NULL.
        sub = create_subscription(db, cvr="12345678", amount_dkk_ore=SENTINEL_MONTHLY)
        for _ in range(3):
            record_payment_event(
                db,
                cvr="12345678",
                subscription_id=sub["id"],
                event_type="payment_failed",
                amount_dkk_ore=SENTINEL_MONTHLY,
                external_id=None,
            )
        events = list_payment_events_for_cvr(db, "12345678")
        assert len(events) == 3

    def test_legacy_duplicates_block_migration(self, db):
        # Simulate a legacy database that pre-dates the unique index
        # (was migrated without the dedup constraint and accumulated
        # duplicate webhook deliveries before we added the guard).
        # The migration must refuse to apply rather than silently
        # mutate bookkeeping data.
        from src.db.migrate import LegacyDataIntegrityError, apply_pending_migrations

        sub = create_subscription(db, cvr="12345678", amount_dkk_ore=SENTINEL_MONTHLY)
        # Drop the unique index so we can insert duplicates (mirrors
        # the legacy DB that never had the index in the first place).
        db.execute("DROP INDEX IF EXISTS uq_payment_events_provider_extid_eventtype")
        record_payment_event(
            db,
            cvr="12345678",
            subscription_id=sub["id"],
            event_type="payment_succeeded",
            amount_dkk_ore=SENTINEL_MONTHLY,
            external_id="NETS-LEGACY-DUP",
        )
        record_payment_event(
            db,
            cvr="12345678",
            subscription_id=sub["id"],
            event_type="payment_succeeded",
            amount_dkk_ore=SENTINEL_MONTHLY,
            external_id="NETS-LEGACY-DUP",
        )
        with pytest.raises(LegacyDataIntegrityError) as excinfo:
            apply_pending_migrations(db)
        msg = str(excinfo.value)
        assert "NETS-LEGACY-DUP" in msg
        assert "Diagnostic query" in msg
        assert "payment_succeeded" in msg

    def test_clean_database_passes_pre_flight(self, db):
        # Clean DB (zero or non-duplicate payment_events rows) must
        # not be blocked by the pre-flight. Re-running the migration
        # is the idempotent path; verify it works.
        from src.db.migrate import apply_pending_migrations

        sub = create_subscription(db, cvr="12345678", amount_dkk_ore=SENTINEL_MONTHLY)
        record_payment_event(
            db,
            cvr="12345678",
            subscription_id=sub["id"],
            event_type="payment_succeeded",
            amount_dkk_ore=SENTINEL_MONTHLY,
            external_id="NETS-UNIQUE-1",
        )
        # Should be a no-op; no error raised.
        added = apply_pending_migrations(db)
        assert added == []
