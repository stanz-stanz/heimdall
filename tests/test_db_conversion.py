"""Tests for src.db.conversion — funnel events + onboarding-stage log."""

from __future__ import annotations

import json

import pytest

from src.db.clients import create_client
from src.db.connection import init_db
from src.db.conversion import (
    VALID_CONVERSION_EVENT_TYPES,
    VALID_STAGE_LOG_SOURCES,
    list_conversion_events_by_type,
    list_conversion_events_for_cvr,
    list_stage_log_for_cvr,
    record_conversion_event,
    record_stage_transition,
    transition_onboarding_stage,
)


@pytest.fixture()
def db(tmp_path):
    conn = init_db(tmp_path / "test.db")
    yield conn
    conn.close()


@pytest.fixture()
def client(db):
    return create_client(
        db,
        cvr="12345678",
        company_name="Test Co",
        status="onboarding",
        plan="sentinel",
    )


# ---------------------------------------------------------------------------
# Conversion events
# ---------------------------------------------------------------------------


class TestRecordConversionEvent:
    def test_records_signup(self, db):
        event = record_conversion_event(
            db, cvr="12345678", event_type="signup", source="email_click"
        )
        assert event["cvr"] == "12345678"
        assert event["event_type"] == "signup"
        assert event["source"] == "email_click"
        assert event["payload_json"] is None

    def test_payload_stored_as_json(self, db):
        event = record_conversion_event(
            db,
            cvr="12345678",
            event_type="consent_signed",
            payload={"domain_count": 3, "mitid_actor_role": "OWNER"},
        )
        assert event["payload_json"] is not None
        parsed = json.loads(event["payload_json"])
        assert parsed["domain_count"] == 3

    def test_rejects_unknown_event_type(self, db):
        with pytest.raises(ValueError, match="Invalid conversion event_type"):
            record_conversion_event(
                db, cvr="12345678", event_type="re_engagement"
            )

    def test_cvr_not_foreign_key_enforced(self, db):
        # signup fires before the clients row exists — must not FK-fail.
        event = record_conversion_event(
            db, cvr="99999999", event_type="signup"
        )
        assert event["cvr"] == "99999999"

    def test_accepts_explicit_occurred_at(self, db):
        event = record_conversion_event(
            db,
            cvr="12345678",
            event_type="cta_click",
            occurred_at="2026-04-23T10:00:00Z",
        )
        assert event["occurred_at"] == "2026-04-23T10:00:00Z"


class TestConversionQueries:
    def test_list_for_cvr_newest_first(self, db):
        record_conversion_event(
            db,
            cvr="12345678",
            event_type="signup",
            occurred_at="2026-04-01T00:00:00Z",
        )
        record_conversion_event(
            db,
            cvr="12345678",
            event_type="cta_click",
            occurred_at="2026-04-23T00:00:00Z",
        )
        rows = list_conversion_events_for_cvr(db, "12345678")
        assert [r["event_type"] for r in rows] == ["cta_click", "signup"]

    def test_list_for_cvr_respects_limit(self, db):
        for i in range(5):
            record_conversion_event(
                db,
                cvr="12345678",
                event_type="cta_click",
                occurred_at=f"2026-04-{i + 1:02d}T00:00:00Z",
            )
        assert len(list_conversion_events_for_cvr(db, "12345678", limit=2)) == 2

    def test_list_by_type_filters(self, db):
        record_conversion_event(db, cvr="12345678", event_type="signup")
        record_conversion_event(db, cvr="87654321", event_type="signup")
        record_conversion_event(db, cvr="12345678", event_type="cta_click")

        signups = list_conversion_events_by_type(db, "signup")

        assert {r["cvr"] for r in signups} == {"12345678", "87654321"}
        assert all(r["event_type"] == "signup" for r in signups)

    def test_list_by_type_validates(self, db):
        with pytest.raises(ValueError, match="Invalid conversion event_type"):
            list_conversion_events_by_type(db, "nope")


# ---------------------------------------------------------------------------
# Onboarding stage log
# ---------------------------------------------------------------------------


