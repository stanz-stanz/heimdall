"""Tests for delta detection — finding comparison across scans."""

from __future__ import annotations

import pytest

from src.client_memory.delta import DeltaDetector, normalize_description
from src.client_memory.models import FindingRecord


@pytest.fixture
def detector():
    return DeltaDetector(fuzzy_threshold=0.85)


# --- Finding ID generation ---


def test_finding_id_deterministic(detector):
    id1 = detector.generate_finding_id("medium", "Missing HSTS header")
    id2 = detector.generate_finding_id("medium", "Missing HSTS header")
    assert id1 == id2


def test_finding_id_case_insensitive(detector):
    id1 = detector.generate_finding_id("MEDIUM", "Missing HSTS Header")
    id2 = detector.generate_finding_id("medium", "missing hsts header")
    assert id1 == id2


def test_finding_id_different_severity(detector):
    id1 = detector.generate_finding_id("medium", "Missing HSTS header")
    id2 = detector.generate_finding_id("high", "Missing HSTS header")
    assert id1 != id2


def test_finding_id_12_chars(detector):
    fid = detector.generate_finding_id("low", "Some finding")
    assert len(fid) == 12


# --- Normalization ---


def test_normalize_description_whitespace():
    assert normalize_description("  Missing   HSTS  header  ") == "missing hsts header"


def test_normalize_description_case():
    assert normalize_description("SSL Certificate Expired") == "ssl certificate expired"


# --- Delta detection ---


def test_all_new_first_scan(detector):
    """First scan: no previous findings, everything is NEW."""
    current = [
        {"severity": "medium", "description": "Missing HSTS header", "risk": "..."},
        {"severity": "low", "description": "Missing CSP header", "risk": "..."},
    ]
    delta = detector.detect_delta([], current)
    assert len(delta.new) == 2
    assert len(delta.recurring) == 0
    assert len(delta.resolved) == 0


def test_all_recurring_no_change(detector):
    """Same findings in both scans: all RECURRING."""
    fid1 = detector.generate_finding_id("medium", "Missing HSTS header")
    fid2 = detector.generate_finding_id("low", "Missing CSP header")

    previous = [
        FindingRecord(finding_id=fid1, description="Missing HSTS header",
                      severity="medium", status="open",
                      first_detected="2026-03-21", last_detected="2026-03-21"),
        FindingRecord(finding_id=fid2, description="Missing CSP header",
                      severity="low", status="open",
                      first_detected="2026-03-21", last_detected="2026-03-21"),
    ]
    current = [
        {"severity": "medium", "description": "Missing HSTS header"},
        {"severity": "low", "description": "Missing CSP header"},
    ]
    delta = detector.detect_delta(previous, current)
    assert len(delta.new) == 0
    assert len(delta.recurring) == 2
    assert len(delta.resolved) == 0


def test_mixed_delta(detector):
    """One recurring, one new, one resolved."""
    fid1 = detector.generate_finding_id("medium", "Missing HSTS header")
    fid2 = detector.generate_finding_id("low", "Missing CSP header")

    previous = [
        FindingRecord(finding_id=fid1, description="Missing HSTS header",
                      severity="medium", status="open",
                      first_detected="2026-03-21", last_detected="2026-03-21"),
        FindingRecord(finding_id=fid2, description="Missing CSP header",
                      severity="low", status="open",
                      first_detected="2026-03-21", last_detected="2026-03-21"),
    ]
    current = [
        {"severity": "medium", "description": "Missing HSTS header"},
        {"severity": "high", "description": "SSL certificate expired"},
    ]
    delta = detector.detect_delta(previous, current)
    assert len(delta.new) == 1
    assert delta.new[0]["description"] == "SSL certificate expired"
    assert len(delta.recurring) == 1
    assert len(delta.resolved) == 1
    assert delta.resolved[0].finding_id == fid2


def test_all_resolved_clean_scan(detector):
    """Clean scan: all previous findings resolved."""
    fid1 = detector.generate_finding_id("medium", "Missing HSTS header")
    previous = [
        FindingRecord(finding_id=fid1, description="Missing HSTS header",
                      severity="medium", status="open",
                      first_detected="2026-03-21", last_detected="2026-03-21"),
    ]
    delta = detector.detect_delta(previous, [])
    assert len(delta.new) == 0
    assert len(delta.recurring) == 0
    assert len(delta.resolved) == 1


def test_fuzzy_match_minor_change(detector):
    """Description changes slightly: should match as RECURRING."""
    fid1 = detector.generate_finding_id("medium", "SSL certificate expires in 14 days")
    previous = [
        FindingRecord(finding_id=fid1, description="SSL certificate expires in 14 days",
                      severity="medium", status="open",
                      first_detected="2026-03-14", last_detected="2026-03-21"),
    ]
    current = [
        {"severity": "medium", "description": "SSL certificate expires in 12 days"},
    ]
    delta = detector.detect_delta(previous, current)
    assert len(delta.recurring) == 1
    assert len(delta.new) == 0


def test_fuzzy_match_major_change_no_match(detector):
    """Completely different description: should NOT match."""
    fid1 = detector.generate_finding_id("medium", "Missing HSTS header")
    previous = [
        FindingRecord(finding_id=fid1, description="Missing HSTS header",
                      severity="medium", status="open",
                      first_detected="2026-03-21", last_detected="2026-03-21"),
    ]
    current = [
        {"severity": "medium", "description": "WordPress version 6.9.4 publicly disclosed"},
    ]
    delta = detector.detect_delta(previous, current)
    assert len(delta.new) == 1
    assert len(delta.resolved) == 1


def test_severity_change_creates_new_finding(detector):
    """Same description, different severity: new finding + old resolves."""
    fid1 = detector.generate_finding_id("low", "Missing CSP header")
    previous = [
        FindingRecord(finding_id=fid1, description="Missing CSP header",
                      severity="low", status="open",
                      first_detected="2026-03-21", last_detected="2026-03-21"),
    ]
    current = [
        {"severity": "medium", "description": "Missing CSP header"},
    ]
    delta = detector.detect_delta(previous, current)
    # Fuzzy match requires same severity, so this is NEW + RESOLVED
    assert len(delta.new) == 1
    assert len(delta.resolved) == 1


def test_duplicate_current_findings_deduplicated(detector):
    """Duplicate findings in a single scan are deduplicated."""
    current = [
        {"severity": "medium", "description": "Missing HSTS header"},
        {"severity": "medium", "description": "Missing HSTS header"},
    ]
    delta = detector.detect_delta([], current)
    assert len(delta.new) == 1


def test_resolved_findings_excluded_from_matching(detector):
    """Previously resolved findings are not matched against."""
    fid1 = detector.generate_finding_id("medium", "Missing HSTS header")
    previous = [
        FindingRecord(finding_id=fid1, description="Missing HSTS header",
                      severity="medium", status="resolved",
                      first_detected="2026-03-14", last_detected="2026-03-21",
                      resolved_date="2026-03-21"),
    ]
    current = [
        {"severity": "medium", "description": "Missing HSTS header"},
    ]
    delta = detector.detect_delta(previous, current)
    # Resolved findings are excluded from prev_by_id, so this is NEW
    assert len(delta.new) == 1
    assert len(delta.recurring) == 0
