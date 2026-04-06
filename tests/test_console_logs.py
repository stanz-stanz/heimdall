"""Tests for the console logs REST endpoint."""

import collections
import json
import time

import fakeredis
import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app


NOW = time.time()


def _make_entry(source="api", level="INFO", message="test", ts=None, ctx=None):
    entry = {
        "ts": ts or NOW,
        "level": level,
        "source": source,
        "module": "src.test",
        "message": message,
    }
    if ctx:
        entry["ctx"] = ctx
    return entry


@pytest.fixture
def client(tmp_path, monkeypatch):
    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr("redis.Redis.from_url", lambda *a, **kw: fake)

    app = create_app(
        redis_url="redis://fake:6379/0",
        results_dir=str(tmp_path / "results"),
        briefs_dir=str(tmp_path / "briefs"),
    )

    with TestClient(app) as tc:
        # Pre-populate the log buffer (after lifespan startup creates it)
        buffer = app.state.log_buffer
        buffer.append(_make_entry(source="api", level="INFO", message="api started"))
        buffer.append(_make_entry(source="worker-1", level="INFO", message="scan_start domain=test.dk",
                                  ctx={"domain": "test.dk"}))
        buffer.append(_make_entry(source="worker-2", level="ERROR", message="scan_failed domain=bad.dk",
                                  ctx={"domain": "bad.dk"}))
        buffer.append(_make_entry(source="delivery", level="WARNING", message="redis_reconnect attempt=2"))
        buffer.append(_make_entry(source="api", level="ERROR", message="http_error path=/console/dashboard"))
        yield tc


class TestLogsEndpoint:
    def test_logs_returns_entries(self, client):
        resp = client.get("/console/logs")
        assert resp.status_code == 200
        body = resp.json()
        assert "entries" in body
        assert "total" in body
        assert body["total"] == 5

    def test_logs_default_limit(self, client):
        resp = client.get("/console/logs")
        body = resp.json()
        assert len(body["entries"]) == 5  # less than default 200

    def test_logs_custom_limit(self, client):
        body = client.get("/console/logs?limit=2").json()
        assert len(body["entries"]) == 2

    def test_logs_newest_first(self, client):
        body = client.get("/console/logs").json()
        # Last appended entry should be first in results
        assert body["entries"][0]["message"] == "http_error path=/console/dashboard"

    def test_logs_filter_by_source(self, client):
        body = client.get("/console/logs?source=api").json()
        assert all(e["source"] == "api" for e in body["entries"])
        assert len(body["entries"]) == 2

    def test_logs_filter_multiple_sources(self, client):
        body = client.get("/console/logs?source=api,delivery").json()
        sources = {e["source"] for e in body["entries"]}
        assert sources == {"api", "delivery"}

    def test_logs_filter_by_level(self, client):
        body = client.get("/console/logs?level=ERROR").json()
        assert all(e["level"] == "ERROR" for e in body["entries"])
        assert len(body["entries"]) == 2

    def test_logs_filter_by_level_warning_and_above(self, client):
        body = client.get("/console/logs?level=WARNING").json()
        levels = {e["level"] for e in body["entries"]}
        assert levels <= {"WARNING", "ERROR", "CRITICAL"}
        assert len(body["entries"]) == 3

    def test_logs_filter_by_text(self, client):
        body = client.get("/console/logs?q=domain").json()
        assert all("domain" in e["message"].lower() for e in body["entries"])

    def test_logs_filter_by_text_case_insensitive(self, client):
        body = client.get("/console/logs?q=DOMAIN").json()
        assert len(body["entries"]) > 0

    def test_logs_filter_combined(self, client):
        body = client.get("/console/logs?source=worker-2&level=ERROR").json()
        assert len(body["entries"]) == 1
        assert body["entries"][0]["source"] == "worker-2"

    def test_logs_empty_buffer(self, tmp_path, monkeypatch):
        fake = fakeredis.FakeRedis(decode_responses=True)
        monkeypatch.setattr("redis.Redis.from_url", lambda *a, **kw: fake)
        app = create_app(
            redis_url="redis://fake:6379/0",
            results_dir=str(tmp_path / "results"),
            briefs_dir=str(tmp_path / "briefs"),
        )
        with TestClient(app) as tc:
            body = tc.get("/console/logs").json()
            assert body["entries"] == []
            assert body["total"] == 0

    def test_logs_since_filter(self, client):
        future = NOW + 3600
        body = client.get(f"/console/logs?since={future}").json()
        assert len(body["entries"]) == 0
