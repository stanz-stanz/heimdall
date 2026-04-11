"""Tests for the scheduler module — job creation and Redis queuing."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import fakeredis
import pytest

from src.prospecting.cvr import Company
from src.scheduler.job_creator import QUEUE_NAME, JobCreator, _build_job

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

REQUIRED_JOB_FIELDS = {
    "job_id",
    "domain",
    "client_id",
    "tier",
    "layer",
    "level",
    "scan_types",
    "created_at",
}


@pytest.fixture()
def fake_redis():
    """Return a fakeredis connection that mimics a real Redis."""
    return fakeredis.FakeRedis(decode_responses=True)


@pytest.fixture()
def creator(fake_redis):
    """Return a JobCreator wired to fakeredis."""
    jc = JobCreator.__new__(JobCreator)
    jc._redis_url = "redis://fake"
    jc._conn = fake_redis
    return jc


def _sample_companies(n: int = 3, ad_protected: bool = False) -> list[Company]:
    """Generate *n* simple Company objects with distinct domains."""
    companies = []
    for i in range(n):
        companies.append(
            Company(
                cvr=str(10000000 + i),
                name=f"Test Firma {i} ApS",
                address="Testvej 1",
                postcode="7100",
                city="Vejle",
                company_form="ApS",
                industry_code="561010",
                industry_name="Restauranter",
                phone="12345678",
                email=f"info@firma{i}.dk",
                ad_protected=ad_protected,
                website_domain=f"firma{i}.dk",
            )
        )
    return companies


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCreateProspectJobs:
    """Test JobCreator.create_prospect_jobs()."""

    @patch("src.scheduler.job_creator.load_filters", return_value={})
    @patch("src.scheduler.job_creator.apply_pre_scan_filters", side_effect=lambda c, f: c)
    @patch("src.scheduler.job_creator.derive_domains", side_effect=lambda c: c)
    @patch("src.scheduler.job_creator.read_excel")
    def test_create_prospect_jobs(
        self, mock_read, mock_derive, mock_filters, mock_load, creator, fake_redis
    ):
        """Correct number of jobs are pushed to Redis."""
        companies = _sample_companies(5)
        mock_read.return_value = companies

        count = creator.create_prospect_jobs(Path("fake.xlsx"), Path("fake.json"))

        assert count == 5
        assert fake_redis.llen(QUEUE_NAME) == 5

    @patch("src.scheduler.job_creator.load_filters", return_value={})
    @patch("src.scheduler.job_creator.apply_pre_scan_filters", side_effect=lambda c, f: c)
    @patch("src.scheduler.job_creator.derive_domains", side_effect=lambda c: c)
    @patch("src.scheduler.job_creator.read_excel")
    def test_job_structure(
        self, mock_read, mock_derive, mock_filters, mock_load, creator, fake_redis
    ):
        """Every pushed job has all required fields with correct types."""
        mock_read.return_value = _sample_companies(1)

        creator.create_prospect_jobs(Path("fake.xlsx"), Path("fake.json"))

        raw = fake_redis.rpop(QUEUE_NAME)
        job = json.loads(raw)

        assert set(job.keys()) == REQUIRED_JOB_FIELDS
        assert job["job_id"].startswith("scan-")
        assert job["domain"] == "firma0.dk"
        assert job["client_id"] == "prospect"
        assert job["tier"] == "watchman"
        assert job["layer"] == 1
        assert job["level"] == 0
        assert job["scan_types"] == ["all"]
        assert "T" in job["created_at"]  # ISO-8601

    @patch("src.scheduler.job_creator.load_filters")
    @patch("src.scheduler.job_creator.apply_pre_scan_filters")
    @patch("src.scheduler.job_creator.derive_domains", side_effect=lambda c: c)
    @patch("src.scheduler.job_creator.read_excel")
    def test_filters_applied(
        self, mock_read, mock_derive, mock_apply, mock_load, creator, fake_redis
    ):
        """Ad-protected companies are excluded when contactable filter is active."""
        all_companies = _sample_companies(3, ad_protected=False)
        # Simulate one ad-protected company being discarded by the filter
        filtered = list(all_companies)
        filtered[1].discard_reason = "filtered:contactable"

        mock_read.return_value = all_companies
        mock_load.return_value = {"contactable": True}
        mock_apply.return_value = filtered

        count = creator.create_prospect_jobs(Path("fake.xlsx"), Path("fake.json"))

        # Company at index 1 was discarded — only 2 should produce jobs
        assert count == 2
        assert fake_redis.llen(QUEUE_NAME) == 2

    @patch("src.scheduler.job_creator.load_filters", return_value={})
    @patch("src.scheduler.job_creator.apply_pre_scan_filters", side_effect=lambda c, f: c)
    @patch("src.scheduler.job_creator.derive_domains", side_effect=lambda c: c)
    @patch("src.scheduler.job_creator.read_excel")
    def test_empty_input(
        self, mock_read, mock_derive, mock_filters, mock_load, creator, fake_redis
    ):
        """Empty company list produces 0 jobs without error."""
        mock_read.return_value = []

        count = creator.create_prospect_jobs(Path("fake.xlsx"), Path("fake.json"))

        assert count == 0
        assert fake_redis.llen(QUEUE_NAME) == 0


class TestRedisDown:
    """Graceful handling when Redis is unavailable."""

    def test_redis_down(self):
        """JobCreator raises a clear error when Redis is unreachable."""
        creator = JobCreator(redis_url="redis://localhost:59999/0")

        with pytest.raises(Exception):
            # _push_job should fail on connection
            creator._push_job(_build_job(domain="example.dk"))


class TestBuildJob:
    """Unit tests for the _build_job helper."""

    def test_defaults(self):
        job = _build_job(domain="example.dk")
        assert job["domain"] == "example.dk"
        assert job["client_id"] == "prospect"
        assert job["tier"] == "watchman"
        assert job["layer"] == 1
        assert job["level"] == 0
        assert job["scan_types"] == ["all"]
        assert set(job.keys()) == REQUIRED_JOB_FIELDS

    def test_custom_values(self):
        job = _build_job(
            domain="client.dk",
            client_id="cli-001",
            tier="sentinel",
            layer=2,
            level=1,
            scan_types=["ssl", "headers"],
        )
        assert job["client_id"] == "cli-001"
        assert job["tier"] == "sentinel"
        assert job["layer"] == 2
        assert job["level"] == 1
        assert job["scan_types"] == ["ssl", "headers"]


class TestCreateClientJobs:
    """Test JobCreator.create_client_jobs()."""

    def test_missing_directory(self, creator):
        """Non-existent directory returns 0."""
        count = creator.create_client_jobs(Path("/nonexistent"), tier="watchman")
        assert count == 0

    def test_client_profiles(self, creator, fake_redis, tmp_path):
        """Jobs are created from client profile JSON files."""
        profile = {
            "client_id": "cli-001",
            "domains": ["alpha.dk", "beta.dk"],
            "tier": "sentinel",
            "level": 0,
        }
        (tmp_path / "client1.json").write_text(json.dumps(profile))

        count = creator.create_client_jobs(tmp_path, tier="watchman")

        assert count == 2
        assert fake_redis.llen(QUEUE_NAME) == 2

        # Verify first job
        raw = fake_redis.rpop(QUEUE_NAME)
        job = json.loads(raw)
        assert job["client_id"] == "cli-001"
        assert job["tier"] == "sentinel"  # from profile, not from arg
