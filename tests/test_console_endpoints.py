"""Tests for the new console API endpoints (dashboard, pipeline, campaigns, etc.)."""


import sqlite3
from datetime import UTC, datetime, timedelta

import fakeredis
import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.db.connection import init_db
from tests._console_auth_helpers import (
    login_console_client,
    seed_console_operator,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

NOW = "2026-04-06T10:00:00Z"


@pytest.fixture
def db_path(tmp_path):
    """Create a test SQLite database with schema + seed data."""
    db_file = tmp_path / "clients.db"
    conn = init_db(str(db_file))

    # Seed clients
    conn.execute(
        "INSERT INTO clients (cvr, company_name, status, plan, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("12345678", "Jelling Kro", "active", "sentinel", NOW, NOW),
    )
    conn.execute(
        "INSERT INTO client_domains (cvr, domain, is_primary, added_at) VALUES (?, ?, ?, ?)",
        ("12345678", "jellingkro.dk", 1, NOW),
    )
    conn.execute(
        "INSERT INTO clients (cvr, company_name, status, plan, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("87654321", "Conrads Bistro", "active", "watchman", NOW, NOW),
    )
    conn.execute(
        "INSERT INTO client_domains (cvr, domain, is_primary, added_at) VALUES (?, ?, ?, ?)",
        ("87654321", "conrads.dk", 1, NOW),
    )

    # Seed prospects
    conn.execute(
        "INSERT INTO prospects (domain, company_name, campaign, bucket, finding_count, "
        "critical_count, high_count, outreach_status, brief_json, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("farylochan.dk", "Farylo Chan", "0426-restaurants", "A", 137, 2, 5, "sent", "{}", NOW, NOW),
    )
    conn.execute(
        "INSERT INTO prospects (domain, company_name, campaign, bucket, finding_count, "
        "critical_count, high_count, outreach_status, brief_json, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("hopballe.dk", "Hopballe Traktsted", "0426-restaurants", "A", 120, 0, 4, "new", "{}", NOW, NOW),
    )
    conn.execute(
        "INSERT INTO prospects (domain, company_name, campaign, bucket, finding_count, "
        "critical_count, high_count, outreach_status, brief_json, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("clinic.dk", "Health Clinic", "0426-clinics", "B", 50, 1, 2, "new", "{}", NOW, NOW),
    )

    # Seed a pipeline run
    conn.execute(
        "INSERT INTO pipeline_runs (run_id, run_date, started_at, completed_at, status, "
        "domain_count, finding_count, critical_count, high_count, total_duration_ms) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("run-001", "2026-04-05", NOW, NOW, "completed", 1169, 16991, 459, 2100, 2880000),
    )

    # Seed a brief snapshot
    conn.execute(
        "INSERT INTO brief_snapshots (domain, scan_date, brief_json, bucket, cms, "
        "finding_count, critical_count, high_count, cvr, company_name, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("jellingkro.dk", "2026-04-05", "{}", "A", "WordPress", 42, 3, 8, "12345678", "Jelling Kro", NOW),
    )

    conn.commit()
    conn.close()
    return str(db_file)


@pytest.fixture
def config_dir(tmp_path):
    """Create test config files."""
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "filters.json").write_text('{"bucket": ["A", "B"]}', encoding="utf-8")
    (cfg / "interpreter.json").write_text(
        '{"backend": "anthropic", "model": "claude-sonnet-4-6", "temperature": 0.3, '
        '"tone": "balanced", "language": "en", "max_output_tokens": 2048}',
        encoding="utf-8",
    )
    (cfg / "delivery.json").write_text(
        '{"require_approval": true, "retry_max": 3, "retry_delay_seconds": 5, '
        '"rate_limit_per_second": 1}',
        encoding="utf-8",
    )
    return cfg


