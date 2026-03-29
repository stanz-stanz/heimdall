"""Tests for client history — scan recording, delta orchestration, finding queries."""

from __future__ import annotations

import pytest

from src.client_memory.delta import DeltaDetector
from src.client_memory.history import ClientHistory
from src.client_memory.remediation import RemediationTracker
from src.client_memory.storage import AtomicFileStore


@pytest.fixture
def store(tmp_path):
    return AtomicFileStore(str(tmp_path))


@pytest.fixture
def history(store):
    return ClientHistory(store, DeltaDetector(), RemediationTracker())


@pytest.fixture
def sample_brief():
    return {
        "domain": "example.dk",
        "scan_date": "2026-03-28",
        "findings": [
            {"severity": "medium", "description": "Missing HSTS header", "risk": "No HTTPS enforcement"},
            {"severity": "low", "description": "Missing CSP header", "risk": "No script restrictions"},
        ],
    }


@pytest.fixture
def sample_brief_v2():
    """Second scan: one finding resolved, one new."""
    return {
        "domain": "example.dk",
        "scan_date": "2026-03-29",
        "findings": [
            {"severity": "medium", "description": "Missing HSTS header", "risk": "No HTTPS enforcement"},
            {"severity": "high", "description": "SSL certificate expired", "risk": "Visitors blocked"},
        ],
    }


# --- Load history ---


def test_load_history_empty(history):
    result = history.load_history("client-001")
    assert result["client_id"] == "client-001"
    assert result["scans"] == []
    assert result["findings"] == []


# --- Record scan ---


def test_first_scan_all_new(history, sample_brief):
    delta = history.record_scan("client-001", sample_brief)
    assert len(delta.new) == 2
    assert len(delta.recurring) == 0
    assert len(delta.resolved) == 0


def test_first_scan_creates_finding_records(history, store, sample_brief):
    history.record_scan("client-001", sample_brief)
    data = store.read_json("client-001", "history.json")
    assert len(data["findings"]) == 2
    assert all(f["status"] == "open" for f in data["findings"])


def test_second_scan_detects_delta(history, sample_brief, sample_brief_v2):
    history.record_scan("client-001", sample_brief)
    delta = history.record_scan("client-001", sample_brief_v2)
    assert len(delta.recurring) == 1  # HSTS still missing
    assert len(delta.new) == 1  # SSL expired
    assert len(delta.resolved) == 1  # CSP resolved


def test_second_scan_updates_history(history, store, sample_brief, sample_brief_v2):
    history.record_scan("client-001", sample_brief)
    history.record_scan("client-001", sample_brief_v2)
    data = store.read_json("client-001", "history.json")
    assert len(data["scans"]) == 2
    # Should have 3 findings total: HSTS (open), SSL (open), CSP (resolved)
    statuses = {f["description"]: f["status"] for f in data["findings"]}
    assert "open" in statuses.get("Missing HSTS header", "")
    assert "resolved" in statuses.get("Missing CSP header", "")


def test_scan_entry_has_delta_summary(history, store, sample_brief, sample_brief_v2):
    history.record_scan("client-001", sample_brief)
    history.record_scan("client-001", sample_brief_v2)
    data = store.read_json("client-001", "history.json")
    second_scan = data["scans"][1]
    assert second_scan["delta_summary"]["new"] == 1
    assert second_scan["delta_summary"]["recurring"] == 1
    assert second_scan["delta_summary"]["resolved"] == 1


# --- Finding queries ---


def test_get_finding_status(history, sample_brief):
    history.record_scan("client-001", sample_brief)
    # Get finding ID for the HSTS finding
    data = history.load_history("client-001")
    fid = data["findings"][0]["finding_id"]
    status = history.get_finding_status("client-001", fid)
    assert status == "open"


def test_get_finding_status_nonexistent(history, sample_brief):
    history.record_scan("client-001", sample_brief)
    assert history.get_finding_status("client-001", "nonexistent") is None


def test_get_open_findings(history, sample_brief, sample_brief_v2):
    history.record_scan("client-001", sample_brief)
    history.record_scan("client-001", sample_brief_v2)
    open_findings = history.get_open_findings("client-001")
    assert len(open_findings) == 2  # HSTS + SSL (CSP resolved)


def test_get_stale_findings_none_stale(history, sample_brief):
    history.record_scan("client-001", sample_brief)
    stale = history.get_stale_findings("client-001", days=14)
    assert len(stale) == 0  # Just created today


# --- Message recording ---


def test_record_message(history, store, sample_brief):
    history.record_scan("client-001", sample_brief)
    history.record_message("client-001", {
        "message_id": "msg-001",
        "type": "weekly_report",
        "sent_at": "2026-03-28T10:00:00Z",
    })
    data = store.read_json("client-001", "history.json")
    assert len(data["messages"]) == 1
    assert data["messages"][0]["message_id"] == "msg-001"
