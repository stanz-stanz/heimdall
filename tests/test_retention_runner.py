"""Tests for src.retention.runner — tick mechanics.

Covers:
- atomic claim (two concurrent connections never both win a row),
- stuck-row reaper,
- backoff schedule (15m / 1h / 4h / 24h / terminal),
- terminal-failure alert callback,
- DRYRUN CVR skip,
- export action raising NotImplementedError,
- offboarding_triggered + authorisation_revoked emission for anonymise,
- job state transitions into 'completed' on success.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from src.db.clients import create_client
from src.db.connection import connect_clients_audited, init_db
from src.db.retention import (
    claim_due_retention_jobs,
    get_retention_job,
    reap_stuck_running_jobs,
    schedule_retention_job,
)
from src.retention import runner as runner_mod
from src.retention.runner import (
    MAX_ATTEMPTS,
    RETENTION_ALERT_CHANNEL,
    _backoff_iso,
    _default_redis_alert,
    _parse_attempt,
    tick,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def db(tmp_path):
    conn = init_db(tmp_path / "test.db")
    yield conn
    conn.close()


@pytest.fixture()
def db_path(tmp_path):
    """Separate path for the concurrent-connection test."""
    conn = init_db(tmp_path / "claim.db")
    conn.close()
    return str(tmp_path / "claim.db")


@pytest.fixture()
def sentinel_client(db):
    return create_client(
        db,
        cvr="12345678",
        company_name="Test Co",
        plan="sentinel",
        status="active",
    )


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


class TestParseAttempt:
    def test_empty_notes_returns_zero(self):
        assert _parse_attempt(None) == 0
        assert _parse_attempt("") == 0

    def test_no_prefix_returns_zero(self):
        assert _parse_attempt("ok: anonymised 47 rows") == 0

    def test_parses_attempt_number(self):
        assert _parse_attempt("attempt 3: locked database") == 3

    def test_case_insensitive(self):
        assert _parse_attempt("Attempt 2: flake") == 2


class TestBackoffIso:
    def test_adds_minutes(self):
        result = _backoff_iso("2026-04-24T00:00:00Z", 60)
        assert result == "2026-04-24T01:00:00Z"

    def test_handles_offset_timestamps(self):
        result = _backoff_iso("2026-04-24T00:00:00+00:00", 15)
        assert result == "2026-04-24T00:15:00Z"

    def test_backoff_iso_normalises_offset_aware_input(self):
        """Offset-aware non-UTC input must be converted before the Z suffix.

        Without the .astimezone(UTC) normalisation, +02:00 wall-clock time
        would be stamped verbatim with `Z`, shifting retry scheduling by the
        offset. 10:00 CEST + 15m = 10:15 CEST = 08:15 UTC.
        """
        result = _backoff_iso("2026-04-24T10:00:00+02:00", 15)
        assert result == "2026-04-24T08:15:00Z"


# ---------------------------------------------------------------------------
# Claim atomicity (two-connection race)
# ---------------------------------------------------------------------------


class TestClaimAtomicity:
    def test_two_concurrent_claims_never_win_same_row(self, tmp_path, sentinel_client):
        """Two connections racing on the same single row: exactly one wins."""
        path = str(tmp_path / "race.db")
        # init from a clean connection so the schema is laid down, then
        # schedule a single overdue job.
        conn = init_db(path)
        create_client(
            conn,
            cvr="99999999",
            company_name="Race Co",
            plan="sentinel",
            status="active",
        )
        schedule_retention_job(
            conn,
            cvr="99999999",
            action="anonymise",
            scheduled_for="2026-01-01T00:00:00Z",
        )
        conn.close()

        # Two independent connections fight over it. Stage A.5: the
        # claim-UPDATE on retention_jobs fires trg_retention_jobs_audit_update
        # which calls the per-connection ``audit_context()`` UDF —
        # ``connect_clients_audited`` registers it. (Plain sqlite3.connect
        # would raise ``no such function: audit_context``.)
        conn_a = connect_clients_audited(path, timeout=5)
        conn_a.execute("PRAGMA journal_mode=WAL")

        conn_b = connect_clients_audited(path, timeout=5)
        conn_b.execute("PRAGMA journal_mode=WAL")

        try:
            claimed_a = claim_due_retention_jobs(
                conn_a, now="2026-04-24T00:00:00Z"
            )
            claimed_b = claim_due_retention_jobs(
                conn_b, now="2026-04-24T00:00:00Z"
            )
        finally:
            conn_a.close()
            conn_b.close()

        # Exactly one winner.
        ids_a = {j["id"] for j in claimed_a}
        ids_b = {j["id"] for j in claimed_b}
        assert ids_a & ids_b == set(), "both connections won the same row"
        assert len(ids_a) + len(ids_b) == 1

    def test_claim_flips_status_to_running_and_stamps_claimed_at(
        self, db, sentinel_client
    ):
        job = schedule_retention_job(
            db,
            cvr=sentinel_client["cvr"],
            action="anonymise",
            scheduled_for="2026-01-01T00:00:00Z",
        )
        claimed = claim_due_retention_jobs(db, now="2026-04-24T00:00:00Z")
        assert len(claimed) == 1
        assert claimed[0]["status"] == "running"
        assert claimed[0]["claimed_at"] == "2026-04-24T00:00:00Z"
        row = get_retention_job(db, job["id"])
        assert row["status"] == "running"

    def test_claim_respects_limit(self, db, sentinel_client):
        for _ in range(5):
            schedule_retention_job(
                db,
                cvr=sentinel_client["cvr"],
                action="anonymise",
                scheduled_for="2026-01-01T00:00:00Z",
            )
        claimed = claim_due_retention_jobs(
            db, now="2026-04-24T00:00:00Z", limit=2
        )
        assert len(claimed) == 2

    def test_claim_skips_future_scheduled(self, db, sentinel_client):
        schedule_retention_job(
            db,
            cvr=sentinel_client["cvr"],
            action="anonymise",
            scheduled_for="2099-01-01T00:00:00Z",
        )
        claimed = claim_due_retention_jobs(db, now="2026-04-24T00:00:00Z")
        assert claimed == []

    def test_claim_skips_non_pending(self, db, sentinel_client):
        job = schedule_retention_job(
            db,
            cvr=sentinel_client["cvr"],
            action="anonymise",
            scheduled_for="2026-01-01T00:00:00Z",
        )
        # Flip to completed manually.
        db.execute(
            "UPDATE retention_jobs SET status = 'completed' WHERE id = ?",
            (job["id"],),
        )
        db.commit()
        assert claim_due_retention_jobs(db, now="2026-04-24T00:00:00Z") == []


# ---------------------------------------------------------------------------
# Reaper
# ---------------------------------------------------------------------------


class TestReaper:
    def test_demotes_stuck_running(self, db, sentinel_client):
        # Insert a stuck running row with an old claimed_at.
        db.execute(
            """
            INSERT INTO retention_jobs
                (cvr, action, scheduled_for, status, claimed_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                sentinel_client["cvr"],
                "anonymise",
                "2026-04-01T00:00:00Z",
                "running",
                "2026-04-01T00:00:00Z",
                "2026-04-01T00:00:00Z",
            ),
        )
        db.commit()

        # Reap with a timeout of 1h, reference now = 2026-04-24 — the
        # stuck row's claimed_at is weeks old so it qualifies.
        count = reap_stuck_running_jobs(
            db,
            timeout_seconds=3600,
            now="2026-04-24T00:00:00Z",
        )
        assert count == 1

        row = db.execute(
            "SELECT status, claimed_at FROM retention_jobs WHERE cvr = ?",
            (sentinel_client["cvr"],),
        ).fetchone()
        assert row["status"] == "pending"
        assert row["claimed_at"] is None

    def test_does_not_touch_recent_running(self, db, sentinel_client):
        # Recent claim, still within timeout window.
        now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        db.execute(
            """
            INSERT INTO retention_jobs
                (cvr, action, scheduled_for, status, claimed_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                sentinel_client["cvr"],
                "anonymise",
                "2026-04-24T00:00:00Z",
                "running",
                now,
                now,
            ),
        )
        db.commit()

        count = reap_stuck_running_jobs(db, timeout_seconds=3600)
        assert count == 0

    def test_does_not_touch_non_running(self, db, sentinel_client):
        # Completed row should never be reaped.
        db.execute(
            """
            INSERT INTO retention_jobs
                (cvr, action, scheduled_for, status, claimed_at, executed_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sentinel_client["cvr"],
                "anonymise",
                "2020-01-01T00:00:00Z",
                "completed",
                "2020-01-01T00:00:00Z",
                "2020-01-01T00:00:00Z",
                "2020-01-01T00:00:00Z",
            ),
        )
        db.commit()

        count = reap_stuck_running_jobs(
            db, timeout_seconds=1, now="2026-04-24T00:00:00Z"
        )
        assert count == 0