@pytest.fixture
def client(db_path, config_dir, tmp_path, monkeypatch):
    """Create authenticated test client with fakeredis and test DB.

    Stage A slice 3f mounts ``SessionAuthMiddleware`` unconditionally,
    so the fixture seeds an operator into a temp ``console.db`` and
    walks one login round trip before yielding. The session cookie +
    default ``X-CSRF-Token`` header are primed on the returned client.
    """
    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr("redis.Redis.from_url", lambda *a, **kw: fake)
    monkeypatch.chdir(tmp_path)

    # Symlink config dir so Path("config/...") resolves
    config_link = tmp_path / "config"
    if not config_link.exists():
        config_link.symlink_to(config_dir)

    console_db_path = tmp_path / "console.db"
    monkeypatch.setenv("CONSOLE_DB_PATH", str(console_db_path))
    monkeypatch.setenv("HEIMDALL_COOKIE_SECURE", "0")

    app = create_app(
        redis_url="redis://fake:6379/0",
        results_dir=str(tmp_path / "results"),
        briefs_dir=str(tmp_path / "briefs"),
    )
    app.state.db_path = db_path

    with TestClient(app) as tc:
        seed_console_operator(console_db_path)
        login_console_client(tc)
        yield tc


# ---------------------------------------------------------------------------
# GET /console/dashboard
# ---------------------------------------------------------------------------

class TestDashboard:
    def test_dashboard_shape(self, client):
        resp = client.get("/console/dashboard")
        assert resp.status_code == 200
        body = resp.json()
        assert "prospects" in body
        assert "briefs" in body
        assert "clients" in body
        assert "critical" in body
        assert "queues" in body
        assert "activity" in body
        assert "timestamp" in body

    def test_dashboard_counts(self, client):
        body = client.get("/console/dashboard").json()
        assert body["prospects"] == 3  # 2 restaurant + 1 clinic
        assert body["clients"] == 2  # Jelling + Conrads
        assert body["briefs"] == 1  # one brief snapshot
        assert body["critical"] == 3  # from brief snapshot

    def test_dashboard_queues_empty(self, client):
        body = client.get("/console/dashboard").json()
        assert body["queues"]["scan"] == 0
        assert body["queues"]["enrichment"] == 0


# ---------------------------------------------------------------------------
# GET /console/pipeline/last
# ---------------------------------------------------------------------------

class TestPipelineLast:
    def test_pipeline_last(self, client):
        resp = client.get("/console/pipeline/last")
        assert resp.status_code == 200
        body = resp.json()
        assert body["run_id"] == "run-001"
        assert body["domain_count"] == 1169
        assert body["finding_count"] == 16991

    def test_pipeline_no_runs(self, config_dir, tmp_path, monkeypatch):
        """Returns no_runs when database has no completed runs."""
        db_file = tmp_path / "empty.db"
        conn = init_db(str(db_file))
        conn.close()

        fake = fakeredis.FakeRedis(decode_responses=True)
        monkeypatch.setattr("redis.Redis.from_url", lambda *a, **kw: fake)
        monkeypatch.chdir(tmp_path)
        config_link = tmp_path / "config"
        if not config_link.exists():
            config_link.symlink_to(config_dir)

        console_db_path = tmp_path / "console.db"
        monkeypatch.setenv("CONSOLE_DB_PATH", str(console_db_path))
        monkeypatch.setenv("HEIMDALL_COOKIE_SECURE", "0")

        app = create_app(
            redis_url="redis://fake:6379/0",
            results_dir=str(tmp_path / "results"),
            briefs_dir=str(tmp_path / "briefs"),
        )
        app.state.db_path = str(db_file)
        with TestClient(app) as tc:
            seed_console_operator(console_db_path)
            login_console_client(tc)
            body = tc.get("/console/pipeline/last").json()
            assert body["status"] == "no_runs"


# ---------------------------------------------------------------------------
# GET /console/campaigns
# ---------------------------------------------------------------------------

class TestCampaigns:
    def test_campaigns_list(self, client):
        resp = client.get("/console/campaigns")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 2
        campaigns = {c["campaign"]: c for c in body}
        assert "0426-restaurants" in campaigns
        assert campaigns["0426-restaurants"]["total"] == 2
        assert campaigns["0426-restaurants"]["sent_count"] == 1
        assert campaigns["0426-restaurants"]["new_count"] == 1

    def test_campaigns_all_counts(self, client):
        body = client.get("/console/campaigns").json()
        clinics = next(c for c in body if c["campaign"] == "0426-clinics")
        assert clinics["total"] == 1
        assert clinics["new_count"] == 1


