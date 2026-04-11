"""Job creator: reads CVR data or client profiles and pushes scan jobs to Redis."""

from __future__ import annotations

import json
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import redis
from loguru import logger

from src.prospecting.config import ENRICHMENT_STAGGER_SECONDS, ENRICHMENT_WORKERS
from src.prospecting.cvr import derive_domains, read_excel
from src.prospecting.filters import apply_pre_scan_filters, load_filters

QUEUE_NAME = "queue:scan"
ENRICHMENT_QUEUE = "queue:enrichment"
ENRICHMENT_COUNTER_KEY = "enrichment:completed"
ENRICHMENT_TOTAL_KEY = "enrichment:total"


def _make_job_id() -> str:
    """Generate a unique job ID: scan-{date}-{short_uuid}."""
    date_str = datetime.now(UTC).strftime("%Y-%m-%d")
    short_id = uuid.uuid4().hex[:8]
    return f"scan-{date_str}-{short_id}"


def _make_enrichment_job_id() -> str:
    """Generate a unique enrichment job ID: enrich-{date}-{short_uuid}."""
    date_str = datetime.now(UTC).strftime("%Y-%m-%d")
    short_id = uuid.uuid4().hex[:8]
    return f"enrich-{date_str}-{short_id}"


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
        "created_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def _build_enrichment_job(
    domains: list[str],
    batch_index: int,
    total_batches: int,
    stagger_delay: int,
) -> dict[str, Any]:
    """Build an enrichment job dict for batch subfinder pre-scan."""
    return {
        "job_id": _make_enrichment_job_id(),
        "job_type": "enrichment",
        "domains": domains,
        "batch_index": batch_index,
        "total_batches": total_batches,
        "stagger_delay": stagger_delay,
        "created_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


class JobCreator:
    """Creates scan jobs and pushes them to a Redis queue."""

    def __init__(self, redis_url: str = "redis://localhost:6379/0") -> None:
        self._redis_url = redis_url
        self._conn: redis.Redis = redis.Redis.from_url(
            redis_url, decode_responses=True
        )

    def extract_prospect_domains(
        self, input_path: Path, filters_path: Path
    ) -> list[str]:
        """Read CVR data, apply filters, derive domains, return deduplicated domain list.

        Checks for a pre-enriched SQLite database first (from the local
        enrichment tool). Falls back to the legacy Excel pipeline if no
        database is found.
        """
        # Check for pre-enriched SQLite database
        db_path = input_path.parent.parent / "enriched" / "companies.db"
        if db_path.exists():
            return self._read_enriched_db(db_path)

        # Legacy Excel pipeline
        companies = read_excel(input_path)
        if not companies:
            logger.info("No companies found in {} — 0 domains extracted", input_path)
            return []

        filters = load_filters(filters_path)
        companies = apply_pre_scan_filters(companies, filters)
        companies = derive_domains(companies)

        active = [c for c in companies if not c.discarded and c.website_domain]

        # Deduplicate by domain — multiple companies can share a domain
        seen_domains: set[str] = set()
        unique_domains: list[str] = []
        for company in active:
            if company.website_domain not in seen_domains:
                seen_domains.add(company.website_domain)
                unique_domains.append(company.website_domain)

        logger.info(
            "Extracted {} unique domains from {} companies",
            len(unique_domains),
            len(companies),
        )
        return unique_domains

    @staticmethod
    def _read_enriched_db(db_path: Path) -> list[str]:
        """Read scan-ready domains from the pre-enriched SQLite database."""
        import sqlite3

        logger.info("Using pre-enriched database: {}", db_path)
        conn = sqlite3.connect(f"file:{db_path}?immutable=1", uri=True, timeout=5)
        conn.row_factory = sqlite3.Row

        # Pre-flight: check for stale filter flags
        total = conn.execute("SELECT COUNT(*) as c FROM domains").fetchone()["c"]
        ready = conn.execute(
            "SELECT COUNT(*) as c FROM domains WHERE ready_for_scan = 1"
        ).fetchone()["c"]
        not_ready = total - ready

        if total > 0 and ready < total * 0.1:
            logger.warning(
                "enriched_db_low_ready_ratio: {}/{} domains ready ({:.0f}%). "
                "Possible stale filter flags in database. "
                "Re-run enrichment pipeline or check domains table.",
                ready, total, (ready / total) * 100,
            )

        if not_ready > 0:
            logger.info(
                "enriched_db_stats: {} total, {} ready, {} filtered out",
                total, ready, not_ready,
            )

        rows = conn.execute(
            "SELECT domain FROM domains WHERE ready_for_scan = 1 ORDER BY domain"
        ).fetchall()
        domains = [row["domain"] for row in rows]
        conn.close()
        logger.info("Extracted {} domains from enriched database", len(domains))
        return domains

    def create_scan_jobs_for_domains(self, domains: list[str]) -> int:
        """Push one scan job per domain to the scan queue.

        Returns the number of jobs created.
        """
        count = 0
        for domain in domains:
            job = _build_job(domain=domain)
            self._push_job(job)
            count += 1

        logger.info("Created {} scan jobs for {} domains", count, len(domains))
        return count

    def create_prospect_jobs(
        self, input_path: Path, filters_path: Path
    ) -> int:
        """Read CVR data, apply filters, derive domains, push one job per domain.

        Returns the number of jobs created.

        Backward-compatible wrapper around extract_prospect_domains +
        create_scan_jobs_for_domains.
        """
        domains = self.extract_prospect_domains(input_path, filters_path)
        if not domains:
            return 0
        return self.create_scan_jobs_for_domains(domains)

    def create_enrichment_jobs(
        self,
        domains: list[str],
        num_workers: int = ENRICHMENT_WORKERS,
        stagger_seconds: int = ENRICHMENT_STAGGER_SECONDS,
    ) -> int:
        """Split domains into batches and push enrichment jobs to the enrichment queue.

        Domains are distributed round-robin across *num_workers* batches.
        Each batch gets a stagger delay of ``batch_index * stagger_seconds``
        to avoid API rate-limit collisions.

        Returns the number of enrichment jobs created.
        """
        if not domains:
            logger.info("No domains for enrichment — 0 jobs created")
            return 0

        # Cap workers to number of domains
        actual_workers = min(num_workers, len(domains))

        # Round-robin domain distribution
        batches: list[list[str]] = [[] for _ in range(actual_workers)]
        for i, domain in enumerate(domains):
            batches[i % actual_workers].append(domain)

        # Reset Redis counters
        self._conn.set(ENRICHMENT_COUNTER_KEY, 0)
        self._conn.set(ENRICHMENT_TOTAL_KEY, actual_workers)

        # Push enrichment jobs
        for batch_index, batch_domains in enumerate(batches):
            job = _build_enrichment_job(
                domains=batch_domains,
                batch_index=batch_index,
                total_batches=actual_workers,
                stagger_delay=batch_index * stagger_seconds,
            )
            self._conn.lpush(ENRICHMENT_QUEUE, json.dumps(job))

        logger.info(
            "Created {} enrichment jobs ({} domains, stagger={}s)",
            actual_workers,
            len(domains),
            stagger_seconds,
        )
        return actual_workers

    def wait_for_enrichment(
        self, timeout: int = 3600, poll_interval: int = 5
    ) -> bool:
        """Poll Redis until all enrichment batches have completed.

        Returns True when all batches complete, False on timeout.
        """
        deadline = time.monotonic() + timeout
        total = int(self._conn.get(ENRICHMENT_TOTAL_KEY) or 0)

        if total == 0:
            logger.warning("Enrichment total is 0 — nothing to wait for")
            return True

        logger.info("Waiting for {} enrichment batches (timeout={}s)", total, timeout)

        while time.monotonic() < deadline:
            completed = int(self._conn.get(ENRICHMENT_COUNTER_KEY) or 0)
            if completed >= total:
                logger.info(
                    "All {} enrichment batches completed", total
                )
                return True
            time.sleep(poll_interval)

        completed = int(self._conn.get(ENRICHMENT_COUNTER_KEY) or 0)
        logger.warning(
            "Enrichment timeout after {}s: {}/{} batches completed",
            timeout,
            completed,
            total,
        )
        return False

    def create_client_jobs(self, client_dir: Path, tier: str) -> int:
        """Read client profiles from *client_dir*, create scan jobs per domain.

        Each client profile is a JSON file containing at minimum:
        ``{"client_id": "...", "domains": ["..."], "tier": "...", "level": ...}``

        Returns the number of jobs created.
        """
        if not client_dir.is_dir():
            logger.warning("Client directory {} does not exist", client_dir)
            return 0

        profiles = sorted(client_dir.glob("*.json"))
        if not profiles:
            logger.info("No client profiles in {}", client_dir)
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

        logger.info(
            "Created {} client jobs from {} profiles (tier filter: {})",
            count,
            len(profiles),
            tier,
        )
        return count

    def _push_job(self, job: dict[str, Any]) -> None:
        """LPUSH a JSON-serialised job to the scan queue."""
        self._conn.lpush(QUEUE_NAME, json.dumps(job))