# ---------------------------------------------------------------------------
# Tick mechanics
# ---------------------------------------------------------------------------


class TestTickHappyPath:
    def test_no_due_jobs_returns_zero(self, db):
        assert tick(db) == 0

    def test_success_marks_completed(self, db, sentinel_client):
        job = schedule_retention_job(
            db,
            cvr=sentinel_client["cvr"],
            action="anonymise",
            scheduled_for="2026-01-01T00:00:00Z",
        )
        n = tick(db)
        assert n == 1
        row = get_retention_job(db, job["id"])
        assert row["status"] == "completed"
        assert row["executed_at"] is not None
        assert row["notes"].startswith("ok:")

    def test_anonymise_emits_offboarding_and_revoked_events(
        self, db, sentinel_client
    ):
        schedule_retention_job(
            db,
            cvr=sentinel_client["cvr"],
            action="anonymise",
            scheduled_for="2026-01-01T00:00:00Z",
        )
        tick(db)

        events = db.execute(
            """
            SELECT event_type FROM conversion_events
             WHERE cvr = ? ORDER BY id ASC
            """,
            (sentinel_client["cvr"],),
        ).fetchall()
        types = [e["event_type"] for e in events]
        assert "offboarding_triggered" in types
        assert "authorisation_revoked" in types


