"""Tests for src.db.console_views — operator-console list queries."""

from __future__ import annotations

import pytest

from src.db.clients import add_domain, create_client
from src.db.connection import init_db
from src.db.console_views import (
    list_retention_queue_pending_due,
    list_trial_expiring,
)
from src.db.conversion import record_conversion_event
from src.db.retention import (
    mark_retention_job_completed,
    mark_retention_job_failed,
    schedule_retention_job,
)


@pytest.fixture()
def db(tmp_path):
    conn = init_db(tmp_path / "test.db")
    yield conn
    conn.close()


def _trial(
    db,
    cvr: str,
    company: str,
    *,
    started: str,
    expires: str,
    status: str = "watchman_active",
    domain: str | None = None,
):
    """Helper: create a Watchman client with explicit trial window."""
    create_client(
        db,
        cvr=cvr,
        company_name=company,
        plan="watchman",
        status=status,
        trial_started_at=started,
        trial_expires_at=expires,
    )
    if domain:
        add_domain(db, cvr, domain, is_primary=1)


# ---------------------------------------------------------------------------
# V1 — list_trial_expiring
# ---------------------------------------------------------------------------


NOW = "2026-04-26T12:00:00Z"


class TestListTrialExpiringEmpty:
    def test_empty_db(self, db):
        assert list_trial_expiring(db, now=NOW) == []

    def test_no_watchman_clients(self, db):
        create_client(
            db,
            cvr="11111111",
            company_name="Sentinel client",
            plan="sentinel",
            status="active",
        )
        assert list_trial_expiring(db, now=NOW) == []


class TestListTrialExpiringWindow:
    def test_includes_trial_expiring_within_default_7d(self, db):
        _trial(
            db,
            "11111111",
            "Kro Jelling",
            started="2026-04-01T00:00:00Z",
            expires="2026-05-01T00:00:00Z",  # 5 days from NOW
            domain="krojelling.dk",
        )
        rows = list_trial_expiring(db, now=NOW)
        assert len(rows) == 1
        assert rows[0]["cvr"] == "11111111"
        assert rows[0]["domain"] == "krojelling.dk"

    def test_excludes_trial_expiring_outside_window(self, db):
        _trial(
            db,
            "22222222",
            "Far future",
            started="2026-04-01T00:00:00Z",
            expires="2027-01-01T00:00:00Z",  # well beyond 7d
        )
        assert list_trial_expiring(db, now=NOW) == []

    def test_excludes_already_expired_trials(self, db):
        # trial_expires_at in the past — operator no longer needs the
        # nudge; the retention cron is the right surface for these.
        _trial(
            db,
            "33333333",
            "Already gone",
            started="2026-03-01T00:00:00Z",
            expires="2026-04-01T00:00:00Z",
        )
        assert list_trial_expiring(db, now=NOW) == []

    def test_window_widens_to_14d(self, db):
        _trial(
            db,
            "44444444",
            "10d out",
            started="2026-04-01T00:00:00Z",
            expires="2026-05-06T00:00:00Z",
        )
        # 7d window excludes; 14d includes.
        assert list_trial_expiring(db, now=NOW) == []
        wider = list_trial_expiring(db, now=NOW, window_days=14)
        assert [r["cvr"] for r in wider] == ["44444444"]

    def test_zero_window_returns_empty(self, db):
        _trial(
            db,
            "55555555",
            "expiring tomorrow",
            started="2026-04-01T00:00:00Z",
            expires="2026-04-27T00:00:00Z",
        )
        assert list_trial_expiring(db, now=NOW, window_days=0) == []


class TestListTrialExpiringStatusFilter:
    def test_excludes_already_expired_status(self, db):
        # trial window still in the future, but status moved on.
        _trial(
            db,
            "66666666",
            "Expired flagged",
            started="2026-04-01T00:00:00Z",
            expires="2026-05-01T00:00:00Z",
            status="watchman_expired",
        )
        assert list_trial_expiring(db, now=NOW) == []

    def test_excludes_active_sentinel(self, db):
        create_client(
            db,
            cvr="77777777",
            company_name="Sentinel mid-trial",
            plan="sentinel",
            status="active",
            trial_started_at="2026-04-01T00:00:00Z",
            trial_expires_at="2026-05-01T00:00:00Z",
        )
        assert list_trial_expiring(db, now=NOW) == []