# ---------------------------------------------------------------------------
# GET /console/campaigns/{campaign}/prospects
# ---------------------------------------------------------------------------

class TestProspects:
    def test_prospects_all(self, client):
        resp = client.get("/console/campaigns/0426-restaurants/prospects")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 2

    def test_prospects_filter_status(self, client):
        body = client.get("/console/campaigns/0426-restaurants/prospects?status=new").json()
        assert len(body) == 1
        assert body[0]["domain"] == "hopballe.dk"

    def test_prospects_filter_sent(self, client):
        body = client.get("/console/campaigns/0426-restaurants/prospects?status=sent").json()
        assert len(body) == 1
        assert body[0]["domain"] == "farylochan.dk"

    def test_prospects_limit(self, client):
        body = client.get("/console/campaigns/0426-restaurants/prospects?limit=1").json()
        assert len(body) == 1

    def test_prospects_empty_campaign(self, client):
        body = client.get("/console/campaigns/nonexistent/prospects").json()
        assert body == []

    def test_prospects_ordered_by_severity(self, client):
        body = client.get("/console/campaigns/0426-restaurants/prospects").json()
        # farylochan has 2 critical, hopballe has 0 — farylochan should be first
        assert body[0]["domain"] == "farylochan.dk"


# ---------------------------------------------------------------------------
# GET /console/clients/list
# ---------------------------------------------------------------------------

class TestClientsList:
    def test_clients_list(self, client):
        resp = client.get("/console/clients/list")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 2

    def test_clients_fields(self, client):
        body = client.get("/console/clients/list").json()
        jelling = next(c for c in body if c["company_name"] == "Jelling Kro")
        assert jelling["plan"] == "sentinel"
        assert jelling["domain"] == "jellingkro.dk"
        assert jelling["status"] == "active"
        assert jelling["last_scan"] == "2026-04-05"


# ---------------------------------------------------------------------------
# GET /console/settings + PUT /console/settings/{name}
# ---------------------------------------------------------------------------