class TestTickDryRunSkip:
    def test_dryrun_cvr_is_skipped(self, db):
        schedule_retention_job(
            db,
            cvr="DRYRUN-ABC",
            action="anonymise",
            scheduled_for="2026-01-01T00:00:00Z",
        )
        n = tick(db)
        assert n == 1  # claimed and processed, but skipped inside loop
        row = db.execute(
            "SELECT status, notes FROM retention_jobs WHERE cvr = ?",
            ("DRYRUN-ABC",),
        ).fetchone()
        assert row["status"] == "completed"
        assert "DRYRUN" in row["notes"]


class TestTickBackoff:
    def test_first_failure_reschedules_15m(self, db, sentinel_client):
        schedule_retention_job(
            db,
            cvr=sentinel_client["cvr"],
            action="anonymise",
            scheduled_for="2026-01-01T00:00:00Z",
        )
        with patch(
            "src.retention.runner.anonymise_client",
            side_effect=RuntimeError("flaky"),
        ):
            tick(db)

        row = db.execute(
            "SELECT status, scheduled_for, notes FROM retention_jobs WHERE cvr = ?",
            (sentinel_client["cvr"],),
        ).fetchone()
        assert row["status"] == "pending"
        assert row["notes"].startswith("attempt 1:")
        # scheduled_for pushed ~15 min into the future.
        bumped = datetime.strptime(
            row["scheduled_for"], "%Y-%m-%dT%H:%M:%SZ"
        ).replace(tzinfo=UTC)
        delta = bumped - datetime.now(UTC)
        assert timedelta(minutes=14) <= delta <= timedelta(minutes=16)

    def test_fifth_failure_is_terminal(self, db, sentinel_client):
        # Seed a row that has already failed 4 times.
        db.execute(
            """
            INSERT INTO retention_jobs
                (cvr, action, scheduled_for, status, notes, created_at)
            VALUES (?, ?, ?, 'pending', 'attempt 4: flake', ?)
            """,
            (
                sentinel_client["cvr"],
                "anonymise",
                "2026-01-01T00:00:00Z",
                "2026-04-24T00:00:00Z",
            ),
        )
        db.commit()

        with patch(
            "src.retention.runner.anonymise_client",
            side_effect=RuntimeError("still flaky"),
        ):
            tick(db)

        row = db.execute(
            "SELECT status, notes FROM retention_jobs WHERE cvr = ?",
            (sentinel_client["cvr"],),
        ).fetchone()
        assert row["status"] == "failed"
        assert row["notes"].startswith(f"attempt {MAX_ATTEMPTS}:")


class TestTickTerminalAlert:
    def test_terminal_failure_fires_alert_cb(self, db, sentinel_client):
        db.execute(
            """
            INSERT INTO retention_jobs
                (cvr, action, scheduled_for, status, notes, created_at)
            VALUES (?, ?, ?, 'pending', 'attempt 4: earlier fail', ?)
            """,
            (
                sentinel_client["cvr"],
                "anonymise",
                "2026-01-01T00:00:00Z",
                "2026-04-24T00:00:00Z",
            ),
        )
        db.commit()

        captured: list[dict] = []

        with patch(
            "src.retention.runner.anonymise_client",
            side_effect=RuntimeError("boom"),
        ):
            tick(db, alert_cb=lambda p: captured.append(p))

        assert len(captured) == 1
        payload = captured[0]
        assert payload["cvr"] == sentinel_client["cvr"]
        assert payload["action"] == "anonymise"
        assert payload["last_error"] == "boom"
        assert "job_id" in payload

    def test_non_terminal_failure_does_not_fire_alert(
        self, db, sentinel_client
    ):
        schedule_retention_job(
            db,
            cvr=sentinel_client["cvr"],
            action="anonymise",
            scheduled_for="2026-01-01T00:00:00Z",
        )
        captured: list[dict] = []
        with patch(
            "src.retention.runner.anonymise_client",
            side_effect=RuntimeError("flaky"),
        ):
            tick(db, alert_cb=lambda p: captured.append(p))
        assert captured == []


