"""Tests for src.db.retention — GDPR offboarding jobs + tiered scheduling."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from src.db.clients import create_client, get_client
from src.db.connection import init_db
from src.db.retention import (
    SENTINEL_ANONYMISE_DAYS,
    SENTINEL_BOOKKEEPING_PURGE_DAYS,
    VALID_DATA_RETENTION_MODES,
    VALID_RETENTION_ACTIONS,
    VALID_RETENTION_JOB_STATUSES,
    cancel_retention_job,
    claim_due_retention_jobs,
    force_run_retention_job,
    list_due_retention_jobs,
    list_retention_jobs_for_cvr,
    mark_retention_job_completed,
    mark_retention_job_failed,
    reap_stuck_running_jobs,
    retry_failed_retention_job,
    schedule_churn_retention,
    schedule_retention_job,
    set_data_retention_mode,
)


@pytest.fixture()
def db(tmp_path):
    conn = init_db(tmp_path / "test.db")
    yield conn
    conn.close()


@pytest.fixture()
def watchman_client(db):
    return create_client(
        db,
        cvr="12345678",
        company_name="Kro Jelling",
        plan="watchman",
        status="watchman_active",
    )


@pytest.fixture()
def sentinel_client(db):
    return create_client(
        db,
        cvr="87654321",
        company_name="Fysio Vejle",
        plan="sentinel",
        status="active",
    )


def _days_between(a_iso: str, b_iso: str) -> float:
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    a = datetime.strptime(a_iso, fmt).replace(tzinfo=UTC)
    b = datetime.strptime(b_iso, fmt).replace(tzinfo=UTC)
    return (b - a).total_seconds() / 86400.0


# ---------------------------------------------------------------------------
# Low-level CRUD
# ---------------------------------------------------------------------------


class TestScheduleRetentionJob:
    def test_defaults_to_pending(self, db):
        job = schedule_retention_job(
            db,
            cvr="12345678",
            action="anonymise",
            scheduled_for="2026-07-23T00:00:00Z",
        )
        assert job["status"] == "pending"
        assert job["action"] == "anonymise"
        assert job["scheduled_for"] == "2026-07-23T00:00:00Z"
        assert job["executed_at"] is None

    def test_rejects_unknown_action(self, db):
        with pytest.raises(ValueError, match="Invalid retention action"):
            schedule_retention_job(
                db,
                cvr="12345678",
                action="wipe",
                scheduled_for="2026-07-23T00:00:00Z",
            )

    def test_accepts_export(self, db):
        job = schedule_retention_job(
            db,
            cvr="12345678",
            action="export",
            scheduled_for="2026-05-01T00:00:00Z",
        )
        assert job["action"] == "export"


class TestListDue:
    def test_returns_only_pending_and_overdue(self, db):
        overdue = schedule_retention_job(
            db,
            cvr="11111111",
            action="anonymise",
            scheduled_for="2026-01-01T00:00:00Z",
        )
        # Future job should not come back.
        schedule_retention_job(
            db,
            cvr="22222222",
            action="anonymise",
            scheduled_for="2099-01-01T00:00:00Z",
        )

        due = list_due_retention_jobs(db, now="2026-04-24T12:00:00Z")

        assert [j["id"] for j in due] == [overdue["id"]]

    def test_ignores_completed(self, db):
        job = schedule_retention_job(
            db,
            cvr="11111111",
            action="purge",
            scheduled_for="2026-01-01T00:00:00Z",
        )
        mark_retention_job_completed(db, job["id"])
        assert list_due_retention_jobs(db, now="2026-04-24T12:00:00Z") == []

    def test_ordered_oldest_first(self, db):
        older = schedule_retention_job(
            db,
            cvr="11111111",
            action="anonymise",
            scheduled_for="2026-01-01T00:00:00Z",
        )
        newer = schedule_retention_job(
            db,
            cvr="22222222",
            action="anonymise",
            scheduled_for="2026-02-01T00:00:00Z",
        )

        due = list_due_retention_jobs(db, now="2026-04-24T12:00:00Z")

        assert [j["id"] for j in due] == [older["id"], newer["id"]]


class TestLifecycleTransitions:
    def test_mark_completed_stamps_executed_at(self, db):
        job = schedule_retention_job(
            db,
            cvr="12345678",
            action="anonymise",
            scheduled_for="2026-01-01T00:00:00Z",
        )
        completed = mark_retention_job_completed(db, job["id"])
        assert completed["status"] == "completed"
        assert completed["executed_at"] is not None

    def test_mark_completed_overwrites_notes_when_supplied(self, db):
        job = schedule_retention_job(
            db,
            cvr="12345678",
            action="anonymise",
            scheduled_for="2026-01-01T00:00:00Z",
            notes="original",
        )
        completed = mark_retention_job_completed(
            db, job["id"], notes="rows anonymised: 47"
        )
        assert completed["notes"] == "rows anonymised: 47"

    def test_mark_failed_records_error(self, db):
        job = schedule_retention_job(
            db,
            cvr="12345678",
            action="purge",
            scheduled_for="2026-01-01T00:00:00Z",
        )
        failed = mark_retention_job_failed(db, job["id"], error="FK violation")
        assert failed["status"] == "failed"
        assert failed["notes"] == "FK violation"

    def test_cancel_retention_job(self, db):
        job = schedule_retention_job(
            db,
            cvr="12345678",
            action="purge",
            scheduled_for="2099-01-01T00:00:00Z",
        )
        cancelled = cancel_retention_job(db, job["id"], notes="re-activated")
        assert cancelled["status"] == "cancelled"
        assert cancelled["notes"] == "re-activated"

    def test_mark_completed_missing_raises(self, db):
        with pytest.raises(KeyError):
            mark_retention_job_completed(db, 99999)


class TestListByCvr:
    def test_soonest_first(self, db):
        later = schedule_retention_job(
            db,
            cvr="12345678",
            action="purge",
            scheduled_for="2027-01-01T00:00:00Z",
        )
        sooner = schedule_retention_job(
            db,
            cvr="12345678",
            action="anonymise",
            scheduled_for="2026-05-01T00:00:00Z",
        )

        rows = list_retention_jobs_for_cvr(db, "12345678")

        assert [r["id"] for r in rows] == [sooner["id"], later["id"]]


# ---------------------------------------------------------------------------
# Operator-console interventions (V6)
# ---------------------------------------------------------------------------


class TestForceRunRetentionJob:
    def test_advances_scheduled_for_to_now(self, db):
        job = schedule_retention_job(
            db,
            cvr="12345678",
            action="purge",
            scheduled_for="2099-01-01T00:00:00Z",
        )
        updated = force_run_retention_job(db, job["id"], operator="alice")
        assert updated["status"] == "pending"
        assert updated["scheduled_for"] < "2099-01-01T00:00:00Z"

    def test_appends_audit_note_without_dropping_prior(self, db):
        job = schedule_retention_job(
            db,
            cvr="12345678",
            action="purge",
            scheduled_for="2099-01-01T00:00:00Z",
            notes="watchman non-converter",
        )
        updated = force_run_retention_job(db, job["id"], operator="alice")
        assert "watchman non-converter" in updated["notes"]
        assert "force-run by alice" in updated["notes"]

    def test_appends_with_no_prior_note(self, db):
        job = schedule_retention_job(
            db,
            cvr="12345678",
            action="purge",
            scheduled_for="2099-01-01T00:00:00Z",
        )
        updated = force_run_retention_job(db, job["id"])
        assert updated["notes"].startswith("[force-run by console")

    def test_refuses_running_job(self, db):
        job = schedule_retention_job(
            db,
            cvr="12345678",
            action="purge",
            scheduled_for="2026-01-01T00:00:00Z",
        )
        # Promote to running via the claim-lock path.
        claim_due_retention_jobs(db, now="2026-04-24T00:00:00Z")
        with pytest.raises(KeyError, match="not pending"):
            force_run_retention_job(db, job["id"])

    def test_refuses_completed_job(self, db):
        job = schedule_retention_job(
            db,
            cvr="12345678",
            action="purge",
            scheduled_for="2026-01-01T00:00:00Z",
        )
        mark_retention_job_completed(db, job["id"])
        with pytest.raises(KeyError, match="not pending"):
            force_run_retention_job(db, job["id"])

    def test_refuses_failed_job(self, db):
        job = schedule_retention_job(
            db,
            cvr="12345678",
            action="purge",
            scheduled_for="2026-01-01T00:00:00Z",
        )
        mark_retention_job_failed(db, job["id"], error="boom")
        with pytest.raises(KeyError, match="not pending"):
            force_run_retention_job(db, job["id"])

    def test_refuses_cancelled_job(self, db):
        job = schedule_retention_job(
            db,
            cvr="12345678",
            action="purge",
            scheduled_for="2099-01-01T00:00:00Z",
        )
        cancel_retention_job(db, job["id"])
        with pytest.raises(KeyError, match="not pending"):
            force_run_retention_job(db, job["id"])

    def test_missing_job_raises(self, db):
        with pytest.raises(KeyError, match="not found"):
            force_run_retention_job(db, 99999)


class TestRetryFailedRetentionJob:
    def test_demotes_failed_to_pending(self, db):
        job = schedule_retention_job(
            db,
            cvr="12345678",
            action="purge",
            scheduled_for="2026-01-01T00:00:00Z",
        )
        mark_retention_job_failed(db, job["id"], error="rds 5xx")
        updated = retry_failed_retention_job(db, job["id"], operator="alice")
        assert updated["status"] == "pending"

    def test_clears_executed_at(self, db):
        job = schedule_retention_job(
            db,
            cvr="12345678",
            action="purge",
            scheduled_for="2026-01-01T00:00:00Z",
        )
        mark_retention_job_failed(db, job["id"], error="rds 5xx")
        updated = retry_failed_retention_job(db, job["id"])
        assert updated["executed_at"] is None
        assert updated["claimed_at"] is None

    def test_preserves_failure_note(self, db):
        job = schedule_retention_job(
            db,
            cvr="12345678",
            action="purge",
            scheduled_for="2026-01-01T00:00:00Z",
        )
        mark_retention_job_failed(db, job["id"], error="rds 5xx")
        updated = retry_failed_retention_job(db, job["id"], operator="alice")
        assert "rds 5xx" in updated["notes"]
        assert "retry by alice" in updated["notes"]

    def test_refuses_pending_job(self, db):
        job = schedule_retention_job(
            db,
            cvr="12345678",
            action="purge",
            scheduled_for="2099-01-01T00:00:00Z",
        )
        with pytest.raises(KeyError, match="not failed"):
            retry_failed_retention_job(db, job["id"])

    def test_refuses_completed_job(self, db):
        job = schedule_retention_job(
            db,
            cvr="12345678",
            action="purge",
            scheduled_for="2026-01-01T00:00:00Z",
        )
        mark_retention_job_completed(db, job["id"])
        with pytest.raises(KeyError, match="not failed"):
            retry_failed_retention_job(db, job["id"])

    def test_missing_job_raises(self, db):
        with pytest.raises(KeyError, match="not found"):
            retry_failed_retention_job(db, 99999)


class TestNoteAppendIsAtomic:
    """Two interleaved operator clicks must both leave their audit
    line in `notes`. Codex flagged the original read-modify-write
    pattern as TOCTOU-vulnerable on 2026-04-26."""

    def test_two_force_runs_both_audit_lines_present(self, db):
        job = schedule_retention_job(
            db,
            cvr="12345678",
            action="purge",
            scheduled_for="2099-01-01T00:00:00Z",
        )
        # Two operators race. The implementation appends in SQL via
        # CASE ... notes || char(10) || suffix, so both audit lines
        # land regardless of read ordering.
        force_run_retention_job(db, job["id"], operator="alice")
        force_run_retention_job(db, job["id"], operator="bob")
        final = list_retention_jobs_for_cvr(db, "12345678")[0]
        assert "force-run by alice" in final["notes"]
        assert "force-run by bob" in final["notes"]
        # Newline separator preserved.
        assert "\n" in final["notes"]


# ---------------------------------------------------------------------------
# Client-level retention mode
# ---------------------------------------------------------------------------


class TestSetDataRetentionMode:
    def test_updates_mode(self, db, watchman_client):
        updated = set_data_retention_mode(
            db, watchman_client["cvr"], "anonymised"
        )
        assert updated["data_retention_mode"] == "anonymised"

    def test_updates_purge_at(self, db, watchman_client):
        updated = set_data_retention_mode(
            db,
            watchman_client["cvr"],
            "purge_scheduled",
            churn_purge_at="2027-04-24T00:00:00Z",
        )
        assert updated["churn_purge_at"] == "2027-04-24T00:00:00Z"

    def test_rejects_unknown_mode(self, db, watchman_client):
        with pytest.raises(ValueError, match="Invalid data_retention_mode"):
            set_data_retention_mode(db, watchman_client["cvr"], "burned")

    def test_missing_client_raises(self, db):
        with pytest.raises(KeyError):
            set_data_retention_mode(db, "99999999", "anonymised")


# ---------------------------------------------------------------------------
# D16 tiered churn scheduling
# ---------------------------------------------------------------------------


class TestScheduleChurnRetentionWatchman:
    """Watchman is a free trial — no anonymise stage, immediate hard-purge
    at the anchor. Revised 2026-04-24 from the initial 90d/365d read."""

    def test_schedules_single_immediate_purge(self, db, watchman_client):
        anchor = "2026-04-24T00:00:00Z"
        jobs = schedule_churn_retention(
            db, cvr=watchman_client["cvr"], plan="watchman", anchor_at=anchor
        )

        assert len(jobs) == 1
        assert jobs[0]["action"] == "purge"
        assert jobs[0]["scheduled_for"] == anchor

    def test_no_anonymise_step(self, db, watchman_client):
        jobs = schedule_churn_retention(
            db, cvr=watchman_client["cvr"], plan="watchman"
        )
        assert "anonymise" not in {j["action"] for j in jobs}

    def test_notes_document_the_zero_retention_policy(self, db, watchman_client):
        jobs = schedule_churn_retention(
            db, cvr=watchman_client["cvr"], plan="watchman"
        )
        assert "free trial retains no data" in jobs[0]["notes"]

    def test_updates_client_purge_at_to_final_job(self, db, watchman_client):
        anchor = "2026-04-24T00:00:00Z"
        jobs = schedule_churn_retention(
            db, cvr=watchman_client["cvr"], plan="watchman", anchor_at=anchor
        )
        client = get_client(db, watchman_client["cvr"])
        assert client["data_retention_mode"] == "purge_scheduled"
        assert client["churn_purge_at"] == jobs[-1]["scheduled_for"]
        assert client["churn_requested_at"] == anchor

    def test_stores_churn_reason(self, db, watchman_client):
        schedule_churn_retention(
            db,
            cvr=watchman_client["cvr"],
            plan="watchman",
            churn_reason="trial expired without conversion",
        )
        client = get_client(db, watchman_client["cvr"])
        assert client["churn_reason"] == "trial expired without conversion"


class TestScheduleChurnRetentionSentinel:
    def test_schedules_anonymise_and_bookkeeping_purge(self, db, sentinel_client):
        anchor = "2026-04-24T00:00:00Z"
        jobs = schedule_churn_retention(
            db, cvr=sentinel_client["cvr"], plan="sentinel", anchor_at=anchor
        )

        assert len(jobs) == 2
        assert [j["action"] for j in jobs] == ["anonymise", "purge_bookkeeping"]

    def test_anonymise_at_plus_30d(self, db, sentinel_client):
        anchor = "2026-04-24T00:00:00Z"
        jobs = schedule_churn_retention(
            db, cvr=sentinel_client["cvr"], plan="sentinel", anchor_at=anchor
        )
        delta = _days_between(anchor, jobs[0]["scheduled_for"])
        assert abs(delta - SENTINEL_ANONYMISE_DAYS) < 1e-6

    def test_bookkeeping_purge_at_plus_5y(self, db, sentinel_client):
        anchor = "2026-04-24T00:00:00Z"
        jobs = schedule_churn_retention(
            db, cvr=sentinel_client["cvr"], plan="sentinel", anchor_at=anchor
        )
        delta = _days_between(anchor, jobs[1]["scheduled_for"])
        assert abs(delta - SENTINEL_BOOKKEEPING_PURGE_DAYS) < 1e-6

    def test_notes_mention_bogforingsloven(self, db, sentinel_client):
        jobs = schedule_churn_retention(
            db, cvr=sentinel_client["cvr"], plan="sentinel"
        )
        bookkeeping = [j for j in jobs if j["action"] == "purge_bookkeeping"][0]
        assert "Bogføringsloven" in bookkeeping["notes"]


class TestScheduleChurnRetentionCommon:
    def test_rejects_unknown_plan(self, db, watchman_client):
        with pytest.raises(ValueError, match="Invalid plan"):
            schedule_churn_retention(
                db, cvr=watchman_client["cvr"], plan="enterprise"
            )

    def test_missing_client_raises(self, db):
        with pytest.raises(KeyError):
            schedule_churn_retention(db, cvr="99999999", plan="watchman")

    def test_defaults_anchor_to_now(self, db, watchman_client):
        # With no explicit anchor, the single Watchman purge job's
        # scheduled_for equals "now" (immediate — the cron claims it on
        # the next tick).
        jobs = schedule_churn_retention(
            db, cvr=watchman_client["cvr"], plan="watchman"
        )
        now = datetime.now(UTC).replace(microsecond=0)
        scheduled = datetime.strptime(
            jobs[0]["scheduled_for"], "%Y-%m-%dT%H:%M:%SZ"
        ).replace(tzinfo=UTC)
        delta = abs(scheduled - now)
        assert delta < timedelta(seconds=2)


class TestClaimDueRetentionJobs:
    def test_returns_empty_when_nothing_due(self, db):
        schedule_retention_job(
            db, "11111111", "purge", "2099-01-01T00:00:00Z"
        )
        assert claim_due_retention_jobs(db) == []

    def test_claims_due_pending_rows_oldest_first(self, db):
        b = schedule_retention_job(
            db, "22222222", "purge", "2026-02-01T00:00:00Z"
        )
        a = schedule_retention_job(
            db, "11111111", "purge", "2026-01-01T00:00:00Z"
        )

        claimed = claim_due_retention_jobs(db, now="2026-04-24T00:00:00Z")

        assert [c["id"] for c in claimed] == [a["id"], b["id"]]
        # Status flipped + claimed_at stamped.
        for c in claimed:
            assert c["status"] == "running"
            assert c["claimed_at"] == "2026-04-24T00:00:00Z"

    def test_does_not_re_claim_already_running(self, db):
        schedule_retention_job(
            db, "11111111", "purge", "2026-01-01T00:00:00Z"
        )
        first = claim_due_retention_jobs(db, now="2026-04-24T00:00:00Z")
        second = claim_due_retention_jobs(db, now="2026-04-24T00:00:00Z")

        assert len(first) == 1
        assert second == []

    def test_skips_completed_failed_cancelled(self, db):
        good = schedule_retention_job(
            db, "11111111", "purge", "2026-01-01T00:00:00Z"
        )
        done = schedule_retention_job(
            db, "22222222", "purge", "2026-01-01T00:00:00Z"
        )
        bad = schedule_retention_job(
            db, "33333333", "purge", "2026-01-01T00:00:00Z"
        )
        gone = schedule_retention_job(
            db, "44444444", "purge", "2026-01-01T00:00:00Z"
        )
        mark_retention_job_completed(db, done["id"])
        mark_retention_job_failed(db, bad["id"], error="x")
        cancel_retention_job(db, gone["id"])

        claimed = claim_due_retention_jobs(db, now="2026-04-24T00:00:00Z")

        assert [c["id"] for c in claimed] == [good["id"]]

    def test_respects_limit(self, db):
        for i in range(5):
            schedule_retention_job(
                db, f"{i:08d}", "purge", "2026-01-01T00:00:00Z"
            )

        claimed = claim_due_retention_jobs(
            db, now="2026-04-24T00:00:00Z", limit=2
        )
        assert len(claimed) == 2

    def test_persists_status_running_after_commit(self, db):
        job = schedule_retention_job(
            db, "11111111", "purge", "2026-01-01T00:00:00Z"
        )
        claim_due_retention_jobs(db, now="2026-04-24T00:00:00Z")

        # Re-fetch via a separate query path to confirm the commit.
        rows = list_retention_jobs_for_cvr(db, "11111111")
        assert rows[0]["id"] == job["id"]
        assert rows[0]["status"] == "running"
        assert rows[0]["claimed_at"] == "2026-04-24T00:00:00Z"


class TestReapStuckRunningJobs:
    def _claim_at(self, db, scheduled: str, claimed_at: str) -> dict:
        """Helper: schedule a job and force its status=running + claimed_at."""
        job = schedule_retention_job(db, "12345678", "purge", scheduled)
        db.execute(
            "UPDATE retention_jobs SET status = 'running', claimed_at = ? WHERE id = ?",
            (claimed_at, job["id"]),
        )
        db.commit()
        return job

    def test_demotes_old_running_back_to_pending(self, db):
        self._claim_at(
            db,
            scheduled="2026-04-24T00:00:00Z",
            claimed_at="2026-04-24T00:00:00Z",  # 2h before "now"
        )

        n = reap_stuck_running_jobs(
            db, timeout_seconds=3600, now="2026-04-24T02:00:00Z"
        )

        assert n == 1
        rows = list_retention_jobs_for_cvr(db, "12345678")
        assert rows[0]["status"] == "pending"
        assert rows[0]["claimed_at"] is None

    def test_leaves_recently_claimed_alone(self, db):
        self._claim_at(
            db,
            scheduled="2026-04-24T00:00:00Z",
            claimed_at="2026-04-24T01:30:00Z",  # 30m before "now"
        )

        n = reap_stuck_running_jobs(
            db, timeout_seconds=3600, now="2026-04-24T02:00:00Z"
        )

        assert n == 0
        rows = list_retention_jobs_for_cvr(db, "12345678")
        assert rows[0]["status"] == "running"

    def test_ignores_completed_and_pending_rows(self, db):
        # Completed, far in the past — should not be reaped.
        completed = schedule_retention_job(
            db, "11111111", "purge", "2026-01-01T00:00:00Z"
        )
        mark_retention_job_completed(db, completed["id"])
        # Plain pending — should not be reaped.
        schedule_retention_job(
            db, "22222222", "purge", "2026-01-01T00:00:00Z"
        )

        n = reap_stuck_running_jobs(db, now="2026-04-24T00:00:00Z")
        assert n == 0

    def test_returns_zero_when_nothing_to_reap(self, db):
        assert reap_stuck_running_jobs(db) == 0

    def test_reap_stuck_running_jobs_normalises_offset_now(self, db):
        """Offset-aware ``now`` must be converted before the cutoff is stamped.

        Job claimed at 07:30 UTC. ``now`` = 10:00+02:00 = 08:00 UTC, only
        30m after the claim — under the 1h timeout, so the job should NOT
        be reaped. Without .astimezone(UTC), the bug would treat the +02
        wall clock as Z, producing cutoff = 09:00Z (2h ahead), and the
        07:30Z claim would fall under the cutoff and get demoted.
        """
        self._claim_at(
            db,
            scheduled="2026-04-24T07:30:00Z",
            claimed_at="2026-04-24T07:30:00Z",
        )

        n = reap_stuck_running_jobs(
            db,
            timeout_seconds=3600,
            now="2026-04-24T10:00:00+02:00",
        )

        assert n == 0
        rows = list_retention_jobs_for_cvr(db, "12345678")
        assert rows[0]["status"] == "running"
        assert rows[0]["claimed_at"] == "2026-04-24T07:30:00Z"


class TestEnumCoverage:
    def test_retention_actions_expected(self):
        assert VALID_RETENTION_ACTIONS == {
            "anonymise",
            "purge",
            "purge_bookkeeping",
            "export",
        }

    def test_retention_statuses_expected(self):
        assert VALID_RETENTION_JOB_STATUSES == {
            "pending",
            "running",
            "completed",
            "failed",
            "cancelled",
        }

    def test_data_retention_modes_expected(self):
        assert VALID_DATA_RETENTION_MODES == {
            "standard",
            "anonymised",
            "purge_scheduled",
            "purged",
        }
