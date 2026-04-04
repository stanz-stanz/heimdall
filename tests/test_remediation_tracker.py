"""Tests for remediation state machine."""

from __future__ import annotations

import pytest

from src.client_memory.models import FindingRecord
from src.client_memory.remediation import InvalidTransition, RemediationTracker


@pytest.fixture
def tracker():
    return RemediationTracker()


@pytest.fixture
def open_finding():
    return FindingRecord(
        finding_id="abc123def456",
        description="Missing HSTS header",
        severity="medium",
        status="open",
        first_detected="2026-03-21",
        last_detected="2026-03-28",
        status_history=[{"status": "open", "date": "2026-03-21", "source": "scan:initial"}],
    )


# --- Valid forward transitions ---


def test_open_to_acknowledged(tracker, open_finding):
    result = tracker.transition(open_finding, "acknowledged", "client_reply", "2026-03-22T10:00:00Z")
    assert result.status == "acknowledged"
    assert len(result.status_history) == 2
    assert result.status_history[-1]["source"] == "client_reply"


def test_acknowledged_to_resolved(tracker, open_finding):
    tracker.transition(open_finding, "acknowledged", "client_reply")
    result = tracker.transition(open_finding, "resolved", "scan")
    assert result.status == "resolved"
    assert result.resolved_date is not None


# --- Invalid transitions ---


def test_skip_open_to_resolved_invalid(tracker, open_finding):
    with pytest.raises(InvalidTransition):
        tracker.transition(open_finding, "resolved", "client_reply")


def test_backward_acknowledged_to_open_invalid(tracker, open_finding):
    tracker.transition(open_finding, "acknowledged", "client_reply")
    with pytest.raises(InvalidTransition):
        tracker.transition(open_finding, "open", "client_reply")


# --- Regression (reopen) ---


def test_reopen_from_resolved(tracker, open_finding):
    tracker.transition(open_finding, "acknowledged", "client_reply")
    tracker.transition(open_finding, "resolved", "scan")
    assert open_finding.status == "resolved"

    result = tracker.reopen(open_finding, "scan:regression")
    assert result.status == "open"
    assert result.resolved_date is None
    assert result.status_history[-1]["source"] == "scan:regression"


def test_reopen_from_acknowledged(tracker, open_finding):
    tracker.transition(open_finding, "acknowledged", "client_reply")
    result = tracker.reopen(open_finding, "scan:regression")
    assert result.status == "open"


# --- Source and timestamp tracking ---


def test_transition_records_source(tracker, open_finding):
    tracker.transition(open_finding, "acknowledged", "operator", "2026-03-25T14:30:00Z")
    entry = open_finding.status_history[-1]
    assert entry["source"] == "operator"
    assert entry["date"] == "2026-03-25T14:30:00Z"
    assert entry["status"] == "acknowledged"


# --- Config loading ---


def test_default_config_when_missing(tmp_path):
    tracker = RemediationTracker(config_path=tmp_path / "nonexistent.json")
    assert tracker.is_valid_transition("open", "acknowledged")
    assert tracker.escalation_threshold_days == 14