class TestTickExport:
    def test_export_raises_not_implemented_and_terminal_fails_immediately(
        self, db, sentinel_client
    ):
        schedule_retention_job(
            db,
            cvr=sentinel_client["cvr"],
            action="export",
            scheduled_for="2026-01-01T00:00:00Z",
        )
        captured: list[dict] = []
        tick(db, alert_cb=lambda p: captured.append(p))

        row = db.execute(
            "SELECT status, notes FROM retention_jobs WHERE cvr = ?",
            (sentinel_client["cvr"],),
        ).fetchone()
        assert row["status"] == "failed"
        assert "export deferred" in row["notes"]
        # First attempt is terminal for export → alert fires once.
        assert len(captured) == 1


# ---------------------------------------------------------------------------
# Default Redis alert callback
# ---------------------------------------------------------------------------


class TestDefaultRedisAlert:
    def test_publishes_to_retention_alert_channel(self):
        published: list[tuple[str, str]] = []

        class FakeRedis:
            def publish(self, channel: str, payload: str) -> None:
                published.append((channel, payload))

        cb = _default_redis_alert(FakeRedis())
        cb({"cvr": "1", "action": "purge", "job_id": 7, "last_error": "x"})

        assert len(published) == 1
        channel, payload = published[0]
        assert channel == RETENTION_ALERT_CHANNEL
        # payload is JSON — verify it round-trips.
        import json

        data = json.loads(payload)
        assert data["cvr"] == "1"
        assert data["action"] == "purge"

    def test_publish_exception_is_swallowed(self):
        class BadRedis:
            def publish(self, channel: str, payload: str) -> None:
                raise ConnectionError("redis down")

        cb = _default_redis_alert(BadRedis())
        # Must not raise — the DB has the state, Redis is best-effort.
        cb({"cvr": "1", "action": "purge", "job_id": 7, "last_error": "x"})


# ---------------------------------------------------------------------------
# Additional scenarios required by the spec
# ---------------------------------------------------------------------------


class TestParseAttemptMalformed:
    """Spec: malformed string returns 0."""

    def test_garbage_prefix_returns_zero(self):
        assert _parse_attempt("attempt: missing number") == 0

    def test_text_only_returns_zero(self):
        assert _parse_attempt("scheduled by operator") == 0


class TestBackoffSchedule:
    """Spec: attempts 2/3/4 hit +1h / +4h / +24h respectively."""

    @pytest.mark.parametrize(
        ("prior_attempt_label", "expected_minutes"),
        [
            ("attempt 1: prior", 60),     # next is attempt 2 → +1h
            ("attempt 2: prior", 240),    # next is attempt 3 → +4h
            ("attempt 3: prior", 1440),   # next is attempt 4 → +24h
        ],
    )
    def test_subsequent_failures_use_correct_backoff(
        self, db, sentinel_client, prior_attempt_label, expected_minutes
    ):
        db.execute(
            """
            INSERT INTO retention_jobs
                (cvr, action, scheduled_for, status, notes, created_at)
            VALUES (?, ?, ?, 'pending', ?, ?)
            """,
            (
                sentinel_client["cvr"],
                "anonymise",
                "2026-01-01T00:00:00Z",
                prior_attempt_label,
                "2026-04-24T00:00:00Z",
            ),
        )
        db.commit()

        with patch(
            "src.retention.runner.anonymise_client",
            side_effect=RuntimeError("still flaky"),
        ):
            tick(db)

        row = db.execute(
            "SELECT status, scheduled_for, notes FROM retention_jobs WHERE cvr = ?",
            (sentinel_client["cvr"],),
        ).fetchone()
        assert row["status"] == "pending"
        bumped = datetime.strptime(
            row["scheduled_for"], "%Y-%m-%dT%H:%M:%SZ"
        ).replace(tzinfo=UTC)
        delta = bumped - datetime.now(UTC)
        # Allow a small slack for execution time.
        assert (
            timedelta(minutes=expected_minutes - 1)
            <= delta
            <= timedelta(minutes=expected_minutes + 1)
        )


