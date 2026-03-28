"""Tests for the Heimdall Results API."""

import json

import fakeredis
import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_result(domain="example.dk", status="completed", scan_date="2026-03-27"):
    """Build a result dict matching worker output format."""
    return {
        "domain": domain,
        "job_id": "test-001",
        "status": status,
        "scan_result": {"domain": domain, "cms": "WordPress", "server": "Apache"},
        "brief": {
            "domain": domain,
            "cvr": "12345678",
            "company_name": "Test ApS",
            "scan_date": scan_date,
            "bucket": "A",
            "gdpr_sensitive": True,
            "gdpr_reasons": ["Data-handling plugins: Gravityforms"],
            "industry": "Servering af mad",
            "technology": {
                "cms": "WordPress",
                "hosting": "one.com",
                "ssl": {"valid": True, "issuer": "Let's Encrypt", "expiry": "2026-06-01", "days_remaining": 60},
                "server": "Apache",
                "detected_plugins": ["Gravityforms"],
                "headers": {
                    "x_frame_options": False,
                    "content_security_policy": False,
                    "strict_transport_security": False,
                    "x_content_type_options": False,
                },
            },
            "tech_stack": ["WordPress:6.9.4", "PHP", "MySQL"],
            "subdomains": {"count": 1, "list": ["www.example.dk"]},
            "dns": {"a": ["1.2.3.4"], "mx": ["mail.example.dk"]},
            "cloud_exposure": {"count": 0, "buckets": []},
            "findings": [
                {"severity": "medium", "description": "Missing CSP header", "risk": "XSS risk"},
                {"severity": "info", "description": "WordPress detected", "risk": "Keep updated"},
            ],
        },
        "timing": {"total_ms": 879},
        "cache_stats": {"hits": 5, "misses": 4},
    }


def _write_result(base_dir, client_id, domain, date, result):
    """Write a result JSON file to the directory tree."""
    domain_dir = base_dir / client_id / domain
    domain_dir.mkdir(parents=True, exist_ok=True)
    path = domain_dir / f"{date}.json"
    path.write_text(json.dumps(result), encoding="utf-8")
    return path


@pytest.fixture
def results_dir(tmp_path):
    """Populated results directory with two domains and multiple dates."""
    _write_result(tmp_path, "prospect", "example.dk", "2026-03-27", _make_result())
    _write_result(tmp_path, "prospect", "example.dk", "2026-03-26", _make_result(scan_date="2026-03-26"))
    _write_result(tmp_path, "prospect", "other.dk", "2026-03-27", _make_result(domain="other.dk"))
    return tmp_path


def _make_app(results_dir: str, monkeypatch):
    """Create app with fakeredis patched in."""
    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr("redis.Redis.from_url", lambda *a, **kw: fake)
    app = create_app(redis_url="redis://fake:6379/0", results_dir=results_dir)
    return app


@pytest.fixture
def client(results_dir, monkeypatch):
    """TestClient backed by tmp_path results and fakeredis (no real Redis)."""
    app = _make_app(str(results_dir), monkeypatch)
    with TestClient(app) as tc:
        yield tc


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

class TestHealth:
    def test_health_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["redis"] == "connected"
        assert body["results_dir"] == "available"

    def test_health_redis_disconnected(self, results_dir, monkeypatch):
        app = _make_app(str(results_dir), monkeypatch)
        with TestClient(app) as tc:
            # Simulate Redis going down after startup
            app.state.redis = None
            resp = tc.get("/health")
            assert resp.status_code == 200
            assert resp.json()["redis"] == "disconnected"

    def test_health_results_dir_missing(self, monkeypatch):
        app = _make_app("/nonexistent/path", monkeypatch)
        with TestClient(app) as tc:
            resp = tc.get("/health")
            assert resp.status_code == 200
            assert resp.json()["results_dir"] == "missing"


# ---------------------------------------------------------------------------
# Get Result
# ---------------------------------------------------------------------------