class TestListTrialExpiringConversionFilter:
    def test_signup_only_does_not_exclude(self, db):
        _trial(
            db,
            "88888888",
            "Trialist no engagement",
            started="2026-04-01T00:00:00Z",
            expires="2026-05-01T00:00:00Z",
        )
        record_conversion_event(db, "88888888", "signup")
        rows = list_trial_expiring(db, now=NOW)
        assert [r["cvr"] for r in rows] == ["88888888"]

    def test_consent_signed_excludes(self, db):
        _trial(
            db,
            "99999999",
            "Trialist mid-consent",
            started="2026-04-01T00:00:00Z",
            expires="2026-05-01T00:00:00Z",
        )
        record_conversion_event(db, "99999999", "consent_signed")
        assert list_trial_expiring(db, now=NOW) == []

    def test_cta_click_excludes(self, db):
        _trial(
            db,
            "10101010",
            "CTA clicker",
            started="2026-04-01T00:00:00Z",
            expires="2026-05-01T00:00:00Z",
        )
        record_conversion_event(db, "10101010", "cta_click")
        assert list_trial_expiring(db, now=NOW) == []

    def test_cancellation_does_not_exclude(self, db):
        # 'cancellation' is a terminal marker, not Sentinel-conversion
        # intent. Still, the operator probably doesn't want to chase a
        # cancelled trial — but per the strict spec only conversion-
        # intent events filter the view. The status filter handles
        # post-cancellation rows separately (the trial flips to
        # watchman_expired). This test pins the spec-literal behaviour.
        _trial(
            db,
            "20202020",
            "Cancelled but still watchman_active",
            started="2026-04-01T00:00:00Z",
            expires="2026-05-01T00:00:00Z",
        )
        record_conversion_event(db, "20202020", "cancellation")
        rows = list_trial_expiring(db, now=NOW)
        assert [r["cvr"] for r in rows] == ["20202020"]


class TestListTrialExpiringOrdering:
    def test_most_urgent_first(self, db):
        _trial(
            db,
            "30303030",
            "Five days",
            started="2026-04-01T00:00:00Z",
            expires="2026-05-01T00:00:00Z",  # +5d
        )
        _trial(
            db,
            "40404040",
            "Two days",
            started="2026-04-01T00:00:00Z",
            expires="2026-04-28T00:00:00Z",  # +2d
        )
        rows = list_trial_expiring(db, now=NOW)
        assert [r["cvr"] for r in rows] == ["40404040", "30303030"]

    def test_days_remaining_is_floor(self, db):
        _trial(
            db,
            "50505050",
            "T+3 days",
            started="2026-04-01T00:00:00Z",
            expires="2026-04-29T00:00:00Z",  # NOW + 2.5 days → floor=2
        )
        rows = list_trial_expiring(db, now=NOW)
        assert rows[0]["days_remaining"] == 2


# ---------------------------------------------------------------------------
# V6 — list_retention_queue_pending_due
# ---------------------------------------------------------------------------


class TestListRetentionQueueEmpty:
    def test_empty_db(self, db):
        assert list_retention_queue_pending_due(db, now=NOW) == []


class TestListRetentionQueueDueFilter:
    def test_includes_pending_due(self, db):
        create_client(db, cvr="11111111", company_name="Kro Jelling")
        add_domain(db, "11111111", "krojelling.dk", is_primary=1)
        schedule_retention_job(
            db,
            cvr="11111111",
            action="purge",
            scheduled_for="2026-04-25T00:00:00Z",  # before NOW
        )
        rows = list_retention_queue_pending_due(db, now=NOW)
        assert len(rows) == 1
        assert rows[0]["company_name"] == "Kro Jelling"
        assert rows[0]["domain"] == "krojelling.dk"
        assert rows[0]["status"] == "pending"

    def test_excludes_pending_not_yet_due(self, db):
        create_client(db, cvr="22222222", company_name="Future")
        schedule_retention_job(
            db,
            cvr="22222222",
            action="purge",
            scheduled_for="2099-01-01T00:00:00Z",
        )
        assert list_retention_queue_pending_due(db, now=NOW) == []

    def test_excludes_running(self, db):
        create_client(db, cvr="33333333", company_name="Running")
        job = schedule_retention_job(
            db,
            cvr="33333333",
            action="purge",
            scheduled_for="2026-04-25T00:00:00Z",
        )
        # Manually flip to running (the cron path; we're not testing the
        # cron here, just the filter behaviour).
        db.execute(
            "UPDATE retention_jobs SET status = 'running', claimed_at = ? WHERE id = ?",
            (NOW, job["id"]),
        )
        db.commit()
        assert list_retention_queue_pending_due(db, now=NOW) == []

    def test_excludes_completed(self, db):
        create_client(db, cvr="44444444", company_name="Done")
        job = schedule_retention_job(
            db,
            cvr="44444444",
            action="purge",
            scheduled_for="2026-04-25T00:00:00Z",
        )
        mark_retention_job_completed(db, job["id"])
        assert list_retention_queue_pending_due(db, now=NOW) == []

    def test_excludes_failed(self, db):
        create_client(db, cvr="55555555", company_name="Boom")
        job = schedule_retention_job(
            db,
            cvr="55555555",
            action="purge",
            scheduled_for="2026-04-25T00:00:00Z",
        )
        mark_retention_job_failed(db, job["id"], error="rds 5xx")
        assert list_retention_queue_pending_due(db, now=NOW) == []


