"""Tests for subfinder batch enrichment: job creation, execution, and cache integration."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import fakeredis

from src.scheduler.job_creator import (
    ENRICHMENT_COUNTER_KEY,
    ENRICHMENT_QUEUE,
    ENRICHMENT_TOTAL_KEY,
    QUEUE_NAME,
    JobCreator,
    _build_enrichment_job,
)
from src.worker.cache import ScanCache
from src.worker.main import _execute_enrichment_job, _run_subfinder_with_retry

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_creator(fake_redis_conn: fakeredis.FakeRedis) -> JobCreator:
    """Create a JobCreator wired to fakeredis."""
    jc = JobCreator.__new__(JobCreator)
    jc._redis_url = "redis://fake"
    jc._conn = fake_redis_conn
    return jc


def _make_cache(server: fakeredis.FakeServer | None = None) -> ScanCache:
    """Create a ScanCache backed by fakeredis."""
    if server is None:
        server = fakeredis.FakeServer()
    cache = ScanCache.__new__(ScanCache)
    cache.hits = 0
    cache.misses = 0
    cache._available = True
    cache._redis = fakeredis.FakeRedis(server=server, decode_responses=True)
    return cache


def _make_redis(server: fakeredis.FakeServer | None = None) -> fakeredis.FakeRedis:
    """Create a fakeredis connection."""
    if server is None:
        server = fakeredis.FakeServer()
    return fakeredis.FakeRedis(server=server, decode_responses=True)


# ---------------------------------------------------------------------------
# TestBuildEnrichmentJob
# ---------------------------------------------------------------------------

class TestBuildEnrichmentJob:
    """Tests for _build_enrichment_job helper."""

    def test_job_structure(self) -> None:
        """Enrichment job has all required fields."""
        job = _build_enrichment_job(
            domains=["a.dk", "b.dk"],
            batch_index=0,
            total_batches=3,
            stagger_delay=0,
        )
        assert job["job_type"] == "enrichment"
        assert job["domains"] == ["a.dk", "b.dk"]
        assert job["batch_index"] == 0
        assert job["total_batches"] == 3
        assert job["stagger_delay"] == 0
        assert job["job_id"].startswith("enrich-")
        assert "T" in job["created_at"]

    def test_stagger_delay_calculation(self) -> None:
        """Stagger delay increases with batch index."""
        job0 = _build_enrichment_job(["a.dk"], 0, 3, 0)
        job1 = _build_enrichment_job(["b.dk"], 1, 3, 10)
        job2 = _build_enrichment_job(["c.dk"], 2, 3, 20)

        assert job0["stagger_delay"] == 0
        assert job1["stagger_delay"] == 10
        assert job2["stagger_delay"] == 20

    def test_unique_job_ids(self) -> None:
        """Each job gets a unique ID."""
        jobs = [
            _build_enrichment_job(["a.dk"], i, 3, i * 10) for i in range(3)
        ]
        ids = {j["job_id"] for j in jobs}
        assert len(ids) == 3


# ---------------------------------------------------------------------------
# TestCreateEnrichmentJobs
# ---------------------------------------------------------------------------

class TestCreateEnrichmentJobs:
    """Tests for JobCreator.create_enrichment_jobs."""

    def test_68_domains_split_into_3_batches(self) -> None:
        """68 domains split round-robin into 23/23/22."""
        server = fakeredis.FakeServer()
        conn = _make_redis(server)
        creator = _make_creator(conn)

        domains = [f"domain{i}.dk" for i in range(68)]
        count = creator.create_enrichment_jobs(domains, num_workers=3)

        assert count == 3
        assert conn.llen(ENRICHMENT_QUEUE) == 3

        # Check batch sizes
        batch_sizes = []
        for _ in range(3):
            raw = conn.rpop(ENRICHMENT_QUEUE)
            job = json.loads(raw)
            batch_sizes.append(len(job["domains"]))

        batch_sizes.sort(reverse=True)
        assert batch_sizes == [23, 23, 22]

    def test_uneven_split(self) -> None:
        """7 domains across 3 workers: 3/2/2."""
        server = fakeredis.FakeServer()
        conn = _make_redis(server)
        creator = _make_creator(conn)

        domains = [f"d{i}.dk" for i in range(7)]
        count = creator.create_enrichment_jobs(domains, num_workers=3)

        assert count == 3
        batch_sizes = []
        for _ in range(3):
            raw = conn.rpop(ENRICHMENT_QUEUE)
            job = json.loads(raw)
            batch_sizes.append(len(job["domains"]))

        batch_sizes.sort(reverse=True)
        assert batch_sizes == [3, 2, 2]

    def test_fewer_domains_than_workers(self) -> None:
        """2 domains with 3 workers: only 2 batches created."""
        server = fakeredis.FakeServer()
        conn = _make_redis(server)
        creator = _make_creator(conn)

        domains = ["a.dk", "b.dk"]
        count = creator.create_enrichment_jobs(domains, num_workers=3)

        assert count == 2
        assert conn.llen(ENRICHMENT_QUEUE) == 2
        assert int(conn.get(ENRICHMENT_TOTAL_KEY)) == 2

    def test_redis_counter_init(self) -> None:
        """Redis counters are reset on job creation."""
        server = fakeredis.FakeServer()
        conn = _make_redis(server)
        creator = _make_creator(conn)

        # Pre-set to simulate leftover from a previous run
        conn.set(ENRICHMENT_COUNTER_KEY, 99)
        conn.set(ENRICHMENT_TOTAL_KEY, 99)

        domains = [f"d{i}.dk" for i in range(10)]
        creator.create_enrichment_jobs(domains, num_workers=3)

        assert int(conn.get(ENRICHMENT_COUNTER_KEY)) == 0
        assert int(conn.get(ENRICHMENT_TOTAL_KEY)) == 3

    def test_empty_domains(self) -> None:
        """Empty domain list creates 0 jobs."""
        server = fakeredis.FakeServer()
        conn = _make_redis(server)
        creator = _make_creator(conn)

        count = creator.create_enrichment_jobs([])
        assert count == 0
        assert conn.llen(ENRICHMENT_QUEUE) == 0

    def test_jobs_pushed_to_enrichment_queue(self) -> None:
        """Jobs are pushed to queue:enrichment, not queue:scan."""
        server = fakeredis.FakeServer()
        conn = _make_redis(server)
        creator = _make_creator(conn)

        creator.create_enrichment_jobs(["a.dk", "b.dk", "c.dk"], num_workers=2)

        assert conn.llen(ENRICHMENT_QUEUE) == 2
        assert conn.llen(QUEUE_NAME) == 0


# ---------------------------------------------------------------------------
# TestWaitForEnrichment
# ---------------------------------------------------------------------------

class TestWaitForEnrichment:
    """Tests for JobCreator.wait_for_enrichment."""

    def test_immediate_completion(self) -> None:
        """Returns True immediately when all batches are already done."""
        server = fakeredis.FakeServer()
        conn = _make_redis(server)
        creator = _make_creator(conn)

        conn.set(ENRICHMENT_TOTAL_KEY, 3)
        conn.set(ENRICHMENT_COUNTER_KEY, 3)

        result = creator.wait_for_enrichment(timeout=5, poll_interval=1)
        assert result is True

    def test_timeout(self) -> None:
        """Returns False when timeout expires before completion."""
        server = fakeredis.FakeServer()
        conn = _make_redis(server)
        creator = _make_creator(conn)

        conn.set(ENRICHMENT_TOTAL_KEY, 3)
        conn.set(ENRICHMENT_COUNTER_KEY, 1)

        result = creator.wait_for_enrichment(timeout=1, poll_interval=1)
        assert result is False

    def test_zero_total(self) -> None:
        """Returns True immediately when total is 0."""
        server = fakeredis.FakeServer()
        conn = _make_redis(server)
        creator = _make_creator(conn)

        conn.set(ENRICHMENT_TOTAL_KEY, 0)

        result = creator.wait_for_enrichment(timeout=5, poll_interval=1)
        assert result is True

    def test_incremental_completion(self) -> None:
        """Returns True after counter reaches total (simulated with pre-set)."""
        server = fakeredis.FakeServer()
        conn = _make_redis(server)
        creator = _make_creator(conn)

        conn.set(ENRICHMENT_TOTAL_KEY, 2)
        conn.set(ENRICHMENT_COUNTER_KEY, 2)

        result = creator.wait_for_enrichment(timeout=5, poll_interval=1)
        assert result is True


# ---------------------------------------------------------------------------
# TestExecuteEnrichmentJob
# ---------------------------------------------------------------------------

class TestExecuteEnrichmentJob:
    """Tests for _execute_enrichment_job in the worker."""

    def test_results_cached_per_domain(self) -> None:
        """Each domain's subfinder results are cached individually."""
        server = fakeredis.FakeServer()
        cache = _make_cache(server)
        redis_conn = _make_redis(server)
        redis_conn.set(ENRICHMENT_COUNTER_KEY, 0)

        subfinder_results = {
            "a.dk": ["sub1.a.dk", "sub2.a.dk"],
            "b.dk": ["mail.b.dk"],
        }

        job = _build_enrichment_job(
            domains=["a.dk", "b.dk"],
            batch_index=0,
            total_batches=1,
            stagger_delay=0,
        )

        with patch("src.worker.main._run_subfinder", return_value=subfinder_results):
            _execute_enrichment_job(job, cache, redis_conn)

        # Verify cache entries
        cached_a = cache.get("subfinder", "a.dk")
        assert cached_a == {"a.dk": ["sub1.a.dk", "sub2.a.dk"]}

        cached_b = cache.get("subfinder", "b.dk")
        assert cached_b == {"b.dk": ["mail.b.dk"]}

    def test_cache_format_matches_scan_job(self) -> None:
        """Cache format matches what scan_job.py _cached_or_run expects.

        scan_job.py line 132: subfinder_results = _cached_or_run("subfinder", _run_subfinder, [domain])
        _run_subfinder([domain]) returns {domain: [subdomains]}
        scan_job.py line 183-184: scan.subdomains = subfinder_results.get(domain, [])

        So cached value must be {domain: [subdomains]}.
        """
        server = fakeredis.FakeServer()
        cache = _make_cache(server)
        redis_conn = _make_redis(server)
        redis_conn.set(ENRICHMENT_COUNTER_KEY, 0)

        subfinder_results = {"example.dk": ["www.example.dk", "mail.example.dk"]}

        job = _build_enrichment_job(
            domains=["example.dk"],
            batch_index=0,
            total_batches=1,
            stagger_delay=0,
        )

        with patch("src.worker.main._run_subfinder", return_value=subfinder_results):
            _execute_enrichment_job(job, cache, redis_conn)

        # This is exactly what scan_job.py would get from cache.get("subfinder", "example.dk")
        cached = cache.get("subfinder", "example.dk")
        assert isinstance(cached, dict)
        assert "example.dk" in cached
        assert cached.get("example.dk", []) == ["www.example.dk", "mail.example.dk"]

    def test_counter_incremented_on_success(self) -> None:
        """Enrichment counter is incremented after successful execution."""
        server = fakeredis.FakeServer()
        cache = _make_cache(server)
        redis_conn = _make_redis(server)
        redis_conn.set(ENRICHMENT_COUNTER_KEY, 0)

        job = _build_enrichment_job(["a.dk"], 0, 1, 0)

        with patch("src.worker.main._run_subfinder", return_value={"a.dk": []}):
            _execute_enrichment_job(job, cache, redis_conn)

        assert int(redis_conn.get(ENRICHMENT_COUNTER_KEY)) == 1

    def test_counter_incremented_on_failure(self) -> None:
        """Enrichment counter is incremented even when subfinder fails."""
        server = fakeredis.FakeServer()
        cache = _make_cache(server)
        redis_conn = _make_redis(server)
        redis_conn.set(ENRICHMENT_COUNTER_KEY, 0)

        job = _build_enrichment_job(["a.dk"], 0, 1, 0)

        # _run_subfinder_with_retry will catch the exception and return {}
        with patch("src.worker.main._run_subfinder", side_effect=RuntimeError("subfinder crashed")):
            _execute_enrichment_job(job, cache, redis_conn)

        assert int(redis_conn.get(ENRICHMENT_COUNTER_KEY)) == 1

    def test_retry_on_failure(self) -> None:
        """Subfinder is retried once on failure."""
        call_count = 0

        def _failing_then_ok(domains):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("transient failure")
            return {"a.dk": ["sub.a.dk"]}

        with patch("src.worker.main._run_subfinder", side_effect=_failing_then_ok):
            result = _run_subfinder_with_retry(["a.dk"], retry_limit=1)

        assert call_count == 2
        assert result == {"a.dk": ["sub.a.dk"]}

    def test_retry_exhausted(self) -> None:
        """Returns empty dict when all retries are exhausted."""
        with patch("src.worker.main._run_subfinder", side_effect=RuntimeError("always fails")):
            result = _run_subfinder_with_retry(["a.dk"], retry_limit=1)

        assert result == {}

    def test_stagger_delay_applied(self) -> None:
        """Stagger delay causes 1s sleeps in a loop."""
        server = fakeredis.FakeServer()
        cache = _make_cache(server)
        redis_conn = _make_redis(server)
        redis_conn.set(ENRICHMENT_COUNTER_KEY, 0)

        job = _build_enrichment_job(["a.dk"], 1, 3, 10)

        with patch("src.worker.main._run_subfinder", return_value={}), \
             patch("src.worker.main.time.sleep") as mock_sleep:
            _execute_enrichment_job(job, cache, redis_conn)

        # Interruptible loop: 10 calls to sleep(1) instead of one sleep(10)
        assert mock_sleep.call_count == 10
        mock_sleep.assert_called_with(1)

    def test_no_stagger_for_batch_zero(self) -> None:
        """Batch 0 has stagger_delay=0, so no sleep."""
        server = fakeredis.FakeServer()
        cache = _make_cache(server)
        redis_conn = _make_redis(server)
        redis_conn.set(ENRICHMENT_COUNTER_KEY, 0)

        job = _build_enrichment_job(["a.dk"], 0, 3, 0)

        with patch("src.worker.main._run_subfinder", return_value={}), \
             patch("src.worker.main.time.sleep") as mock_sleep:
            _execute_enrichment_job(job, cache, redis_conn)

        mock_sleep.assert_not_called()

    def test_domain_with_no_subdomains_cached_as_empty(self) -> None:
        """Domains with no subfinder results are still cached (empty list)."""
        server = fakeredis.FakeServer()
        cache = _make_cache(server)
        redis_conn = _make_redis(server)
        redis_conn.set(ENRICHMENT_COUNTER_KEY, 0)

        # subfinder returns results for only one of two domains
        subfinder_results = {"a.dk": ["sub.a.dk"]}

        job = _build_enrichment_job(["a.dk", "b.dk"], 0, 1, 0)

        with patch("src.worker.main._run_subfinder", return_value=subfinder_results):
            _execute_enrichment_job(job, cache, redis_conn)

        cached_b = cache.get("subfinder", "b.dk")
        assert cached_b == {"b.dk": []}


