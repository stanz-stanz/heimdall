"""Tests for the new console API endpoints (dashboard, pipeline, campaigns, etc.)."""


import fakeredis
import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.db.connection import init_db

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
    """Create test client with fakeredis and test DB."""
    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr("redis.Redis.from_url", lambda *a, **kw: fake)
    monkeypatch.chdir(tmp_path)

    # Symlink config dir so Path("config/...") resolves
    config_link = tmp_path / "config"
    if not config_link.exists():
        config_link.symlink_to(config_dir)

    app = create_app(
        redis_url="redis://fake:6379/0",
        results_dir=str(tmp_path / "results"),
        briefs_dir=str(tmp_path / "briefs"),
    )
    app.state.db_path = db_path

    with TestClient(app) as tc:
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

        app = create_app(
            redis_url="redis://fake:6379/0",
            results_dir=str(tmp_path / "results"),
            briefs_dir=str(tmp_path / "briefs"),
        )
        app.state.db_path = str(db_file)
        with TestClient(app) as tc:
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