class TestListRetentionQueueOrphanedClient:
    def test_returns_row_when_client_already_purged(self, db):
        # The Watchman purge can hard-delete the clients row. The
        # retention_jobs audit row survives one tick longer; operator
        # still needs to see it.
        schedule_retention_job(
            db,
            cvr="ORPHAN01",
            action="purge",
            scheduled_for="2026-04-25T00:00:00Z",
        )
        rows = list_retention_queue_pending_due(db, now=NOW)
        assert len(rows) == 1
        assert rows[0]["cvr"] == "ORPHAN01"
        assert rows[0]["company_name"] is None
        assert rows[0]["domain"] is None


class TestListRetentionQueueOrdering:
    def test_oldest_due_first(self, db):
        create_client(db, cvr="11111111", company_name="Older")
        create_client(db, cvr="22222222", company_name="Newer")
        newer = schedule_retention_job(
            db,
            cvr="22222222",
            action="purge",
            scheduled_for="2026-04-26T00:00:00Z",
        )
        older = schedule_retention_job(
            db,
            cvr="11111111",
            action="purge",
            scheduled_for="2026-04-20T00:00:00Z",
        )
        rows = list_retention_queue_pending_due(db, now=NOW)
        assert [r["id"] for r in rows] == [older["id"], newer["id"]]


class TestListRetentionQueuePagination:
    def test_limit_and_offset(self, db):
        for i in range(5):
            cvr = f"CLIENT{i:02d}"
            create_client(db, cvr=cvr, company_name=f"C{i}")
            schedule_retention_job(
                db,
                cvr=cvr,
                action="purge",
                scheduled_for=f"2026-04-2{i}T00:00:00Z",
            )
        page1 = list_retention_queue_pending_due(db, now=NOW, limit=2, offset=0)
        page2 = list_retention_queue_pending_due(db, now=NOW, limit=2, offset=2)
        assert len(page1) == 2
        assert len(page2) == 2
        assert {r["id"] for r in page1}.isdisjoint({r["id"] for r in page2})


# ---------------------------------------------------------------------------
# Multi-primary client_domains rows must not fan out result rows
# (Codex P2 finding 2026-04-26).
# ---------------------------------------------------------------------------


class TestMultiPrimaryDomainCollapse:
    def test_v1_returns_one_row_per_cvr(self, db):
        _trial(
            db,
            "MULTI001",
            "Two primary domains",
            started="2026-04-01T00:00:00Z",
            expires="2026-05-01T00:00:00Z",
        )
        # Both rows tagged primary — schema permits this; our query
        # must collapse them to one result row per CVR.
        add_domain(db, "MULTI001", "alpha.dk", is_primary=1)
        add_domain(db, "MULTI001", "bravo.dk", is_primary=1)
        rows = list_trial_expiring(db, now=NOW)
        assert len(rows) == 1
        # MIN(domain) is deterministic — alphabetical first.
        assert rows[0]["domain"] == "alpha.dk"

    def test_v6_returns_one_row_per_job(self, db):
        create_client(db, cvr="MULTI002", company_name="Two primaries")
        add_domain(db, "MULTI002", "alpha.dk", is_primary=1)
        add_domain(db, "MULTI002", "bravo.dk", is_primary=1)
        schedule_retention_job(
            db,
            cvr="MULTI002",
            action="purge",
            scheduled_for="2026-04-25T00:00:00Z",
        )
        rows = list_retention_queue_pending_due(db, now=NOW)
        assert len(rows) == 1
        assert rows[0]["domain"] == "alpha.dk"