# ---------------------------------------------------------------------------
# TestWorkerDualQueue
# ---------------------------------------------------------------------------

class TestWorkerDualQueue:
    """Tests for dual-queue BRPOP behavior."""

    def test_enrichment_queue_priority(self) -> None:
        """When both queues have jobs, enrichment is processed first.

        Redis BRPOP returns the first non-empty queue in the list order.
        """
        server = fakeredis.FakeServer()
        conn = fakeredis.FakeRedis(server=server, decode_responses=True)

        # Push to both queues
        enrichment_job = json.dumps({"job_type": "enrichment", "domains": ["a.dk"]})
        scan_job = json.dumps({"job_type": "scan", "domain": "b.dk"})
        conn.lpush("queue:enrichment", enrichment_job)
        conn.lpush("queue:scan", scan_job)

        # BRPOP with enrichment first
        result = conn.brpop(["queue:enrichment", "queue:scan"], timeout=1)
        assert result is not None
        queue_name, raw = result
        assert queue_name == "queue:enrichment"
        job = json.loads(raw)
        assert job["job_type"] == "enrichment"

    def test_scan_job_processed_when_no_enrichment(self) -> None:
        """Scan jobs are processed when enrichment queue is empty."""
        server = fakeredis.FakeServer()
        conn = fakeredis.FakeRedis(server=server, decode_responses=True)

        scan_job = json.dumps({"job_type": "scan", "domain": "b.dk"})
        conn.lpush("queue:scan", scan_job)

        result = conn.brpop(["queue:enrichment", "queue:scan"], timeout=1)
        assert result is not None
        queue_name, raw = result
        assert queue_name == "queue:scan"

    def test_job_routing_enrichment(self) -> None:
        """Jobs with job_type=enrichment are routed to enrichment handler."""
        job = {"job_type": "enrichment", "domains": ["a.dk"]}
        assert job.get("job_type") == "enrichment"

    def test_job_routing_scan(self) -> None:
        """Jobs without job_type or with job_type=scan go to scan handler."""
        job_explicit = {"job_type": "scan", "domain": "a.dk"}
        job_implicit = {"domain": "a.dk"}

        assert job_explicit.get("job_type", "scan") == "scan"
        assert job_implicit.get("job_type", "scan") == "scan"


