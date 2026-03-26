"""Job creator: reads CVR data or client profiles and pushes scan jobs to Redis."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import redis

from src.prospecting.cvr import Company, derive_domains, read_excel
from src.prospecting.filters import apply_pre_scan_filters, load_filters

log = logging.getLogger(__name__)

QUEUE_NAME = "queue:scan"


def _make_job_id() -> str:
    """Generate a unique job ID: scan-{date}-{short_uuid}."""
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    short_id = uuid.uuid4().hex[:8]
    return f"scan-{date_str}-{short_id}"


def _build_job(
    domain: str,
    client_id: str = "prospect",
    tier: str = "watchman",
    layer: int = 1,
    level: int = 0,
    scan_types: list[str] | None = None,
) -> dict[str, Any]:
    """Build a scan job dict matching the architecture spec."""
    return {
        "job_id": _make_job_id(),
        "domain": domain,
        "client_id": client_id,
        "tier": tier,
        "layer": layer,
        "level": level,
        "scan_types": scan_types or ["all"],
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


class JobCreator:
    """Creates scan jobs and pushes them to a Redis queue."""

    def __init__(self, redis_url: str = "redis://localhost:6379/0") -> None:
        self._redis_url = redis_url
        self._conn: redis.Redis = redis.Redis.from_url(
            redis_url, decode_responses=True
        )

    def create_prospect_jobs(
        self, input_path: Path, filters_path: Path
    ) -> int:
        """Read CVR data, apply filters, derive domains, push one job per domain.

        Returns the number of jobs created.
        """
        companies = read_excel(input_path)
        if not companies:
            log.info("No companies found in %s — 0 jobs created", input_path)
            return 0

        filters = load_filters(filters_path)
        companies = apply_pre_scan_filters(companies, filters)
        companies = derive_domains(companies)

        active = [c for c in companies if not c.discarded and c.website_domain]

        # Deduplicate by domain — multiple companies can share a domain
        seen_domains: set[str] = set()
        unique: list[Company] = []
        for company in active:
            if company.website_domain not in seen_domains:
                seen_domains.add(company.website_domain)
                unique.append(company)

        count = 0
        for company in unique:
            job = _build_job(domain=company.website_domain)
            self._push_job(job)
            count += 1

        log.info(
            "Created %d prospect jobs from %d companies (%d unique domains)",
            count,
            len(companies),
            len(seen_domains),
        )
        return count

    def create_client_jobs(self, client_dir: Path, tier: str) -> int:
        """Read client profiles from *client_dir*, create scan jobs per domain.

        Each client profile is a JSON file containing at minimum:
        ``{"client_id": "...", "domains": ["..."], "tier": "...", "level": ...}``

        Returns the number of jobs created.
        """
        if not client_dir.is_dir():
            log.warning("Client directory %s does not exist", client_dir)
            return 0

        profiles = sorted(client_dir.glob("*.json"))
        if not profiles:
            log.info("No client profiles in %s", client_dir)
            return 0

        count = 0
        for profile_path in profiles:
            with open(profile_path, encoding="utf-8") as fh:
                profile = json.load(fh)

            client_id: str = profile.get("client_id", profile_path.stem)
            client_tier: str = profile.get("tier", tier)
            level: int = profile.get("level", 0)
            layer: int = 1 if level == 0 else 2
            domains: list[str] = profile.get("domains", [])

            for domain in domains:
                job = _build_job(
                    domain=domain,
                    client_id=client_id,
                    tier=client_tier,
                    layer=layer,
                    level=level,
                )
                self._push_job(job)
                count += 1

        log.info(
            "Created %d client jobs from %d profiles (tier filter: %s)",
            count,
            len(profiles),
            tier,
        )
        return count

    def _push_job(self, job: dict[str, Any]) -> None:
        """LPUSH a JSON-serialised job to the scan queue."""
        self._conn.lpush(QUEUE_NAME, json.dumps(job))