class TestTickResetsClaimedAtOnReschedule:
    def test_failed_attempt_clears_claimed_at(self, db, sentinel_client):
        schedule_retention_job(
            db,
            cvr=sentinel_client["cvr"],
            action="anonymise",
            scheduled_for="2026-01-01T00:00:00Z",
        )
        with patch(
            "src.retention.runner.anonymise_client",
            side_effect=RuntimeError("flaky"),
        ):
            tick(db)

        row = db.execute(
            "SELECT claimed_at FROM retention_jobs WHERE cvr = ?",
            (sentinel_client["cvr"],),
        ).fetchone()
        assert row["claimed_at"] is None


class TestTickTerminalStampsExecutedAt:
    def test_terminal_failure_stamps_executed_at(self, db, sentinel_client):
        db.execute(
            """
            INSERT INTO retention_jobs
                (cvr, action, scheduled_for, status, notes, created_at)
            VALUES (?, ?, ?, 'pending', 'attempt 4: prior', ?)
            """,
            (
                sentinel_client["cvr"],
                "anonymise",
                "2026-01-01T00:00:00Z",
                "2026-04-24T00:00:00Z",
            ),
        )
        db.commit()
        with patch(
            "src.retention.runner.anonymise_client",
            side_effect=RuntimeError("boom"),
        ):
            tick(db, alert_cb=lambda p: None)

        row = db.execute(
            "SELECT status, executed_at FROM retention_jobs WHERE cvr = ?",
            (sentinel_client["cvr"],),
        ).fetchone()
        assert row["status"] == "failed"
        assert row["executed_at"] is not None


class TestTickReapBeforeClaim:
    """Spec: tick reaps stranded ``running`` rows BEFORE claiming new
    ones. We seed both a stranded row and a fresh due row; one tick
    should rescue + claim + dispatch the rescued row in the same call.
    """

    def test_reap_then_claim_dispatches_rescued_row(self, db, sentinel_client):
        # Stranded running row from a crashed prior tick. claimed_at is
        # ancient relative to the default 1h reap window.
        db.execute(
            """
            INSERT INTO retention_jobs
                (cvr, action, scheduled_for, status, claimed_at, created_at)
            VALUES (?, 'anonymise', '2026-01-01T00:00:00Z', 'running',
                    '2020-01-01T00:00:00Z', '2020-01-01T00:00:00Z')
            """,
            (sentinel_client["cvr"],),
        )
        db.commit()

        n = tick(db)

        # Reaped, then claimed + dispatched in the same tick.
        assert n == 1
        row = db.execute(
            "SELECT status FROM retention_jobs WHERE cvr = ?",
            (sentinel_client["cvr"],),
        ).fetchone()
        assert row["status"] == "completed"


class TestTickUnknownAction:
    """Spec: an unknown action falls through ``_dispatch_action``'s
    raise ValueError → caught by the runner's generic Exception handler
    → backoff branch (attempt 1, +15min). NOT the NotImplementedError
    branch (which is reserved for export's deliberate stub).
    """

    def test_unknown_action_routed_to_backoff_not_terminal(
        self, db, sentinel_client
    ):
        # We can't use schedule_retention_job (it validates), so go raw.
        db.execute(
            """
            INSERT INTO retention_jobs
                (cvr, action, scheduled_for, status, created_at)
            VALUES (?, 'unrecognised_action', '2026-01-01T00:00:00Z',
                    'pending', '2026-04-24T00:00:00Z')
            """,
            (sentinel_client["cvr"],),
        )
        db.commit()

        captured: list[dict] = []
        tick(db, alert_cb=lambda p: captured.append(p))

        row = db.execute(
            "SELECT status, notes FROM retention_jobs WHERE cvr = ?",
            (sentinel_client["cvr"],),
        ).fetchone()
        # Backoff branch — not terminal on first failure.
        assert row["status"] == "pending"
        assert row["notes"].startswith("attempt 1:")
        assert "unrecognised_action" in row["notes"]
        # Alert NOT fired (non-terminal).
        assert captured == []