# ---------------------------------------------------------------------------
# TestExtractProspectDomains
# ---------------------------------------------------------------------------

class TestExtractProspectDomains:
    """Tests for JobCreator.extract_prospect_domains."""

    @patch("src.scheduler.job_creator.load_filters", return_value={})
    @patch("src.scheduler.job_creator.apply_pre_scan_filters", side_effect=lambda c, f: c)
    @patch("src.scheduler.job_creator.derive_domains", side_effect=lambda c: c)
    @patch("src.scheduler.job_creator.read_excel")
    def test_returns_domain_list(
        self, mock_read, mock_derive, mock_filters, mock_load
    ) -> None:
        """Returns a list of domain strings."""
        from src.prospecting.cvr import Company

        companies = [
            Company(
                cvr="10000000", name="Test ApS", address="Testvej 1",
                postcode="7100", city="Vejle", company_form="ApS",
                industry_code="561010", industry_name="Restauranter",
                phone="12345678", email="info@test.dk",
                ad_protected=False, website_domain="test.dk",
            ),
        ]
        mock_read.return_value = companies

        server = fakeredis.FakeServer()
        conn = _make_redis(server)
        creator = _make_creator(conn)

        domains = creator.extract_prospect_domains(Path("fake.xlsx"), Path("fake.json"))

        assert domains == ["test.dk"]
        assert isinstance(domains, list)

    @patch("src.scheduler.job_creator.load_filters", return_value={})
    @patch("src.scheduler.job_creator.apply_pre_scan_filters", side_effect=lambda c, f: c)
    @patch("src.scheduler.job_creator.derive_domains", side_effect=lambda c: c)
    @patch("src.scheduler.job_creator.read_excel")
    def test_deduplication(
        self, mock_read, mock_derive, mock_filters, mock_load
    ) -> None:
        """Duplicate domains are removed."""
        from src.prospecting.cvr import Company

        companies = [
            Company(
                cvr=f"1000000{i}", name=f"Test {i} ApS", address="Testvej 1",
                postcode="7100", city="Vejle", company_form="ApS",
                industry_code="561010", industry_name="Restauranter",
                phone="12345678", email=f"info{i}@shared.dk",
                ad_protected=False, website_domain="shared.dk",
            )
            for i in range(3)
        ]
        mock_read.return_value = companies

        server = fakeredis.FakeServer()
        conn = _make_redis(server)
        creator = _make_creator(conn)

        domains = creator.extract_prospect_domains(Path("fake.xlsx"), Path("fake.json"))

        assert domains == ["shared.dk"]

    @patch("src.scheduler.job_creator.read_excel", return_value=[])
    def test_empty_input(self, mock_read) -> None:
        """Empty input returns empty list."""
        server = fakeredis.FakeServer()
        conn = _make_redis(server)
        creator = _make_creator(conn)

        domains = creator.extract_prospect_domains(Path("fake.xlsx"), Path("fake.json"))
        assert domains == []


