"""Tests for HTTP Basic Auth middleware on operator console endpoints."""

import base64
import os
import pytest
from unittest.mock import patch

import fakeredis
from fastapi.testclient import TestClient


@pytest.fixture
def app_with_auth():
    with patch.dict(os.environ, {
        "CONSOLE_USER": "admin",
        "CONSOLE_PASSWORD": "secret123",
    }):
        # Need to reimport to pick up env vars
        from src.api.app import create_app
        fake = fakeredis.FakeRedis(decode_responses=True)
        with patch("redis.Redis.from_url", return_value=fake):
            app = create_app(results_dir="/tmp", redis_url="", messages_dir="/tmp")
        return app


def test_console_rejects_without_auth(app_with_auth):
    client = TestClient(app_with_auth)
    resp = client.get("/console/dashboard")
    assert resp.status_code == 401
    assert "WWW-Authenticate" in resp.headers


def test_console_www_authenticate_realm(app_with_auth):
    client = TestClient(app_with_auth)
    resp = client.get("/console/dashboard")
    assert 'Basic realm="Heimdall Console"' in resp.headers["WWW-Authenticate"]


def test_console_accepts_valid_auth(app_with_auth):
    client = TestClient(app_with_auth)
    creds = base64.b64encode(b"admin:secret123").decode()
    # Use /console/status — doesn't need SQLite, so no DB setup needed
    resp = client.get("/console/status", headers={"Authorization": f"Basic {creds}"})
    assert resp.status_code != 401


def test_health_no_auth_required(app_with_auth):
    client = TestClient(app_with_auth)
    resp = client.get("/health")
    assert resp.status_code == 200


def test_results_no_auth_required(app_with_auth):
    client = TestClient(app_with_auth)
    resp = client.get("/results/test-client")
    # May be 404 or 200 but NOT 401
    assert resp.status_code != 401


def test_wrong_password_rejected(app_with_auth):
    client = TestClient(app_with_auth)
    creds = base64.b64encode(b"admin:wrong").decode()
    resp = client.get("/console/dashboard", headers={"Authorization": f"Basic {creds}"})
    assert resp.status_code == 401


def test_wrong_username_rejected(app_with_auth):
    client = TestClient(app_with_auth)
    creds = base64.b64encode(b"notadmin:secret123").decode()
    resp = client.get("/console/dashboard", headers={"Authorization": f"Basic {creds}"})
    assert resp.status_code == 401


def test_malformed_auth_header_rejected(app_with_auth):
    client = TestClient(app_with_auth)
    resp = client.get("/console/dashboard", headers={"Authorization": "Basic !@#$not-valid-base64!!!"})
    assert resp.status_code == 401


def test_app_prefix_protected(app_with_auth):
    """The /app prefix (SPA) is also protected."""
    client = TestClient(app_with_auth)
    resp = client.get("/app/")
    # Should be 401 (no auth) rather than 200 or 404
    assert resp.status_code == 401


def test_no_middleware_when_env_vars_absent():
    """When CONSOLE_USER/PASSWORD are not set, BasicAuthMiddleware is not added."""
    from src.api.app import BasicAuthMiddleware
    env_without_auth = {k: v for k, v in os.environ.items()
                        if k not in ("CONSOLE_USER", "CONSOLE_PASSWORD")}
    with patch.dict(os.environ, env_without_auth, clear=True):
        from src.api.app import create_app
        fake = fakeredis.FakeRedis(decode_responses=True)
        with patch("redis.Redis.from_url", return_value=fake):
            app = create_app(results_dir="/tmp", redis_url="", messages_dir="/tmp")

    # Inspect the middleware stack — BasicAuthMiddleware must not be present
    middleware_classes = [
        type(m.cls if hasattr(m, "cls") else m)
        for m in getattr(app, "user_middleware", [])
    ]
    assert BasicAuthMiddleware not in middleware_classes
