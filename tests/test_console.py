"""Tests for the Heimdall Console API (monitor + demo endpoints)."""

import asyncio
import json
from unittest.mock import patch

import fakeredis
import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.api.demo_orchestrator import SCAN_SEQUENCE, get_demo_queue, run_demo_replay

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_BRIEF = {
    "domain": "example.dk",
    "company_name": "Test Restaurant ApS",
    "bucket": "A",
    "tech_stack": ["WordPress:6.9.4", "PHP", "Cloudflare"],
    "findings": [
        {"severity": "medium", "description": "Missing HSTS header", "risk": "MITM risk"},
        {"severity": "low", "description": "Missing CSP header", "risk": "XSS risk"},
    ],
}


@pytest.fixture
def briefs_dir(tmp_path):
    """Create a briefs directory with one sample brief."""
    d = tmp_path / "briefs"
    d.mkdir()
    (d / "example.dk.json").write_text(json.dumps(SAMPLE_BRIEF), encoding="utf-8")
    return d


@pytest.fixture
def results_dir(tmp_path):
    """Create a results directory with one sample result."""
    domain_dir = tmp_path / "results" / "prospect" / "example.dk"
    domain_dir.mkdir(parents=True)
    result = {
        "domain": "example.dk",
        "job_id": "test-001",
        "status": "completed",
        "brief": {
            "domain": "example.dk",
            "scan_date": "2026-03-28",
            "bucket": "A",
            "findings": [
                {"severity": "medium", "description": "Missing HSTS"},
            ],
        },
        "timing": {"total_ms": 500},
        "cache_stats": {"hits": 3, "misses": 2},
    }
    (domain_dir / "2026-03-28.json").write_text(json.dumps(result), encoding="utf-8")
    return tmp_path / "results"


def _make_app(results_dir: str, briefs_dir: str, monkeypatch):
    """Create app with fakeredis patched in."""
    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr("redis.Redis.from_url", lambda *a, **kw: fake)
    app = create_app(
        redis_url="redis://fake:6379/0",
        results_dir=results_dir,
        briefs_dir=briefs_dir,
    )
    return app


@pytest.fixture
def client(results_dir, briefs_dir, monkeypatch):
    app = _make_app(str(results_dir), str(briefs_dir), monkeypatch)
    with TestClient(app) as tc:
        yield tc


# ---------------------------------------------------------------------------
# Monitor: GET /console/status
# ---------------------------------------------------------------------------

class TestConsoleStatus:
    def test_status_shape(self, client):
        resp = client.get("/console/status")
        assert resp.status_code == 200
        body = resp.json()
        assert "queues" in body
        assert "enrichment" in body
        assert "recent_scans" in body
        assert "cache_keys" in body
        assert "timestamp" in body

    def test_status_empty_queues(self, client):
        body = client.get("/console/status").json()
        assert body["queues"]["scan"] == 0
        assert body["queues"]["enrichment"] == 0
        assert "wpscan" not in body["queues"]

    def test_status_with_queued_jobs(self, results_dir, briefs_dir, monkeypatch):
        fake = fakeredis.FakeRedis(decode_responses=True)
        fake.lpush("queue:scan", json.dumps({"job_id": "j1", "domain": "a.dk"}))
        fake.lpush("queue:scan", json.dumps({"job_id": "j2", "domain": "b.dk"}))
        fake.set("enrichment:completed", "2")
        fake.set("enrichment:total", "3")
        monkeypatch.setattr("redis.Redis.from_url", lambda *a, **kw: fake)
        app = create_app(
            redis_url="redis://fake:6379/0",
            results_dir=str(results_dir),
            briefs_dir=str(briefs_dir),
        )
        with TestClient(app) as tc:
            body = tc.get("/console/status").json()
            assert body["queues"]["scan"] == 2
            assert body["enrichment"]["completed"] == 2
            assert body["enrichment"]["total"] == 3

    def test_status_recent_scans(self, client):
        body = client.get("/console/status").json()
        assert len(body["recent_scans"]) >= 1
        assert body["recent_scans"][0]["domain"] == "example.dk"

    def test_status_redis_down(self, results_dir, briefs_dir, monkeypatch):
        """If Redis is unavailable, status still returns with zero values."""
        monkeypatch.setattr("redis.Redis.from_url", lambda *a, **kw: (_ for _ in ()).throw(Exception("down")))
        app = create_app(
            redis_url="redis://fake:6379/0",
            results_dir=str(results_dir),
            briefs_dir=str(briefs_dir),
        )
        with TestClient(app) as tc:
            body = tc.get("/console/status").json()
            assert body["queues"]["scan"] == 0