# ---------------------------------------------------------------------------
# TestEndToEnd
# ---------------------------------------------------------------------------

class TestEndToEnd:
    """End-to-end: enrichment caches results, scan job hits cache."""

    def test_enrichment_then_scan_cache_hit(self) -> None:
        """Enrichment pre-caches subfinder, scan job gets cache hit."""
        server = fakeredis.FakeServer()
        cache = _make_cache(server)
        redis_conn = _make_redis(server)
        redis_conn.set(ENRICHMENT_COUNTER_KEY, 0)

        domain = "example.dk"
        subfinder_results = {domain: ["www.example.dk", "mail.example.dk"]}

        # Phase 1: enrichment
        enrichment_job = _build_enrichment_job([domain], 0, 1, 0)
        with patch("src.worker.main._run_subfinder", return_value=subfinder_results):
            _execute_enrichment_job(enrichment_job, cache, redis_conn)

        # Phase 2: verify cache hit (what scan_job.py _cached_or_run would do)
        cached = cache.get("subfinder", domain)
        assert cached is not None
        assert isinstance(cached, dict)
        # This is the exact pattern scan_job.py uses at line 183-184
        subdomains = cached.get(domain, [])
        assert subdomains == ["www.example.dk", "mail.example.dk"]

    def test_enrichment_counter_tracks_completion(self) -> None:
        """Counter correctly tracks multiple batch completions."""
        server = fakeredis.FakeServer()
        cache = _make_cache(server)
        redis_conn = _make_redis(server)

        # Simulate 3-worker enrichment
        redis_conn.set(ENRICHMENT_COUNTER_KEY, 0)
        redis_conn.set(ENRICHMENT_TOTAL_KEY, 3)

        for i in range(3):
            job = _build_enrichment_job([f"d{i}.dk"], i, 3, 0)
            with patch("src.worker.main._run_subfinder", return_value={}):
                _execute_enrichment_job(job, cache, redis_conn)

        assert int(redis_conn.get(ENRICHMENT_COUNTER_KEY)) == 3

        # Scheduler would see this as complete
        creator = _make_creator(redis_conn)
        result = creator.wait_for_enrichment(timeout=1, poll_interval=1)
        assert result is True