class TestDispatchAction:
    """Spec: verify _dispatch_action's audit-event behaviour per action,
    using the actions module monkeypatched to a no-op so we isolate the
    dispatcher's behaviour from action implementation details.
    """

    def test_purge_writes_only_offboarding_triggered_then_cascades(
        self, db, sentinel_client, monkeypatch
    ):
        """The runner emits ``offboarding_triggered`` BEFORE invoking
        purge_client. purge_client itself wipes ``conversion_events`` for
        the CVR — so after dispatch the count is 0. We verify by
        monkeypatching purge_client to a NO-OP that does NOT delete
        conversion_events; the offboarding_triggered row should be the
        only conversion_event present.
        """
        captured_calls: list[dict] = []

        def _fake_purge(conn, job_row):
            captured_calls.append({"action": "purge", "cvr": job_row["cvr"]})
            return {"clients": 1}

        monkeypatch.setattr(runner_mod, "purge_client", _fake_purge)

        schedule_retention_job(
            db,
            cvr=sentinel_client["cvr"],
            action="purge",
            scheduled_for="2026-01-01T00:00:00Z",
        )
        tick(db)

        # purge_client was invoked.
        assert captured_calls == [
            {"action": "purge", "cvr": sentinel_client["cvr"]}
        ]
        # offboarding_triggered was emitted; authorisation_revoked was NOT.
        events = db.execute(
            "SELECT event_type FROM conversion_events WHERE cvr = ?",
            (sentinel_client["cvr"],),
        ).fetchall()
        types = [e["event_type"] for e in events]
        assert "offboarding_triggered" in types
        assert "authorisation_revoked" not in types

    def test_purge_real_action_leaves_zero_conversion_events(
        self, db, sentinel_client
    ):
        """Without monkeypatching, the real purge_client cascade deletes
        the conversion_events row that the dispatcher just inserted.
        End state: 0 rows for the CVR.
        """
        schedule_retention_job(
            db,
            cvr=sentinel_client["cvr"],
            action="purge",
            scheduled_for="2026-01-01T00:00:00Z",
        )
        tick(db)

        count = db.execute(
            "SELECT COUNT(*) FROM conversion_events WHERE cvr = ?",
            (sentinel_client["cvr"],),
        ).fetchone()[0]
        assert count == 0

    def test_purge_bookkeeping_writes_no_conversion_events(
        self, db, sentinel_client, monkeypatch
    ):
        called: list[dict] = []

        def _fake_pb(conn, job_row):
            called.append({"cvr": job_row["cvr"]})
            return {"payment_events": 0, "subscriptions": 0}

        monkeypatch.setattr(runner_mod, "purge_bookkeeping", _fake_pb)

        schedule_retention_job(
            db,
            cvr=sentinel_client["cvr"],
            action="purge_bookkeeping",
            scheduled_for="2026-01-01T00:00:00Z",
        )
        tick(db)

        assert called == [{"cvr": sentinel_client["cvr"]}]
        events = db.execute(
            "SELECT event_type FROM conversion_events WHERE cvr = ?",
            (sentinel_client["cvr"],),
        ).fetchall()
        # No offboarding_triggered, no authorisation_revoked — the +5y
        # bookkeeping purge runs after all PII is already gone.
        assert events == []

    def test_anonymise_dispatches_to_handler_with_conn_and_job(
        self, db, sentinel_client, monkeypatch
    ):
        """Decouple the dispatcher from the (currently buggy) anonymise
        implementation by monkeypatching the handler and asserting it
        receives ``(conn, job_row)`` and the surrounding audit events.
        """
        spy_calls: list[tuple[object, dict]] = []

        def _fake_anonymise(conn, job_row):
            spy_calls.append((conn, dict(job_row)))
            return {"clients": 1, "consent_records": 0}

        monkeypatch.setattr(runner_mod, "anonymise_client", _fake_anonymise)

        schedule_retention_job(
            db,
            cvr=sentinel_client["cvr"],
            action="anonymise",
            scheduled_for="2026-01-01T00:00:00Z",
        )
        tick(db)

        assert len(spy_calls) == 1
        passed_conn, passed_job = spy_calls[0]
        assert passed_conn is db
        assert passed_job["cvr"] == sentinel_client["cvr"]
        assert passed_job["action"] == "anonymise"

        # Both audit rows present.
        types = [
            e["event_type"]
            for e in db.execute(
                "SELECT event_type FROM conversion_events WHERE cvr = ? "
                "ORDER BY id ASC",
                (sentinel_client["cvr"],),
            ).fetchall()
        ]
        assert types[0] == "offboarding_triggered"
        assert "authorisation_revoked" in types

    def test_purge_bookkeeping_real_action_leaves_no_conversion_events(
        self, db, sentinel_client
    ):
        """End-to-end check: real purge_bookkeeping path emits nothing."""
        schedule_retention_job(
            db,
            cvr=sentinel_client["cvr"],
            action="purge_bookkeeping",
            scheduled_for="2026-01-01T00:00:00Z",
        )
        tick(db)

        events = db.execute(
            "SELECT event_type FROM conversion_events WHERE cvr = ?",
            (sentinel_client["cvr"],),
        ).fetchall()
        assert events == []


# ---------------------------------------------------------------------------
# Atomic audit writes (Codex P1 / Valdí ruling 2026-04-25)
# ---------------------------------------------------------------------------


