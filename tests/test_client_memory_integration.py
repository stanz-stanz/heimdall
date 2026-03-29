"""End-to-end integration tests for client memory in the scan pipeline."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from src.client_memory import (
    AtomicFileStore,
    ClientHistory,
    ClientProfile,
    DeltaDetector,
    RemediationTracker,
)
from src.interpreter.prompts import build_user_prompt
from src.composer.telegram import compose_telegram


@pytest.fixture
def store(tmp_path):
    return AtomicFileStore(str(tmp_path))


@pytest.fixture
def client_memory(store):
    history = ClientHistory(store, DeltaDetector(), RemediationTracker())
    profile = ClientProfile(store)
    return history, profile


@pytest.fixture
def brief_scan1():
    return {
        "domain": "restaurant-nordlys.dk",
        "company_name": "Restaurant Nordlys ApS",
        "scan_date": "2026-03-21",
        "industry": "Servering af mad",
        "technology": {
            "cms": "WordPress",
            "hosting": "one.com",
            "ssl": {"valid": True, "issuer": "Let's Encrypt", "expiry": "2026-06-01", "days_remaining": 72},
            "detected_plugins": ["Gravity Forms"],
            "headers": {
                "strict_transport_security": False,
                "content_security_policy": False,
                "x_frame_options": False,
                "x_content_type_options": True,
            },
        },
        "tech_stack": ["WordPress:6.9.4"],
        "gdpr_sensitive": True,
        "gdpr_reasons": ["Data-handling plugins"],
        "findings": [
            {"severity": "medium", "description": "Missing HSTS header", "risk": "No HTTPS enforcement"},
            {"severity": "low", "description": "Missing CSP header", "risk": "No script restrictions"},
            {"severity": "low", "description": "Missing X-Frame-Options", "risk": "Clickjacking possible"},
        ],
    }


@pytest.fixture
def brief_scan2():
    """Second scan: HSTS fixed, new SSL finding, CSP still missing."""
    return {
        "domain": "restaurant-nordlys.dk",
        "company_name": "Restaurant Nordlys ApS",
        "scan_date": "2026-03-28",
        "industry": "Servering af mad",
        "technology": {
            "cms": "WordPress",
            "hosting": "one.com",
            "ssl": {"valid": True, "issuer": "Let's Encrypt", "expiry": "2026-04-05", "days_remaining": 7},
            "detected_plugins": ["Gravity Forms"],
            "headers": {
                "strict_transport_security": True,
                "content_security_policy": False,
                "x_frame_options": False,
                "x_content_type_options": True,
            },
        },
        "tech_stack": ["WordPress:6.9.4"],
        "gdpr_sensitive": True,
        "gdpr_reasons": ["Data-handling plugins"],
        "findings": [
            {"severity": "high", "description": "SSL certificate expires in 7 days", "risk": "Visitors blocked soon"},
            {"severity": "low", "description": "Missing CSP header", "risk": "No script restrictions"},
            {"severity": "low", "description": "Missing X-Frame-Options", "risk": "Clickjacking possible"},
        ],
    }


# --- Full flow: two scans with delta ---


class TestFullDeltaFlow:

    def test_two_scans_produce_correct_delta(self, client_memory, brief_scan1, brief_scan2):
        history, profile = client_memory
        profile.create_profile("client-001", "Restaurant Nordlys", "restaurant-nordlys.dk")

        # First scan
        delta1 = history.record_scan("client-001", brief_scan1)
        assert len(delta1.new) == 3
        assert len(delta1.recurring) == 0
        assert len(delta1.resolved) == 0

        # Second scan
        delta2 = history.record_scan("client-001", brief_scan2)
        assert len(delta2.new) == 1  # SSL expires
        assert len(delta2.recurring) == 2  # CSP + X-Frame-Options
        assert len(delta2.resolved) == 1  # HSTS fixed

    def test_delta_context_in_interpreter_prompt(self, client_memory, brief_scan1, brief_scan2):
        history, _ = client_memory
        history.record_scan("client-001", brief_scan1)
        delta2 = history.record_scan("client-001", brief_scan2)

        delta_context = {
            "new": [{"description": f.get("description", ""), "severity": f.get("severity", "")} for f in delta2.new],
            "recurring": [{"description": f.get("description", ""), "severity": f.get("severity", "")} for f in delta2.recurring],
            "resolved": [{"description": r.description, "severity": r.severity} for r in delta2.resolved],
        }

        prompt = build_user_prompt(brief_scan2, delta_context=delta_context)
        assert "Delta since last scan:" in prompt
        assert "RESOLVED since last scan" in prompt
        assert "Missing HSTS header" in prompt  # in resolved section
        assert "NEW since last scan:" in prompt
        assert "SSL certificate expires" in prompt

    def test_delta_context_in_telegram_composer(self, client_memory, brief_scan1, brief_scan2):
        history, _ = client_memory
        history.record_scan("client-001", brief_scan1)
        delta2 = history.record_scan("client-001", brief_scan2)

        delta_context = {
            "resolved": [{"description": r.description, "severity": r.severity} for r in delta2.resolved],
        }

        # Mock an interpreted output
        interpreted = {
            "domain": "restaurant-nordlys.dk",
            "scan_date": "2026-03-28",
            "good_news": ["SSL is valid"],
            "findings": [
                {"title": "SSL expiring soon", "explanation": "Certificate expires in 7 days",
                 "action": "Renew certificate", "who": "web_host", "effort": "5 minutes"},
            ],
            "summary": "1 urgent item, 1 issue resolved.",
        }

        messages = compose_telegram(interpreted, delta_context=delta_context)
        full_text = " ".join(messages)
        assert "Fixed since last scan" in full_text
        assert "Missing HSTS header" in full_text


# --- Backward compatibility ---


class TestBackwardCompatibility:

    def test_interpret_without_delta(self, brief_scan1):
        """Interpreter works without delta context (prospecting mode)."""
        prompt = build_user_prompt(brief_scan1)
        assert "Delta since last scan" not in prompt
        assert "Missing HSTS header" in prompt  # in findings

    def test_compose_without_delta(self):
        """Composer works without delta context."""
        interpreted = {
            "domain": "test.dk",
            "scan_date": "2026-03-28",
            "good_news": [],
            "findings": [{"title": "Issue", "explanation": "Explanation",
                          "action": "Fix it", "who": "developer", "effort": "1 hour"}],
            "summary": "One issue found.",
        }
        messages = compose_telegram(interpreted)
        assert len(messages) >= 1
        assert "Fixed since last scan" not in messages[0]


# --- Profile + history persistence ---


class TestPersistence:

    def test_history_survives_reload(self, store, brief_scan1):
        """History persists to disk and can be reloaded."""
        h1 = ClientHistory(store, DeltaDetector(), RemediationTracker())
        h1.record_scan("client-001", brief_scan1)

        # Create a new instance (simulating process restart)
        h2 = ClientHistory(store, DeltaDetector(), RemediationTracker())
        history = h2.load_history("client-001")
        assert len(history["scans"]) == 1
        assert len(history["findings"]) == 3

    def test_profile_survives_reload(self, store):
        p1 = ClientProfile(store)
        p1.create_profile("client-001", "Test Co", "test.dk", "sentinel")

        p2 = ClientProfile(store)
        profile = p2.load_profile("client-001")
        assert profile["tier"] == "sentinel"
        assert profile["scan_schedule"] == "daily"