# ---------------------------------------------------------------------------
# Demo: GET /console/briefs
# ---------------------------------------------------------------------------

class TestConsoleBriefs:
    def test_list_briefs(self, client):
        resp = client.get("/console/briefs")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        assert body[0]["domain"] == "example.dk"
        assert body[0]["company_name"] == "Test Restaurant ApS"
        assert body[0]["findings_count"] == 2

    def test_list_briefs_empty_dir(self, results_dir, monkeypatch, tmp_path):
        empty = tmp_path / "empty_briefs"
        empty.mkdir()
        app = _make_app(str(results_dir), str(empty), monkeypatch)
        with TestClient(app) as tc:
            body = tc.get("/console/briefs").json()
            assert body == []

    def test_list_briefs_missing_dir(self, results_dir, monkeypatch):
        app = _make_app(str(results_dir), "/nonexistent", monkeypatch)
        with TestClient(app) as tc:
            body = tc.get("/console/briefs").json()
            assert body == []


# ---------------------------------------------------------------------------
# Demo: POST /console/demo/start
# ---------------------------------------------------------------------------

class TestDemoStart:
    def test_start_valid_domain(self, client):
        resp = client.post("/console/demo/start", json={"domain": "example.dk"})
        assert resp.status_code == 200
        body = resp.json()
        assert "scan_id" in body
        assert body["domain"] == "example.dk"

    def test_start_unknown_domain(self, client):
        resp = client.post("/console/demo/start", json={"domain": "nonexistent.dk"})
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Demo orchestrator: event sequence
# ---------------------------------------------------------------------------

class TestDemoOrchestrator:
    def test_event_sequence(self):
        """Verify events are published in the correct order."""
        # Run with minimal sleeps — events go to in-process queue
        with patch("src.api.demo_orchestrator.asyncio.sleep", return_value=asyncio.sleep(0)):
            loop = asyncio.new_event_loop()
            loop.run_until_complete(run_demo_replay("test-001", SAMPLE_BRIEF))
            loop.close()

        # Collect all events from the in-process queue
        queue = get_demo_queue("test-001")
        events = []
        while not queue.empty():
            events.append(json.loads(queue.get_nowait()))

        # Verify sequence
        types = [e["type"] for e in events]

        # Starts with two phase events
        assert types[0] == "phase"
        assert events[0]["phase"] == "initializing"
        assert types[1] == "phase"
        assert events[1]["phase"] == "scanning"

        # Then scan_start/scan_complete pairs
        scan_events = [e for e in events if e["type"] in ("scan_start", "scan_complete")]
        assert len(scan_events) == len(SCAN_SEQUENCE) * 2
        for i in range(0, len(scan_events), 2):
            assert scan_events[i]["type"] == "scan_start"
            assert scan_events[i + 1]["type"] == "scan_complete"
            assert scan_events[i]["scan_type"] == scan_events[i + 1]["scan_type"]

        # Then tech_reveal
        tech_idx = types.index("tech_reveal")
        assert events[tech_idx]["tech_stack"] == SAMPLE_BRIEF["tech_stack"]

        # Then findings
        finding_events = [e for e in events if e["type"] == "finding"]
        assert len(finding_events) == len(SAMPLE_BRIEF["findings"])
        assert finding_events[0]["severity"] == "medium"
        assert finding_events[1]["severity"] == "low"

        # Ends with complete
        assert types[-1] == "complete"
        assert events[-1]["findings_count"] == 2


# ---------------------------------------------------------------------------
# Demo: WebSocket
# ---------------------------------------------------------------------------

class TestDemoWebSocket:
    def test_websocket_connects(self, client):
        """Verify the WebSocket endpoint accepts connections."""
        with client.websocket_connect("/console/demo/ws/test-id") as ws:
            # Connection accepted — close from client side
            ws.close()

    def test_demo_start_stores_pending(self, client):
        """Demo start stores the brief for the WebSocket to pick up."""
        resp = client.post("/console/demo/start", json={"domain": "example.dk"})
        assert resp.status_code == 200
        assert "scan_id" in resp.json()