class TestAtomicAuditWrites:
    """Forensic-trail integrity: audit rows commit ONLY when the action
    they describe also commits.

    Before the fix, ``_dispatch_action`` called the public
    :func:`record_conversion_event` which committed internally. That
    meant if the subsequent action raised, the runner's rollback could
    not unwind the audit row — leaving an ``offboarding_triggered``
    record for a job that never executed. The fix replaces those calls
    with :func:`_emit_event_in_txn`, which inserts WITHOUT committing,
    so rollback / commit semantics are uniform across the dispatch.
    """

    def test_offboarding_triggered_rolled_back_when_action_fails(
        self, db, sentinel_client
    ):
        """anonymise raises → tick rolls back → no offboarding_triggered
        row survives in conversion_events for the CVR.
        """
        schedule_retention_job(
            db,
            cvr=sentinel_client["cvr"],
            action="anonymise",
            scheduled_for="2026-01-01T00:00:00Z",
        )

        with patch(
            "src.retention.runner.anonymise_client",
            side_effect=RuntimeError("anonymise blew up"),
        ):
            tick(db)

        # Job rescheduled (attempt 1, +15min) — proves the failure path
        # ran — but no conversion_events row survived the rollback.
        job_row = db.execute(
            "SELECT status, notes FROM retention_jobs WHERE cvr = ?",
            (sentinel_client["cvr"],),
        ).fetchone()
        assert job_row["status"] == "pending"
        assert job_row["notes"].startswith("attempt 1:")

        events = db.execute(
            "SELECT event_type FROM conversion_events WHERE cvr = ?",
            (sentinel_client["cvr"],),
        ).fetchall()
        types = [e["event_type"] for e in events]
        # Critically: no offboarding_triggered, no authorisation_revoked.
        assert "offboarding_triggered" not in types
        assert "authorisation_revoked" not in types

    def test_offboarding_and_authorisation_revoked_committed_with_action_on_success(
        self, db, sentinel_client
    ):
        """anonymise succeeds → both audit rows present after the tick."""
        schedule_retention_job(
            db,
            cvr=sentinel_client["cvr"],
            action="anonymise",
            scheduled_for="2026-01-01T00:00:00Z",
        )

        n = tick(db)
        assert n == 1

        # Job marked completed → action committed.
        job_row = db.execute(
            "SELECT status FROM retention_jobs WHERE cvr = ?",
            (sentinel_client["cvr"],),
        ).fetchone()
        assert job_row["status"] == "completed"

        events = db.execute(
            """
            SELECT event_type FROM conversion_events
             WHERE cvr = ? AND event_type IN
                 ('offboarding_triggered', 'authorisation_revoked')
             ORDER BY id ASC
            """,
            (sentinel_client["cvr"],),
        ).fetchall()
        types = [e["event_type"] for e in events]
        assert types == ["offboarding_triggered", "authorisation_revoked"]

    def test_purge_offboarding_rolled_back_when_action_fails(
        self, db, sentinel_client
    ):
        """The atomicity invariant also holds for the purge branch:
        if purge_client raises, the offboarding_triggered audit row
        does NOT survive.
        """
        schedule_retention_job(
            db,
            cvr=sentinel_client["cvr"],
            action="purge",
            scheduled_for="2026-01-01T00:00:00Z",
        )

        with patch(
            "src.retention.runner.purge_client",
            side_effect=RuntimeError("purge blew up"),
        ):
            tick(db)

        events = db.execute(
            "SELECT event_type FROM conversion_events WHERE cvr = ?",
            (sentinel_client["cvr"],),
        ).fetchall()
        types = [e["event_type"] for e in events]
        assert "offboarding_triggered" not in types

    def test_record_conversion_event_still_commits_for_external_callers(
        self, db, sentinel_client
    ):
        """``record_conversion_event`` is unchanged — other modules
        (signup, onboarding handler) rely on its committing semantic.
        Quick smoke-test to guard against accidental refactor of the
        helper itself.
        """
        # Direct call from outside the retention runner.
        from src.db.conversion import record_conversion_event

        record_conversion_event(
            db,
            cvr=sentinel_client["cvr"],
            event_type="signup",
            source="test_smoke",
            payload={"hello": "world"},
        )

        # Open a SECOND connection — the row must already be visible
        # there, proving the helper committed on its own.
        path = db.execute(
            "SELECT file FROM pragma_database_list WHERE name = 'main'"
        ).fetchone()["file"]
        observer = sqlite3.connect(path, timeout=5)
        observer.row_factory = sqlite3.Row
        try:
            row = observer.execute(
                "SELECT event_type FROM conversion_events WHERE cvr = ? "
                "AND event_type = 'signup'",
                (sentinel_client["cvr"],),
            ).fetchone()
        finally:
            observer.close()
        assert row is not None
        assert row["event_type"] == "signup"


