"""Pydantic models for Redis job payloads."""

from pydantic import BaseModel


class ScanJob(BaseModel):
    """Schema for scan jobs from queue:scan."""

    domain: str
    job_id: str = ""
    client_id: str = "prospect"
    tier: str = "watchman"
    layer: int = 1
    level: int = 0
    scan_types: list[str] = []
    created_at: str = ""
    # Optional fields populated by enrichment or legacy pipelines
    company_name: str = ""
    cvr: str = ""
    industry_code: str = ""
    industry_name: str = ""
    job_type: str = "scan"

    model_config = {"extra": "allow"}


class EnrichmentJob(BaseModel):
    """Schema for enrichment jobs from queue:enrichment."""

    batch_id: int = 0
    domains: list[str]
    # Fields set by _build_enrichment_job
    job_id: str = ""
    job_type: str = "enrichment"
    batch_index: int = 0
    total_batches: int = 1
    stagger_delay: int = 0
    created_at: str = ""

    model_config = {"extra": "allow"}