class TestRecordStageTransition:
    def test_records_entry_into_funnel(self, db, client):
        row = record_stage_transition(
            db,
            cvr=client["cvr"],
            from_stage=None,
            to_stage="upgrade_interest",
            source="webhook",
        )
        assert row["from_stage"] is None
        assert row["to_stage"] == "upgrade_interest"
        assert row["source"] == "webhook"

    def test_records_exit_to_active(self, db, client):
        row = record_stage_transition(
            db,
            cvr=client["cvr"],
            from_stage="provisioning",
            to_stage=None,
            source="system",
            note="Betalingsservice mandate confirmed",
        )
        assert row["from_stage"] == "provisioning"
        assert row["to_stage"] is None

    def test_rejects_unknown_stage(self, db, client):
        with pytest.raises(ValueError, match="Invalid onboarding_stage"):
            record_stage_transition(
                db,
                cvr=client["cvr"],
                from_stage=None,
                to_stage="pending_bogus",
            )

    def test_rejects_unknown_source(self, db, client):
        with pytest.raises(ValueError, match="Invalid stage-log source"):
            record_stage_transition(
                db,
                cvr=client["cvr"],
                from_stage=None,
                to_stage="pending_payment",
                source="cli",
            )

    def test_source_may_be_none(self, db, client):
        row = record_stage_transition(
            db,
            cvr=client["cvr"],
            from_stage=None,
            to_stage="pending_payment",
        )
        assert row["source"] is None


class TestTransitionOnboardingStage:
    def test_updates_client_and_logs(self, db, client):
        updated = transition_onboarding_stage(
            db,
            cvr=client["cvr"],
            to_stage="pending_payment",
            source="webhook",
        )
        assert updated["onboarding_stage"] == "pending_payment"

        log = list_stage_log_for_cvr(db, client["cvr"])
        assert len(log) == 1
        assert log[0]["from_stage"] is None
        assert log[0]["to_stage"] == "pending_payment"
        assert log[0]["source"] == "webhook"

    def test_sequential_transitions_all_logged(self, db, client):
        transition_onboarding_stage(
            db, cvr=client["cvr"], to_stage="upgrade_interest", source="operator"
        )
        transition_onboarding_stage(
            db, cvr=client["cvr"], to_stage="pending_payment", source="webhook"
        )
        transition_onboarding_stage(
            db, cvr=client["cvr"], to_stage="pending_consent", source="webhook"
        )

        log = list_stage_log_for_cvr(db, client["cvr"])

        # Newest first.
        assert [r["to_stage"] for r in log] == [
            "pending_consent",
            "pending_payment",
            "upgrade_interest",
        ]
        assert [r["from_stage"] for r in log] == [
            "pending_payment",
            "upgrade_interest",
            None,
        ]

    def test_same_stage_is_noop(self, db, client):
        transition_onboarding_stage(
            db, cvr=client["cvr"], to_stage="pending_payment", source="webhook"
        )
        # Retry — should not duplicate log row or re-update.
        transition_onboarding_stage(
            db, cvr=client["cvr"], to_stage="pending_payment", source="webhook"
        )
        assert len(list_stage_log_for_cvr(db, client["cvr"])) == 1

    def test_missing_client_raises_key_error(self, db):
        with pytest.raises(KeyError):
            transition_onboarding_stage(
                db, cvr="99999999", to_stage="pending_payment"
            )

    def test_exit_to_active_logs_transition(self, db, client):
        transition_onboarding_stage(db, cvr=client["cvr"], to_stage="provisioning")
        final = transition_onboarding_stage(
            db, cvr=client["cvr"], to_stage=None, source="system"
        )
        assert final["onboarding_stage"] is None
        log = list_stage_log_for_cvr(db, client["cvr"])
        assert log[0]["from_stage"] == "provisioning"
        assert log[0]["to_stage"] is None


class TestEnumCoverage:
    """Guard against silent drift of the enum constants."""

    def test_conversion_event_types_expected(self):
        assert VALID_CONVERSION_EVENT_TYPES == {
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
        }

    def test_stage_log_sources_expected(self):
        assert VALID_STAGE_LOG_SOURCES == {
            "webhook",
            "operator",
            "cron",
            "system",
        }