class TestSettings:
    def test_settings_read(self, client):
        resp = client.get("/console/settings")
        assert resp.status_code == 200
        body = resp.json()
        assert "filters" in body
        assert "interpreter" in body
        assert "delivery" in body
        assert body["filters"]["bucket"] == ["A", "B"]
        assert body["interpreter"]["model"] == "claude-sonnet-4-6"
        assert body["delivery"]["require_approval"] is True

    def test_settings_write(self, client):
        resp = client.put(
            "/console/settings/filters",
            json={"bucket": ["A", "B", "C"]},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "saved"

        # Verify it persisted
        body = client.get("/console/settings").json()
        assert body["filters"]["bucket"] == ["A", "B", "C"]

    def test_settings_write_invalid_name(self, client):
        resp = client.put("/console/settings/secrets", json={"evil": True})
        assert resp.status_code == 400

    def test_settings_write_invalid_body(self, client):
        resp = client.put(
            "/console/settings/filters",
            content="not json",
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# POST /console/commands/{command}
# ---------------------------------------------------------------------------

class TestCommands:
    def test_command_queued(self, client):
        resp = client.post("/console/commands/run-pipeline", json={})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "queued"
        assert body["command"] == "run-pipeline"

    def test_command_invalid(self, client):
        resp = client.post("/console/commands/drop-database", json={})
        assert resp.status_code == 400

    def test_command_interpret(self, client):
        resp = client.post(
            "/console/commands/interpret",
            json={"campaign": "0426-restaurants", "limit": 10},
        )
        assert resp.status_code == 200

    def test_command_send(self, client):
        resp = client.post(
            "/console/commands/send",
            json={"campaign": "0426-restaurants"},
        )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# WebSocket /console/ws
# ---------------------------------------------------------------------------

class TestConsoleWebSocket:
    def test_ws_connects(self, client):
        with client.websocket_connect("/console/ws") as ws:
            ws.close()

    def test_ws_ping_pong(self, client):
        with client.websocket_connect("/console/ws") as ws:
            ws.send_json({"type": "ping"})
            # Server also pushes queue_status / log_batch frames on a timer.
            # Drain unrelated frames until we see the pong response.
            for _ in range(10):
                resp = ws.receive_json()
                if resp["type"] == "pong":
                    return
            raise AssertionError("Did not receive pong after 10 frames")


# ---------------------------------------------------------------------------
# Operator-console V1 / V6 — trial-expiring + retention queue
# ---------------------------------------------------------------------------


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture
def retention_seed(client, db_path):
    """Seed a trial-expiring Watchman client + a few retention jobs.

    Returns the seed payload (CVRs + job IDs) so individual tests can
    target them. Timestamps are relative to *real* `datetime.now(UTC)`
    so the endpoint's server-side `now()` resolves into the same window.
    """
    now = datetime.now(UTC)
    seed = {
        "expiring_cvr": "TRIAL001",
        "future_cvr": "TRIAL002",
        "due_job_id": None,
        "future_job_id": None,
        "completed_job_id": None,
        "failed_job_id": None,
    }

    conn = sqlite3.connect(db_path)
    try:
        # Watchman trial expiring in ~5 days (within default 7d window).
        conn.execute(
            "INSERT INTO clients (cvr, company_name, status, plan, "
            "trial_started_at, trial_expires_at, created_at, updated_at) "
            "VALUES (?, ?, 'watchman_active', 'watchman', ?, ?, ?, ?)",
            (
                seed["expiring_cvr"],
                "Expiring Trial",
                _iso(now - timedelta(days=25)),
                _iso(now + timedelta(days=5)),
                _iso(now),
                _iso(now),
            ),
        )
        # Watchman trial well beyond the 7d window.
        conn.execute(
            "INSERT INTO clients (cvr, company_name, status, plan, "
            "trial_started_at, trial_expires_at, created_at, updated_at) "
            "VALUES (?, ?, 'watchman_active', 'watchman', ?, ?, ?, ?)",
            (
                seed["future_cvr"],
                "Future Trial",
                _iso(now),
                _iso(now + timedelta(days=29)),
                _iso(now),
                _iso(now),
            ),
        )

        # Retention jobs — due, future, completed, failed.
        cur = conn.execute(
            "INSERT INTO retention_jobs (cvr, action, scheduled_for, status, created_at) "
            "VALUES (?, 'purge', ?, 'pending', ?)",
            (seed["expiring_cvr"], _iso(now - timedelta(hours=1)), _iso(now)),
        )
        seed["due_job_id"] = cur.lastrowid

        cur = conn.execute(
            "INSERT INTO retention_jobs (cvr, action, scheduled_for, status, created_at) "
            "VALUES (?, 'purge', ?, 'pending', ?)",
            (seed["future_cvr"], _iso(now + timedelta(days=30)), _iso(now)),
        )
        seed["future_job_id"] = cur.lastrowid

        cur = conn.execute(
            "INSERT INTO retention_jobs (cvr, action, scheduled_for, status, "
            "executed_at, created_at) "
            "VALUES (?, 'purge', ?, 'completed', ?, ?)",
            (
                seed["expiring_cvr"],
                _iso(now - timedelta(days=2)),
                _iso(now - timedelta(days=1)),
                _iso(now - timedelta(days=2)),
            ),
        )
        seed["completed_job_id"] = cur.lastrowid

        cur = conn.execute(
            "INSERT INTO retention_jobs (cvr, action, scheduled_for, status, "
            "executed_at, notes, created_at) "
            "VALUES (?, 'purge', ?, 'failed', ?, ?, ?)",
            (
                seed["future_cvr"],
                _iso(now - timedelta(hours=3)),
                _iso(now - timedelta(hours=2)),
                "rds 5xx",
                _iso(now - timedelta(hours=3)),
            ),
        )
        seed["failed_job_id"] = cur.lastrowid

        conn.commit()
    finally:
        conn.close()

    return seed


class TestTrialExpiringEndpoint:
    def test_returns_only_clients_within_default_7d_window(self, client, retention_seed):
        resp = client.get("/console/clients/trial-expiring")
        assert resp.status_code == 200
        body = resp.json()
        cvrs = {row["cvr"] for row in body}
        assert retention_seed["expiring_cvr"] in cvrs
        assert retention_seed["future_cvr"] not in cvrs

    def test_window_widens_to_30d(self, client, retention_seed):
        resp = client.get("/console/clients/trial-expiring?window_days=30")
        assert resp.status_code == 200
        cvrs = {row["cvr"] for row in resp.json()}
        assert retention_seed["expiring_cvr"] in cvrs
        assert retention_seed["future_cvr"] in cvrs

    def test_window_clamped_to_max(self, client, retention_seed):
        resp = client.get("/console/clients/trial-expiring?window_days=999")
        assert resp.status_code == 422  # FastAPI Query(le=30) rejects

    def test_window_minimum_is_one(self, client, retention_seed):
        resp = client.get("/console/clients/trial-expiring?window_days=0")
        assert resp.status_code == 422


class TestRetentionQueueEndpoint:
    def test_returns_only_pending_due(self, client, retention_seed):
        resp = client.get("/console/clients/retention-queue")
        assert resp.status_code == 200
        body = resp.json()
        ids = {row["id"] for row in body}
        assert retention_seed["due_job_id"] in ids
        assert retention_seed["future_job_id"] not in ids
        assert retention_seed["completed_job_id"] not in ids
        assert retention_seed["failed_job_id"] not in ids

    def test_pagination(self, client, retention_seed, db_path):
        # Add several due jobs to test pagination
        now = datetime.now(UTC)
        conn = sqlite3.connect(db_path)
        try:
            for i in range(5):
                conn.execute(
                    "INSERT INTO retention_jobs (cvr, action, scheduled_for, status, created_at) "
                    "VALUES (?, 'purge', ?, 'pending', ?)",
                    (
                        f"PAG{i:05d}",
                        _iso(now - timedelta(hours=2 + i)),
                        _iso(now),
                    ),
                )
            conn.commit()
        finally:
            conn.close()

        page1 = client.get("/console/clients/retention-queue?limit=2&offset=0").json()
        page2 = client.get("/console/clients/retention-queue?limit=2&offset=2").json()
        assert len(page1) == 2
        assert len(page2) == 2
        assert {r["id"] for r in page1}.isdisjoint({r["id"] for r in page2})


class TestRetentionForceRun:
    def test_advances_pending_due(self, client, retention_seed, db_path):
        # The fixture's due_job_id is already due. To meaningfully test
        # force-run, schedule a future job and force-advance it.
        future_id = retention_seed["future_job_id"]
        resp = client.post(f"/console/retention-jobs/{future_id}/force-run")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "pending"
        assert "force-run by console" in (body["notes"] or "")

    def test_404_on_missing(self, client, retention_seed):
        resp = client.post("/console/retention-jobs/99999/force-run")
        assert resp.status_code == 404

    def test_404_on_completed(self, client, retention_seed):
        resp = client.post(
            f"/console/retention-jobs/{retention_seed['completed_job_id']}/force-run"
        )
        assert resp.status_code == 404


class TestRetentionCancel:
    def test_cancels_pending(self, client, retention_seed):
        resp = client.post(
            f"/console/retention-jobs/{retention_seed['due_job_id']}/cancel",
            json={"notes": "operator override"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "cancelled"
        assert body["notes"] == "operator override"

    def test_cancels_without_body(self, client, retention_seed, db_path):
        # One-click cancel — no JSON body. Endpoint must accept this
        # and must NOT erase any pre-existing notes.
        # Seed an existing note so we can prove preservation.
        conn = sqlite3.connect(db_path)
        try:
            conn.execute(
                "UPDATE retention_jobs SET notes = ? WHERE id = ?",
                ("watchman non-converter", retention_seed["due_job_id"]),
            )
            conn.commit()
        finally:
            conn.close()

        resp = client.post(
            f"/console/retention-jobs/{retention_seed['due_job_id']}/cancel",
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "cancelled"
        assert body["notes"] == "watchman non-converter"

    def test_cancels_with_null_notes_preserves_existing(
        self, client, retention_seed, db_path
    ):
        conn = sqlite3.connect(db_path)
        try:
            conn.execute(
                "UPDATE retention_jobs SET notes = ? WHERE id = ?",
                ("scheduled by churn flow", retention_seed["due_job_id"]),
            )
            conn.commit()
        finally:
            conn.close()

        resp = client.post(
            f"/console/retention-jobs/{retention_seed['due_job_id']}/cancel",
            json={"notes": None},
        )
        assert resp.status_code == 200
        assert resp.json()["notes"] == "scheduled by churn flow"

    def test_404_on_missing(self, client, retention_seed):
        resp = client.post(
            "/console/retention-jobs/99999/cancel",
            json={"notes": None},
        )
        assert resp.status_code == 404

    def test_404_on_completed(self, client, retention_seed):
        resp = client.post(
            f"/console/retention-jobs/{retention_seed['completed_job_id']}/cancel",
            json={"notes": None},
        )
        assert resp.status_code == 404


class TestRetentionRetry:
    def test_retries_failed(self, client, retention_seed):
        resp = client.post(
            f"/console/retention-jobs/{retention_seed['failed_job_id']}/retry"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "pending"
        assert body["executed_at"] is None
        assert "retry by console" in (body["notes"] or "")

    def test_404_on_missing(self, client, retention_seed):
        resp = client.post("/console/retention-jobs/99999/retry")
        assert resp.status_code == 404

    def test_404_on_pending(self, client, retention_seed):
        # Retry only applies to failed jobs.
        resp = client.post(
            f"/console/retention-jobs/{retention_seed['due_job_id']}/retry"
        )
        assert resp.status_code == 404


class TestRetentionActionAuditPublish:
    def test_force_run_publishes_activity_with_structured_payload(
        self, client, retention_seed
    ):
        # The fixture's `client` fixture wires fakeredis at app.state.redis.
        # Subscribe BEFORE the action so the publish lands in our buffer.
        # Pull the redis instance off the app state via the test-client app.
        redis_conn = client.app.state.redis
        pubsub = redis_conn.pubsub()
        pubsub.subscribe("console:activity")
        # First message is the subscribe ack — drain it.
        pubsub.get_message(timeout=0.5)

        future_id = retention_seed["future_job_id"]
        resp = client.post(f"/console/retention-jobs/{future_id}/force-run")
        assert resp.status_code == 200

        seen_action = None
        seen_message = None
        for _ in range(5):
            msg = pubsub.get_message(timeout=0.5)
            if msg is None:
                continue
            if msg.get("type") != "message":
                continue
            import json as _json

            payload = _json.loads(msg["data"])
            # Existing console:activity convention: type == "activity".
            # The structured fields ride along in payload for consumers
            # that care.
            if payload.get("type") == "activity":
                seen_action = payload["payload"].get("action")
                seen_message = payload["payload"].get("message")
                break

        pubsub.unsubscribe()
        pubsub.close()
        assert seen_action == "force_run"
        assert seen_message is not None
        assert "force-ran" in seen_message
        assert str(future_id) in seen_message


class TestRetentionCancelRaceGuard:
    """Regression guard: cancel must use CAS so the cron can't race
    with the operator. Codex flagged the original read-then-write as
    TOCTOU-vulnerable on 2026-04-26."""

    def test_cancel_loses_to_cron_claim_returns_404(
        self, client, retention_seed, db_path
    ):
        # Simulate the cron beating the operator: flip the row to
        # 'running' before the cancel POST hits the DB. With CAS the
        # endpoint returns 404; without CAS it would silently cancel
        # an in-flight job.
        job_id = retention_seed["due_job_id"]
        conn = sqlite3.connect(db_path)
        try:
            conn.execute(
                "UPDATE retention_jobs SET status='running', claimed_at=? WHERE id=?",
                (datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), job_id),
            )
            conn.commit()
        finally:
            conn.close()

        resp = client.post(
            f"/console/retention-jobs/{job_id}/cancel",
            json={"notes": None},
        )
        assert resp.status_code == 404
        # Confirm the row stayed running.
        conn = sqlite3.connect(db_path)
        try:
            row = conn.execute(
                "SELECT status FROM retention_jobs WHERE id=?", (job_id,)
            ).fetchone()
        finally:
            conn.close()
        assert row[0] == "running"
