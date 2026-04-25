"""Tests for src.client_memory.trial_expiry — Watchman trial-expiry scanner."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from io import StringIO

import pytest
from loguru import logger

from src.client_memory.trial_expiry import (
    expire_watchman_trial,
    find_expired_trials,
    reconcile_watchman_expired_orphans,
    run_trial_expiry_sweep,
)
from src.db.clients import create_client, get_client
from src.db.connection import init_db
from src.db.retention import (
    cancel_retention_job,
    list_retention_jobs_for_cvr,
    mark_retention_job_completed,
    mark_retention_job_failed,
)


@pytest.fixture()
def db(tmp_path):
    conn = init_db(tmp_path / "test.db")
    yield conn
    conn.close()


def _iso_offset(days: int) -> str:
    return (datetime.now(UTC) + timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _make_watchman(db, cvr: str, *, expires_offset_days: int) -> dict:
    """Seed a watchman_active client with trial_expires_at shifted by days."""
    return create_client(
        db,
        cvr=cvr,
        company_name=f"Co {cvr}",
        status="watchman_active",
        plan="watchman",
        trial_started_at=_iso_offset(expires_offset_days - 30),
        trial_expires_at=_iso_offset(expires_offset_days),
    )


# ---------------------------------------------------------------------------
# find_expired_trials
# ---------------------------------------------------------------------------


class TestFindExpiredTrials:
    def test_empty_when_none_expired(self, db):
        _make_watchman(db, "11111111", expires_offset_days=+5)
        assert find_expired_trials(db) == []

    def test_returns_expired_ordered_oldest_first(self, db):
        newer = _make_watchman(db, "22222222", expires_offset_days=-1)
        older = _make_watchman(db, "33333333", expires_offset_days=-7)

        rows = find_expired_trials(db)

        assert [r["cvr"] for r in rows] == [older["cvr"], newer["cvr"]]

    def test_ignores_non_watchman_active(self, db):
        # Prospect with an expired trial_expires_at should not be picked up.
        create_client(
            db,
            cvr="44444444",
            company_name="Not yet active",
            status="prospect",
            trial_expires_at=_iso_offset(-10),
        )
        # Active sentinel client with old trial date also ignored.
        create_client(
            db,
            cvr="55555555",
            company_name="Converted",
            status="active",
            plan="sentinel",
            trial_expires_at=_iso_offset(-100),
        )
        assert find_expired_trials(db) == []

    def test_ignores_null_trial_expires_at(self, db):
        create_client(
            db,
            cvr="66666666",
            company_name="Pending activation",
            status="watchman_active",
            plan="watchman",
        )
        assert find_expired_trials(db) == []

    def test_accepts_explicit_now(self, db):
        _make_watchman(db, "77777777", expires_offset_days=+10)
        # Jump "now" 20 days into the future — that trial is now expired.
        future_now = _iso_offset(+20)
        rows = find_expired_trials(db, now=future_now)
        assert [r["cvr"] for r in rows] == ["77777777"]


# ---------------------------------------------------------------------------
# expire_watchman_trial
# ---------------------------------------------------------------------------


class TestExpireWatchmanTrial:
    def test_flips_status_to_watchman_expired(self, db):
        client = _make_watchman(db, "12345678", expires_offset_days=-1)
        updated, transitioned = expire_watchman_trial(db, client["cvr"])
        assert updated["status"] == "watchman_expired"
        assert transitioned is True

    def test_schedules_single_immediate_purge(self, db):
        client = _make_watchman(db, "12345678", expires_offset_days=-1)
        _, transitioned = expire_watchman_trial(db, client["cvr"])
        assert transitioned is True

        jobs = list_retention_jobs_for_cvr(db, client["cvr"])
        assert len(jobs) == 1
        assert jobs[0]["action"] == "purge"
        assert jobs[0]["status"] == "pending"
        # Anchor is the trial_expires_at, not "now".
        assert jobs[0]["scheduled_for"] == client["trial_expires_at"]

    def test_stores_churn_reason(self, db):
        client = _make_watchman(db, "12345678", expires_offset_days=-1)
        _, transitioned = expire_watchman_trial(db, client["cvr"])
        assert transitioned is True
        row = get_client(db, client["cvr"])
        assert row["churn_reason"] == "watchman trial expired without conversion"

    def test_marks_data_retention_mode_purge_scheduled(self, db):
        client = _make_watchman(db, "12345678", expires_offset_days=-1)
        _, transitioned = expire_watchman_trial(db, client["cvr"])
        assert transitioned is True
        row = get_client(db, client["cvr"])
        assert row["data_retention_mode"] == "purge_scheduled"

    def test_unknown_cvr_raises_key_error(self, db):
        with pytest.raises(KeyError):
            expire_watchman_trial(db, "99999999")

    def test_refuses_non_watchman_active(self, db):
        create_client(
            db,
            cvr="12345678",
            company_name="Active Sentinel",
            status="active",
            plan="sentinel",
        )
        with pytest.raises(ValueError, match="only transitions from 'watchman_active'"):
            expire_watchman_trial(db, "12345678")

    def test_falls_back_to_now_when_trial_expires_at_is_null(self, db):
        # Edge case: an orphan watchman_active row without trial_expires_at.
        # Scanner never picks this up via find_expired_trials (tested above),
        # but a direct call must still be safe — anchor falls back to 'now'.
        create_client(
            db,
            cvr="12345678",
            company_name="Orphan",
            status="watchman_active",
            plan="watchman",
        )
        when = "2026-06-01T00:00:00Z"
        _, transitioned = expire_watchman_trial(db, "12345678", now=when)
        assert transitioned is True

        jobs = list_retention_jobs_for_cvr(db, "12345678")
        assert jobs[0]["scheduled_for"] == when


# ---------------------------------------------------------------------------
# run_trial_expiry_sweep
# ---------------------------------------------------------------------------


class TestRunTrialExpirySweep:
    def test_expires_all_overdue_trials(self, db):
        _make_watchman(db, "11111111", expires_offset_days=-1)
        _make_watchman(db, "22222222", expires_offset_days=-3)
        _make_watchman(db, "33333333", expires_offset_days=+5)  # Still active

        count = run_trial_expiry_sweep(db)

        assert count == 2
        assert get_client(db, "11111111")["status"] == "watchman_expired"
        assert get_client(db, "22222222")["status"] == "watchman_expired"
        assert get_client(db, "33333333")["status"] == "watchman_active"

    def test_returns_zero_when_nothing_to_do(self, db):
        _make_watchman(db, "11111111", expires_offset_days=+10)
        assert run_trial_expiry_sweep(db) == 0

    def test_single_failure_does_not_abort_sweep(self, db, monkeypatch):
        _make_watchman(db, "11111111", expires_offset_days=-1)
        _make_watchman(db, "22222222", expires_offset_days=-2)

        # Force the first expire call to fail, second to succeed.
        original_expire = expire_watchman_trial
        call_count = {"n": 0}

        def flaky_expire(conn, cvr, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("synthetic failure")
            return original_expire(conn, cvr, **kwargs)

        monkeypatch.setattr(
            "src.client_memory.trial_expiry.expire_watchman_trial",
            flaky_expire,
        )

        count = run_trial_expiry_sweep(db)

        # One succeeded, one failed — sweep reports 1, does not raise.
        assert count == 1

    def test_sweep_count_excludes_raced_rows(self, db, monkeypatch):
        # Two seeded rows: one will transition normally, the other will
        # come back from expire_watchman_trial with transitioned=False —
        # simulating the CAS race where a concurrent writer flipped the
        # row out of 'watchman_active' between the SELECT and UPDATE.
        # The sweep must count only the real transition.
        _make_watchman(db, "11111111", expires_offset_days=-1)
        _make_watchman(db, "22222222", expires_offset_days=-2)

        original_expire = expire_watchman_trial
        call_count = {"n": 0}

        def raced_then_real(conn, cvr, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                # Simulate the CAS race outcome: the function returns
                # (row, False) — status unchanged, no retention scheduled.
                row = dict(get_client(conn, cvr))
                row["status"] = "watchman_active"
                return row, False
            return original_expire(conn, cvr, **kwargs)

        monkeypatch.setattr(
            "src.client_memory.trial_expiry.expire_watchman_trial",
            raced_then_real,
        )

        count = run_trial_expiry_sweep(db)

        # Only the second row genuinely transitioned.
        assert count == 1

    def test_sweep_does_not_count_concurrent_worker_winning_the_race(
        self, db, monkeypatch
    ):
        # Codex P3 scenario: a concurrent worker has already flipped the
        # row to 'watchman_expired' before our CAS UPDATE ran, so our
        # rowcount==0 and the post-UPDATE re-read returns a row whose
        # status is 'watchman_expired'. The fixed expire_watchman_trial
        # must signal this with transitioned=False, and the sweep must
        # NOT count it as a local success — otherwise two workers racing
        # the same row would each report +1 and the operator metric
        # would double-count every contended expiry.
        _make_watchman(db, "11111111", expires_offset_days=-1)

        def concurrent_worker_won(conn, cvr, **kwargs):
            # Mirror what the real function would now return on a lost
            # CAS where another worker already won: the post-re-read
            # reflects 'watchman_expired', but transitioned is False.
            row = dict(get_client(conn, cvr))
            row["status"] = "watchman_expired"
            return row, False

        monkeypatch.setattr(
            "src.client_memory.trial_expiry.expire_watchman_trial",
            concurrent_worker_won,
        )

        count = run_trial_expiry_sweep(db)

        # The concurrent worker did the work; we must not also count it.
        assert count == 0


# ---------------------------------------------------------------------------
# reconcile_watchman_expired_orphans
# ---------------------------------------------------------------------------


class TestReconcileWatchmanExpiredOrphans:
    def _seed_expired_without_job(self, db, cvr: str) -> dict:
        """Create a watchman_expired client with no retention job.

        Mimics the crash-between-commits scenario inside
        ``expire_watchman_trial``.
        """
        return create_client(
            db,
            cvr=cvr,
            company_name=f"Co {cvr}",
            status="watchman_expired",
            plan="watchman",
            trial_started_at=_iso_offset(-35),
            trial_expires_at=_iso_offset(-5),
        )

    def test_reconciles_orphan_by_scheduling_purge(self, db):
        client = self._seed_expired_without_job(db, "11111111")

        count = reconcile_watchman_expired_orphans(db)

        assert count == 1
        jobs = list_retention_jobs_for_cvr(db, client["cvr"])
        assert len(jobs) == 1
        assert jobs[0]["action"] == "purge"
        assert jobs[0]["scheduled_for"] == client["trial_expires_at"]
        # The "reconciled — " prefix is stamped on clients.churn_reason,
        # not on retention_jobs.notes (that's the fixed schedule string).
        assert "reconciled" in get_client(db, client["cvr"])["churn_reason"]

    def test_ignores_expired_with_pending_purge(self, db):
        # Healthy case: expire_watchman_trial ran to completion, so the
        # client has a pending purge job. The reconciler must skip.
        client = self._seed_expired_without_job(db, "11111111")
        expire_watchman_trial.__globals__["schedule_churn_retention"](
            db, client["cvr"], plan="watchman",
            anchor_at=client["trial_expires_at"],
            churn_reason="seeded healthy case",
        )
        assert len(list_retention_jobs_for_cvr(db, client["cvr"])) == 1

        count = reconcile_watchman_expired_orphans(db)

        assert count == 0
        assert len(list_retention_jobs_for_cvr(db, client["cvr"])) == 1

    def test_ignores_expired_with_running_job(self, db):
        from src.db.retention import schedule_retention_job
        client = self._seed_expired_without_job(db, "11111111")
        # Simulate a job already claimed by the runner.
        schedule_retention_job(
            db, client["cvr"], "purge", client["trial_expires_at"],
            notes="seeded",
        )
        db.execute(
            "UPDATE retention_jobs SET status = 'running' WHERE cvr = ?",
            (client["cvr"],),
        )
        db.commit()

        assert reconcile_watchman_expired_orphans(db) == 0

    def test_ignores_expired_with_completed_purge(self, db):
        # A completed purge should also block reconciliation — the work
        # is done even if a stale clients row somehow lingered.
        from src.db.retention import schedule_retention_job
        client = self._seed_expired_without_job(db, "11111111")
        job = schedule_retention_job(
            db, client["cvr"], "purge", client["trial_expires_at"],
            notes="seeded",
        )
        mark_retention_job_completed(db, job["id"])

        assert reconcile_watchman_expired_orphans(db) == 0

    def test_reschedules_when_prior_job_failed_or_cancelled(self, db):
        # A failed or cancelled job leaves the client un-purged — the
        # reconciler SHOULD reschedule in that case.
        from src.db.retention import schedule_retention_job
        client = self._seed_expired_without_job(db, "11111111")
        job = schedule_retention_job(
            db, client["cvr"], "purge", client["trial_expires_at"],
            notes="seeded",
        )
        mark_retention_job_failed(db, job["id"], error="synthetic")

        count = reconcile_watchman_expired_orphans(db)

        assert count == 1
        jobs = list_retention_jobs_for_cvr(db, client["cvr"])
        # Original failed row + new reconciled pending row.
        assert len(jobs) == 2
        pending = [j for j in jobs if j["status"] == "pending"]
        assert len(pending) == 1

    def test_cancelled_job_also_triggers_reschedule(self, db):
        from src.db.retention import schedule_retention_job
        client = self._seed_expired_without_job(db, "11111111")
        job = schedule_retention_job(
            db, client["cvr"], "purge", client["trial_expires_at"],
        )
        cancel_retention_job(db, job["id"])

        assert reconcile_watchman_expired_orphans(db) == 1

    def test_ignores_watchman_active_clients(self, db):
        _make_watchman(db, "11111111", expires_offset_days=+5)  # still active
        assert reconcile_watchman_expired_orphans(db) == 0

    def test_ignores_sentinel_clients(self, db):
        # A sentinel in churned / expired-ish state is not the reconciler's
        # job — sentinel retention goes through a different operator path.
        create_client(
            db,
            cvr="22222222",
            company_name="Sentinel Co",
            status="churned",
            plan="sentinel",
        )
        assert reconcile_watchman_expired_orphans(db) == 0

    def test_returns_zero_when_nothing_to_do(self, db):
        assert reconcile_watchman_expired_orphans(db) == 0


# ---------------------------------------------------------------------------
# Race condition + DRYRUN skip + logger event-name regression coverage
# ---------------------------------------------------------------------------


class TestExpireWatchmanTrialRace:
    """Concurrent writers between SELECT and UPDATE must not be clobbered."""

    def test_stale_read_does_not_overwrite_concurrent_status_change(
        self, db, monkeypatch
    ):
        # Real DB state: client is 'active' (already converted to Sentinel).
        create_client(
            db,
            cvr="12345678",
            company_name="Converted to Sentinel",
            status="active",
            plan="sentinel",
            trial_started_at=_iso_offset(-30),
            trial_expires_at=_iso_offset(-1),
        )

        # Simulate the race by having the FIRST get_client call return
        # a stale 'watchman_active' snapshot (as if the read had landed
        # before a concurrent Sentinel-conversion writer flipped the
        # row). Subsequent calls — including the function's own final
        # "return current state" lookup — read the real row.
        real_row = get_client(db, "12345678")
        stale_row = dict(real_row)
        stale_row["status"] = "watchman_active"
        calls = {"n": 0}

        def stale_then_real(conn, cvr):
            calls["n"] += 1
            return stale_row if calls["n"] == 1 else real_row

        monkeypatch.setattr(
            "src.client_memory.trial_expiry.get_client",
            stale_then_real,
        )

        # If the race fix is missing, schedule_churn_retention would fire.
        # Patch it to raise so any call surfaces as a test failure.
        def boom(*args, **kwargs):
            raise AssertionError(
                "schedule_churn_retention must not run on a raced row"
            )

        monkeypatch.setattr(
            "src.client_memory.trial_expiry.schedule_churn_retention",
            boom,
        )

        # Should NOT raise — the function detects the race and bails.
        result, transitioned = expire_watchman_trial(db, "12345678")

        # The returned row reflects current DB state (still 'active').
        assert result["status"] == "active"
        # Race-loss path must explicitly signal "this worker did nothing".
        assert transitioned is False

        # And no retention job was scheduled.
        assert list_retention_jobs_for_cvr(db, "12345678") == []


class TestRunTrialExpirySweepDryRunSkip:
    """B7 default-lean: synthetic DRYRUN-* CVRs are skipped by the sweep."""

    def test_dryrun_cvr_is_left_untouched_and_not_counted(self, db):
        # Synthetic CVR — must be skipped.
        _make_watchman(db, "DRYRUN-12345678", expires_offset_days=-1)
        # Real CVR — must be expired normally.
        _make_watchman(db, "11111111", expires_offset_days=-1)

        count = run_trial_expiry_sweep(db)

        # Only the real client counted.
        assert count == 1

        dryrun_row = get_client(db, "DRYRUN-12345678")
        assert dryrun_row["status"] == "watchman_active"
        assert list_retention_jobs_for_cvr(db, "DRYRUN-12345678") == []

        real_row = get_client(db, "11111111")
        assert real_row["status"] == "watchman_expired"
        assert len(list_retention_jobs_for_cvr(db, "11111111")) == 1


class TestLoggerEventNameContract:
    """Federico's monitoring greps for the literal event name. Lock it in."""

    def test_watchman_trial_expired_event_name_is_emitted(self, db):
        buf = StringIO()
        # Plain text sink so we can substring-match the event name. Loguru
        # default handler is removed during the test so all output flows
        # through ``buf``; we restore it in the finally block.
        logger.remove()
        sink_id = logger.add(buf, level="INFO", format="{message}")
        try:
            client = _make_watchman(db, "12345678", expires_offset_days=-1)
            expire_watchman_trial(db, client["cvr"])
        finally:
            logger.remove(sink_id)
            # Re-add a default-ish sink so subsequent tests are unaffected.
            import sys
            logger.add(sys.stderr, level="INFO")

        assert "watchman_trial_expired" in buf.getvalue()
