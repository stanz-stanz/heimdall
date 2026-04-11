"""Tests for the pipeline export script."""

from __future__ import annotations

import csv
import json
from unittest.mock import MagicMock, patch

import pytest

from scripts.export_results import _find_latest_result, export


@pytest.fixture
def results_dir(tmp_path):
    """Create mock worker results in a tmp directory."""
    prospect = tmp_path / "results" / "prospect"

    # Domain 1: WordPress site with findings
    d1 = prospect / "example.dk"
    d1.mkdir(parents=True)
    (d1 / "2026-03-29.json").write_text(json.dumps({
        "domain": "example.dk",
        "status": "completed",
        "brief": {
            "domain": "example.dk",
            "cvr": "12345678",
            "company_name": "Example ApS",
            "scan_date": "2026-03-29",
            "bucket": "A",
            "gdpr_sensitive": True,
            "gdpr_reasons": ["Data-handling plugins"],
            "industry": "Restaurant",
            "technology": {
                "cms": "WordPress",
                "hosting": "one.com",
                "ssl": {"valid": True, "issuer": "LE", "expiry": "2026-06-01", "days_remaining": 64},
                "server": "nginx",
                "detected_plugins": ["Contact Form 7"],
                "headers": {},
            },
            "tech_stack": ["WordPress:6.9.4"],
            "subdomains": {"count": 2, "list": ["www.example.dk", "mail.example.dk"]},
            "dns": {},
            "cloud_exposure": [],
            "findings": [
                {"severity": "medium", "description": "Missing HSTS", "risk": "..."},
            ],
        },
    }))

    # Domain 2: minimal site
    d2 = prospect / "other.dk"
    d2.mkdir(parents=True)
    (d2 / "2026-03-29.json").write_text(json.dumps({
        "domain": "other.dk",
        "status": "completed",
        "brief": {
            "domain": "other.dk",
            "cvr": "",
            "company_name": "other.dk",
            "scan_date": "2026-03-29",
            "bucket": "E",
            "gdpr_sensitive": False,
            "gdpr_reasons": [],
            "industry": "",
            "technology": {
                "cms": "",
                "hosting": "Unknown",
                "ssl": {"valid": True, "issuer": "LE", "expiry": "2026-12-01", "days_remaining": 247},
                "server": "",
                "detected_plugins": [],
                "headers": {},
            },
            "tech_stack": [],
            "subdomains": {"count": 0, "list": []},
            "dns": {},
            "cloud_exposure": [],
            "findings": [],
        },
    }))

    return tmp_path / "results"


@pytest.fixture
def output_dir(tmp_path):
    return tmp_path / "output"


# --- Normal export ---


def test_export_produces_csv_and_briefs(results_dir, output_dir):
    summary = export(str(results_dir), str(output_dir))
    assert summary["domains"] == 2
    assert summary["briefs"] == 2
    assert (output_dir / "prospects-list.csv").is_file()
    assert (output_dir / "briefs" / "example.dk.json").is_file()
    assert (output_dir / "briefs" / "other.dk.json").is_file()


def test_csv_has_correct_columns(results_dir, output_dir):
    export(str(results_dir), str(output_dir))
    with open(output_dir / "prospects-list.csv") as f:
        reader = csv.DictReader(f)
        row = next(reader)
    expected = [
        "cvr_number", "company_name", "website", "bucket",
        "industry_code", "industry_name", "gdpr_sensitive", "contactable",
        "cms", "hosting", "ssl_valid", "ssl_expiry", "subdomain_count",
        "findings_count",
    ]
    assert list(row.keys()) == expected


def test_csv_row_values(results_dir, output_dir):
    export(str(results_dir), str(output_dir))
    with open(output_dir / "prospects-list.csv") as f:
        rows = list(csv.DictReader(f))
    wp_row = next(r for r in rows if r["website"] == "example.dk")
    assert wp_row["bucket"] == "A"
    assert wp_row["cms"] == "WordPress"
    assert wp_row["findings_count"] == "1"
    assert wp_row["gdpr_sensitive"] == "True"


def test_brief_matches_result(results_dir, output_dir):
    export(str(results_dir), str(output_dir))
    brief = json.loads((output_dir / "briefs" / "example.dk.json").read_text())
    assert brief["domain"] == "example.dk"
    assert brief["bucket"] == "A"
    assert len(brief["findings"]) == 1


# --- Skipped results ---


def test_skipped_non_completed(results_dir, output_dir):
    """Non-completed results are skipped."""
    d3 = results_dir / "prospect" / "skipped.dk"
    d3.mkdir(parents=True)
    (d3 / "2026-03-29.json").write_text(json.dumps({
        "domain": "skipped.dk",
        "status": "skipped",
        "skip_reason": "robots.txt denied",
        "brief": None,
    }))
    summary = export(str(results_dir), str(output_dir))
    assert summary["domains"] == 2
    assert summary["skipped"] == 1


def test_skipped_malformed_json(results_dir, output_dir):
    d3 = results_dir / "prospect" / "bad.dk"
    d3.mkdir(parents=True)
    (d3 / "2026-03-29.json").write_text("NOT JSON")
    summary = export(str(results_dir), str(output_dir))
    assert summary["domains"] == 2
    assert summary["skipped"] == 1


# --- CVR enrichment ---


def test_cvr_enrichment(results_dir, output_dir, tmp_path):
    """When CVR data is available, contactable field is populated."""
    # Create a dummy CVR file so the file-exists check passes
    cvr_file = tmp_path / "CVR-extract.xlsx"
    cvr_file.write_bytes(b"dummy")

    mock_companies = [MagicMock(
        email="info@example.dk",
        cvr="12345678",
        name="Example ApS",
        industry_code="561010",
        ad_protected=False,
    )]

    with patch("src.prospecting.cvr.read_excel", return_value=mock_companies):
        with patch("src.prospecting.config.FREE_WEBMAIL", set()):
            summary = export(str(results_dir), str(output_dir), cvr_file=str(cvr_file))

    assert summary["cvr_enriched"] > 0
    with open(output_dir / "prospects-list.csv") as f:
        rows = list(csv.DictReader(f))
    wp_row = next(r for r in rows if r["website"] == "example.dk")
    assert wp_row["contactable"] == "True"
    assert wp_row["industry_code"] == "561010"


def test_missing_cvr_file(results_dir, output_dir):
    """Export succeeds without CVR file — contactable is empty."""
    summary = export(str(results_dir), str(output_dir), cvr_file="/nonexistent.xlsx")
    assert summary["domains"] == 2
    assert summary["cvr_enriched"] == 0
    with open(output_dir / "prospects-list.csv") as f:
        rows = list(csv.DictReader(f))
    assert all(r["contactable"] == "" for r in rows)


def test_missing_openpyxl(results_dir, output_dir):
    """Export succeeds when openpyxl is not installed."""
    with patch.dict("sys.modules", {"openpyxl": None}):
        summary = export(str(results_dir), str(output_dir), cvr_file="fake.xlsx")
    assert summary["domains"] == 2


# --- Missing results dir ---


def test_missing_results_dir(output_dir):
    summary = export("/nonexistent", str(output_dir))
    assert summary["domains"] == 0


# --- Latest result selection ---


def test_find_latest_result(tmp_path):
    d = tmp_path / "domain.dk"
    d.mkdir()
    (d / "2026-03-28.json").write_text(json.dumps({"old": True}))
    (d / "2026-03-29.json").write_text(json.dumps({"new": True}))
    result = _find_latest_result(d)
    assert result.get("new") is True
