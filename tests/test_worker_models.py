"""Tests for src.worker.models — Pydantic validation of Redis job payloads."""

import pytest
from pydantic import ValidationError

from src.worker.models import EnrichmentJob, ScanJob


def test_scan_job_valid():
    job = ScanJob.model_validate_json('{"domain": "example.dk", "level": 0}')
    assert job.domain == "example.dk"
    assert job.level == 0
    assert job.client_id == "prospect"


def test_scan_job_missing_domain():
    with pytest.raises(ValidationError):
        ScanJob.model_validate_json('{"level": 0}')


def test_scan_job_extra_fields_ignored():
    job = ScanJob.model_validate_json('{"domain": "x.dk", "extra": "ignored"}')
    assert job.domain == "x.dk"


def test_enrichment_job_valid():
    job = EnrichmentJob.model_validate_json('{"batch_id": 1, "domains": ["a.dk"]}')
    assert job.batch_id == 1
    assert job.domains == ["a.dk"]


def test_enrichment_job_missing_domains():
    with pytest.raises(ValidationError):
        EnrichmentJob.model_validate_json('{"batch_id": 1}')


def test_scan_job_model_dump():
    job = ScanJob(domain="test.dk", level=1)
    d = job.model_dump()
    assert d["domain"] == "test.dk"
    assert isinstance(d, dict)


def test_scan_job_defaults():
    job = ScanJob(domain="test.dk")
    assert job.tier == "watchman"
    assert job.layer == 1
    assert job.level == 0
    assert job.client_id == "prospect"
    assert job.job_type == "scan"
    assert job.scan_types == []


def test_scan_job_full_shape():
    """Validate that a job produced by _build_job passes validation."""
    payload = (
        '{"job_id": "scan-2026-04-11-abc12345", "domain": "firma.dk",'
        ' "client_id": "prospect", "tier": "watchman", "layer": 1,'
        ' "level": 0, "scan_types": ["all"], "created_at": "2026-04-11T10:00:00Z"}'
    )
    job = ScanJob.model_validate_json(payload)
    assert job.domain == "firma.dk"
    assert job.scan_types == ["all"]


def test_enrichment_job_full_shape():
    """Validate that a job produced by _build_enrichment_job passes validation."""
    payload = (
        '{"job_id": "enrich-2026-04-11-abc12345", "job_type": "enrichment",'
        ' "domains": ["a.dk", "b.dk"], "batch_index": 0, "total_batches": 3,'
        ' "stagger_delay": 0, "created_at": "2026-04-11T10:00:00Z"}'
    )
    job = EnrichmentJob.model_validate_json(payload)
    assert job.domains == ["a.dk", "b.dk"]
    assert job.job_type == "enrichment"
    assert job.batch_index == 0


def test_scan_job_with_optional_enrichment_fields():
    """Fields accessed by scan_job.py but not set by _build_job have defaults."""
    job = ScanJob(domain="test.dk")
    assert job.company_name == ""
    assert job.cvr == ""
    assert job.industry_code == ""
    assert job.industry_name == ""


def test_enrichment_job_extra_fields_preserved():
    """extra='allow' means unknown fields survive the round-trip."""
    payload = '{"domains": ["x.dk"], "batch_id": 0, "custom_flag": true}'
    job = EnrichmentJob.model_validate_json(payload)
    d = job.model_dump()
    assert d["custom_flag"] is True
