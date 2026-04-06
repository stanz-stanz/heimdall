"""Tests for the outreach module (promote, interpret, send)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from src.db.connection import init_db
from src.outreach.promote import run_promote, _matches_filters


@pytest.fixture
def db(tmp_path):
    db_path = str(tmp_path / "test_clients.db")
    conn = init_db(db_path)
    return conn, db_path


@pytest.fixture
def briefs_dir(tmp_path):
    d = tmp_path / "briefs"
    d.mkdir()
    return d


def _write_brief(briefs_dir: Path, domain: str, bucket: str = "A",
                 industry_code: str = "561010", findings: list | None = None) -> Path:
    brief = {
        "domain": domain,
        "company_name": f"Test {domain}",
        "cvr": "12345678",
        "bucket": bucket,
        "industry_code": industry_code,
        "industry": "Restaurants",
        "findings": findings or [
            {"severity": "critical", "description": "No SSL"},
            {"severity": "high", "description": "Missing HSTS"},
            {"severity": "medium", "description": "Missing CSP"},
        ],
    }
    path = briefs_dir / f"{domain}.json"
    path.write_text(json.dumps(brief))
    return path


class TestPromote:
    def test_basic_promote(self, db, briefs_dir):
        _, db_path = db
        _write_brief(briefs_dir, "example.dk")
        _write_brief(briefs_dir, "test.dk")

        result = run_promote(
            campaign="0426-test",
            briefs_dir=str(briefs_dir),
            db_path=db_path,
        )
        assert result["inserted"] == 2
        assert result["filtered"] == 0
        assert result["skipped"] == 0

    def test_idempotent_promote(self, db, briefs_dir):
        _, db_path = db
        _write_brief(briefs_dir, "example.dk")

        run_promote(campaign="0426-test", briefs_dir=str(briefs_dir), db_path=db_path)
        result = run_promote(campaign="0426-test", briefs_dir=str(briefs_dir), db_path=db_path)
        assert result["inserted"] == 0
        assert result["skipped"] == 1

    def test_bucket_filter(self, db, briefs_dir):
        _, db_path = db
        _write_brief(briefs_dir, "a-site.dk", bucket="A")
        _write_brief(briefs_dir, "e-site.dk", bucket="E")

        result = run_promote(
            campaign="0426-test",
            buckets=["A"],
            briefs_dir=str(briefs_dir),
            db_path=db_path,
        )
        assert result["inserted"] == 1
        assert result["filtered"] == 1

    def test_industry_filter(self, db, briefs_dir):
        _, db_path = db
        _write_brief(briefs_dir, "restaurant.dk", industry_code="561010")
        _write_brief(briefs_dir, "clinic.dk", industry_code="862100")

        result = run_promote(
            campaign="0426-restaurants",
            industry_prefixes=["56"],
            briefs_dir=str(briefs_dir),
            db_path=db_path,
        )
        assert result["inserted"] == 1
        assert result["filtered"] == 1

    def test_severity_counts_stored(self, db, briefs_dir):
        conn, db_path = db
        _write_brief(briefs_dir, "example.dk", findings=[
            {"severity": "critical", "description": "A"},
            {"severity": "critical", "description": "B"},
            {"severity": "high", "description": "C"},
            {"severity": "medium", "description": "D"},
        ])

        run_promote(campaign="0426-test", briefs_dir=str(briefs_dir), db_path=db_path)

        row = conn.execute(
            "SELECT * FROM prospects WHERE domain = 'example.dk'"
        ).fetchone()
        assert row["critical_count"] == 2
        assert row["high_count"] == 1
        assert row["finding_count"] == 4
        assert row["outreach_status"] == "new"

    def test_same_domain_different_campaigns(self, db, briefs_dir):
        _, db_path = db
        _write_brief(briefs_dir, "example.dk")

        r1 = run_promote(campaign="0426-restaurants", briefs_dir=str(briefs_dir), db_path=db_path)
        r2 = run_promote(campaign="0526-restaurants", briefs_dir=str(briefs_dir), db_path=db_path)
        assert r1["inserted"] == 1
        assert r2["inserted"] == 1


class TestMatchesFilters:
    def test_no_filters(self):
        assert _matches_filters({"bucket": "A"}, None, None) is True

    def test_bucket_match(self):
        assert _matches_filters({"bucket": "A"}, ["A", "B"], None) is True

    def test_bucket_no_match(self):
        assert _matches_filters({"bucket": "E"}, ["A", "B"], None) is False

    def test_industry_prefix_match(self):
        assert _matches_filters({"industry_code": "561010"}, None, ["56"]) is True

    def test_industry_prefix_no_match(self):
        assert _matches_filters({"industry_code": "862100"}, None, ["56"]) is False


class TestInterpret:
    @patch("src.outreach.interpret.interpret_brief")
    def test_dry_run_no_api_call(self, mock_interpret, db, briefs_dir):
        conn, db_path = db
        _write_brief(briefs_dir, "example.dk")
        run_promote(campaign="0426-test", briefs_dir=str(briefs_dir), db_path=db_path)

        from src.outreach.interpret import run_interpret
        result = run_interpret(campaign="0426-test", dry_run=True, db_path=db_path)

        mock_interpret.assert_not_called()
        assert result["skipped"] == 1

    @patch("src.outreach.interpret.interpret_brief")
    def test_min_severity_filter(self, mock_interpret, db, briefs_dir):
        conn, db_path = db
        _write_brief(briefs_dir, "no-crit.dk", findings=[
            {"severity": "medium", "description": "Something"},
        ])
        _write_brief(briefs_dir, "has-crit.dk", findings=[
            {"severity": "critical", "description": "Bad"},
        ])
        run_promote(campaign="0426-test", briefs_dir=str(briefs_dir), db_path=db_path)

        mock_interpret.return_value = {"findings": [], "summary": "test"}

        from src.outreach.interpret import run_interpret
        result = run_interpret(
            campaign="0426-test",
            min_severity="high",
            db_path=db_path,
        )
        # Only has-crit.dk should be processed (1 call)
        # no-crit.dk has 0 critical and 0 high, so filtered out by query
        assert mock_interpret.call_count == 1

    @patch("src.outreach.interpret.interpret_brief")
    def test_limit_caps_batch(self, mock_interpret, db, briefs_dir):
        conn, db_path = db
        for i in range(5):
            _write_brief(briefs_dir, f"site{i}.dk")
        run_promote(campaign="0426-test", briefs_dir=str(briefs_dir), db_path=db_path)

        mock_interpret.return_value = {"findings": [], "summary": "test", "good_news": []}

        from src.outreach.interpret import run_interpret
        result = run_interpret(campaign="0426-test", limit=2, db_path=db_path)

        # All 5 sites have identical findings, so only 1 API call + 1 cache hit
        assert mock_interpret.call_count == 1
        assert result["interpreted"] == 2
        assert result["cache_hits"] == 1
        assert result["api_calls"] == 1


class TestChannelSplit:
    """Verify the Redis channel rename doesn't break delivery runner tests."""

    def test_delivery_runner_subscribes_to_client_channel(self):
        from src.delivery import runner
        import inspect
        source = inspect.getsource(runner.DeliveryRunner._subscribe_and_process)
        assert "client-scan-complete" in source
        assert "scan-complete" not in source.replace("client-scan-complete", "")

    def test_worker_publishes_client_channel(self):
        from src.worker import main
        import inspect
        source = inspect.getsource(main)
        assert "client-scan-complete" in source