# ---------------------------------------------------------------------------
# Codex P2: claim-then-cascade / external-update guard
# ---------------------------------------------------------------------------


class TestTickReclaimGuard:
    """The runner re-fetches each claimed row immediately before
    dispatch. If the row is gone (cascaded by an earlier purge in the
    same batch) or no longer in 'running' (an external writer changed
    it), the loop skips silently — no double processing, no failure
    log, no alert.
    """

    def test_tick_skips_purge_cascaded_sibling(self, db, sentinel_client):
        """Two ``purge`` rows for the same CVR claimed in one tick. The
        first purge's ``purge_client`` cascade deletes the second row out
        from under the loop. The runner's re-fetch guard must notice and
        skip silently — no alert, no failure, no double processing.
        """
        # Schedule TWO purge jobs for the same CVR, both due, both pending.
        job_a = schedule_retention_job(
            db,
            cvr=sentinel_client["cvr"],
            action="purge",
            scheduled_for="2026-01-01T00:00:00Z",
        )
        job_b = schedule_retention_job(
            db,
            cvr=sentinel_client["cvr"],
            action="purge",
            scheduled_for="2026-01-01T00:00:01Z",
        )

        captured: list[dict] = []
        n = tick(db, alert_cb=lambda p: captured.append(p))

        # Only one purge counted as processed — the second was cascaded
        # away by the first and the guard skipped it without incrementing.
        assert n == 1
        # No alert — the skip is silent.
        assert captured == []

        # The first purge ran to completion: clients row gone, every
        # CVR-attached table empty.
        client_row = db.execute(
            "SELECT 1 FROM clients WHERE cvr = ?",
            (sentinel_client["cvr"],),
        ).fetchone()
        assert client_row is None

        # The second purge row was deleted by the cascade — neither
        # 'completed' nor 'failed', it simply does not exist any more.
        # The first purge row preserves itself via the cascade's
        # ``id != current_job_id`` guard, so it survived to be marked
        # completed.
        first = get_retention_job(db, job_a["id"])
        assert first is not None
        assert first["status"] == "completed"
        second = get_retention_job(db, job_b["id"])
        assert second is None

        # Sanity: no leftover conversion_events (purge cascades them too).
        count = db.execute(
            "SELECT COUNT(*) FROM conversion_events WHERE cvr = ?",
            (sentinel_client["cvr"],),
        ).fetchone()[0]
        assert count == 0

    def test_tick_skips_externally_completed_job(
        self, db, sentinel_client, monkeypatch
    ):
        """Between claim and dispatch, an external writer flips the row
        to 'completed'. The guard must see the change, skip the row
        without altering it, and emit no alert."""
        job = schedule_retention_job(
            db,
            cvr=sentinel_client["cvr"],
            action="anonymise",
            scheduled_for="2026-01-01T00:00:00Z",
        )

        # Capture the row state we want to preserve so we can verify the
        # runner did not overwrite it.
        sentinel_executed_at = "2026-04-24T12:00:00Z"
        sentinel_notes = "completed externally — operator override"

        # Wrap get_retention_job so the FIRST call (the guard re-fetch)
        # simulates a concurrent UPDATE flipping the row to 'completed'
        # before observation.
        original = runner_mod.get_retention_job
        flipped = {"done": False}

        def _flipping_get(conn, job_id):
            if not flipped["done"]:
                conn.execute(
                    """
                    UPDATE retention_jobs
                       SET status = 'completed',
                           executed_at = ?,
                           notes = ?
                     WHERE id = ?
                    """,
                    (sentinel_executed_at, sentinel_notes, job_id),
                )
                conn.commit()
                flipped["done"] = True
            return original(conn, job_id)

        monkeypatch.setattr(runner_mod, "get_retention_job", _flipping_get)

        captured: list[dict] = []
        # Spy on _dispatch_action to confirm it is NEVER called for the
        # externally-completed row.
        dispatch_calls: list[dict] = []
        original_dispatch = runner_mod._dispatch_action

        def _spy_dispatch(conn, job_row):
            dispatch_calls.append(dict(job_row))
            return original_dispatch(conn, job_row)

        monkeypatch.setattr(runner_mod, "_dispatch_action", _spy_dispatch)

        n = tick(db, alert_cb=lambda p: captured.append(p))

        # Skipped: not counted, no dispatch, no alert.
        assert n == 0
        assert dispatch_calls == []
        assert captured == []

        # Row preserved exactly as the external writer left it.
        row = get_retention_job(db, job["id"])
        assert row["status"] == "completed"
        assert row["executed_at"] == sentinel_executed_at
        assert row["notes"] == sentinel_notes