class TestGetResult:
    def test_get_latest_result(self, client):
        resp = client.get("/results/prospect/example.dk")
        assert resp.status_code == 200
        body = resp.json()
        assert body["domain"] == "example.dk"
        assert body["brief"]["scan_date"] == "2026-03-27"
        assert "scan_result" not in body

    def test_get_result_by_date(self, client):
        resp = client.get("/results/prospect/example.dk?date=2026-03-26")
        assert resp.status_code == 200
        assert resp.json()["brief"]["scan_date"] == "2026-03-26"

    def test_get_result_include_full(self, client):
        resp = client.get("/results/prospect/example.dk?include=full")
        assert resp.status_code == 200
        body = resp.json()
        assert "scan_result" in body
        assert body["scan_result"]["cms"] == "WordPress"

    def test_result_not_found_404(self, client):
        resp = client.get("/results/prospect/nonexistent.dk")
        assert resp.status_code == 404

    def test_invalid_date_400(self, client):
        resp = client.get("/results/prospect/example.dk?date=not-a-date")
        assert resp.status_code == 400

    def test_corrupted_file_returns_404(self, results_dir, monkeypatch):
        """A corrupted JSON file is treated as missing (None from store)."""
        domain_dir = results_dir / "prospect" / "broken.dk"
        domain_dir.mkdir(parents=True)
        (domain_dir / "2026-03-27.json").write_text("{invalid json", encoding="utf-8")

        app = _make_app(str(results_dir), monkeypatch)
        with TestClient(app) as tc:
            resp = tc.get("/results/prospect/broken.dk")
            assert resp.status_code == 404


# ---------------------------------------------------------------------------
# List Domains
# ---------------------------------------------------------------------------

class TestListDomains:
    def test_list_domains(self, client):
        resp = client.get("/results/prospect")
        assert resp.status_code == 200
        body = resp.json()
        assert body["client_id"] == "prospect"
        assert body["total"] == 2
        assert len(body["domains"]) == 2
        domains = {d["domain"] for d in body["domains"]}
        assert "example.dk" in domains
        assert "other.dk" in domains
        assert body["domains"][0]["findings_count"] == 2

    def test_list_domains_pagination(self, client):
        resp = client.get("/results/prospect?limit=1&offset=0")
        body = resp.json()
        assert len(body["domains"]) == 1
        assert body["total"] == 2
        assert body["limit"] == 1
        assert body["offset"] == 0

    def test_list_domains_empty_client(self, client):
        resp = client.get("/results/unknown-client")
        assert resp.status_code == 200
        body = resp.json()
        assert body["domains"] == []
        assert body["total"] == 0


# ---------------------------------------------------------------------------
# List Dates
# ---------------------------------------------------------------------------

class TestListDates:
    def test_list_dates(self, client):
        resp = client.get("/results/prospect/example.dk/dates")
        assert resp.status_code == 200
        body = resp.json()
        assert body["dates"] == ["2026-03-27", "2026-03-26"]

    def test_list_dates_not_found(self, client):
        resp = client.get("/results/prospect/nonexistent.dk/dates")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Path Traversal
# ---------------------------------------------------------------------------

class TestPathTraversal:
    def test_dotdot_client_id(self, client):
        """FastAPI splits on / so ../../etc never reaches the handler as one param."""
        resp = client.get("/results/../../etc")
        assert resp.status_code in (400, 404)

    def test_dotdot_domain(self, client):
        resp = client.get("/results/prospect/../../etc")
        assert resp.status_code in (400, 404)

    def test_dotdot_encoded_client_id(self, client):
        """Dots in a single segment are caught by the regex."""
        resp = client.get("/results/..prospect")
        assert resp.status_code == 400

    def test_single_char_rejected(self, client):
        """Single-character names don't match the 2+ char regex."""
        resp = client.get("/results/x")
        assert resp.status_code == 400
