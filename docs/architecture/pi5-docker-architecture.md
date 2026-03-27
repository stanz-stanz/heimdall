# Heimdall Pi5 Docker Architecture

## Overview

Heimdall runs on a Raspberry Pi 5 (8GB RAM, NVMe SSD) as a Docker Compose stack. The architecture separates concerns into containers coordinated through Redis.

```
Pi5 (Docker Compose)
├── heimdall-scheduler     # Two-phase: enrichment batches → scan jobs
├── heimdall-worker × 3    # Scan execution (dual-queue: enrichment + scan)
├── redis                  # Job queue + result cache
├── ct-collector           # CertStream subscriber → local SQLite CT database
├── heimdall-api           # Results API (for Telegram delivery)
├── dozzle                 # Live container log viewer (:8080)
├── prometheus             # Metrics collection (:9090)
├── grafana                # Dashboards (:3000)
└── volumes
    ├── /data/cache        # Tool-specific scan cache
    ├── /data/results      # Scan results per client
    ├── /data/ct           # CT certificate SQLite database (NVMe)
    └── /data/clients      # Client profiles, consent records
```

## Containers

### redis

Standard Redis instance. Two roles:

1. **Job queue** — scan jobs pushed by scheduler, pulled by workers (Redis lists with BRPOP for blocking wait)
2. **Result cache** — per-domain scan results with TTL. Workers check cache before scanning; if fresh, skip.

No persistence needed for the queue (jobs are recreated each schedule cycle). Cache uses RDB snapshots for persistence across restarts.

### heimdall-scheduler

Reads client configurations from `/data/clients/`. For each client, creates scan jobs based on their tier:

| Tier | Schedule | Scan types |
|------|----------|------------|
| Watchman | Weekly (Monday 06:00) | Layer 1 only |
| Sentinel | Daily (06:00) | Layer 1 only (Layer 2 when Level 1 pipeline is built) |
| Guardian | Daily (05:00) | Layer 1 + Layer 2 (with consent) |

Also handles the prospecting pipeline with a two-phase approach:

1. **Enrichment phase**: Extracts domains from CVR data, divides into 3 batches, pushes to `queue:enrichment`. Workers run `subfinder -dL` in batch mode (one subprocess for ~68 domains), cache results per-domain in Redis. Scheduler polls a Redis atomic counter until all batches complete.
2. **Scan phase**: Pushes 204 per-domain scan jobs to `queue:scan`. Workers get subfinder cache hits (~879ms/domain vs ~66s without).

Supports `--skip-enrichment` for subsequent runs with warm cache.

The scheduler is a lightweight Python process. It does no scanning — only creates jobs.

### heimdall-worker (× 3)

Pulls one domain job from Redis, executes all scan types for that domain, stores results. Each worker:

1. **Validates Valdí approvals on startup** — if any token is invalid, the worker refuses to start
2. **BRPOP on dual queue** — `["queue:enrichment", "queue:scan"]` (enrichment has priority)
3. **Enrichment jobs**: runs `subfinder -dL` in batch mode, caches results per-domain with format matching `_cached_or_run` expectations, increments Redis completion counter
4. **Scan jobs**: checks robots.txt (hard skip if denied), checks Redis cache for each scan type, runs scan types that need refreshing
5. **Assembles ScanResult** from fresh + cached data
6. **Generates findings** (severity/description/risk)
7. **Determines GDPR sensitivity** from scan evidence
8. **Queries local CT database** (SQLite, `immutable=1` mode) instead of remote crt.sh API (<5ms vs 1-32s)
9. **Stores result** in Redis cache (per-type TTL) and writes JSON to `/data/results/{client_id}/{domain}/{date}.json`
10. **Publishes scan-complete event** via Redis pub/sub

Workers are identical and stateless. Scale by changing `deploy.replicas` in docker-compose.yml. 3 workers on Pi5 uses 3 of 4 CPU cores. `stop_grace_period: 330s` allows enrichment jobs to complete before SIGKILL.

### heimdall-api

Reads scan results and generates client-facing output:

- Assembles per-client briefs from scan results
- Formats messages for Telegram delivery (via Message Composer logic)
- Exposes health check endpoint (`/health`)
- Listens for scan-complete events via Redis pub/sub to trigger delivery

Runs as a lightweight FastAPI or Flask process.

## Job Structure

```json
{
  "job_id": "scan-2026-03-27-001",
  "domain": "conrads.dk",
  "client_id": "cli-28616376",
  "tier": "watchman",
  "layer": 1,
  "level": 0,
  "scan_types": ["all"],
  "created_at": "2026-03-27T06:00:00Z"
}
```

Two queue types:
- **`queue:enrichment`** — batch subfinder jobs (3 jobs for 204 domains, one per worker)
- **`queue:scan`** — per-domain scan jobs (204 jobs)

Workers BRPOP with enrichment priority and a 30s timeout. Enrichment jobs are processed first; scan jobs only start after enrichment completes.

For prospecting (no client), `client_id` is `"prospect"` and results go to `/data/results/prospect/`.

## Caching Strategy

Workers check Redis cache before each scan type. If the cached result exists and hasn't expired, the worker uses it instead of running the scan.

| Key pattern | TTL | Rationale |
|-------------|-----|-----------|
| `cache:ssl:{domain}` | 24h | Certificates change on renewal (90 days for LE, but we want to catch imminent expiry) |
| `cache:headers:{domain}` | 24h | Headers change on server config updates |
| `cache:meta:{domain}` | 24h | Page content changes on CMS updates |
| `cache:httpx:{domain}` | 24h | Tech stack changes on deployments |
| `cache:webanalyze:{domain}` | 24h | Same as httpx |
| `cache:subfinder:{domain}` | 7d | Subdomains change rarely |
| `cache:crtsh:{domain}` | 7d | CT logs are append-only |
| `cache:dnsx:{domain}` | 24h | DNS records change on config updates |
| `cache:ghw:{domain}` | 7d | Exposed buckets change rarely |

**Impact:** On day 1, a 1,000-domain scan takes 30+ minutes. On day 2 (with 7d-TTL items cached), it takes ~10 minutes. On subsequent daily runs, only SSL/headers/meta/httpx/webanalyze/dnsx refresh (24h TTL) — subfinder, crt.sh, and GrayHatWarfare are served from cache.

## Resource Budget (Pi5 8GB)

| Component | RAM | CPU | Notes |
|-----------|-----|-----|-------|
| Redis | 512 MB | Shared | Maxmemory policy: allkeys-lru |
| Worker × 3 | 3 GB (1 GB each) | 3 cores | Go tools (httpx, subfinder) are memory-hungry |
| CT Collector | 256 MB | 0.25 core | CertStream WebSocket + SQLite writer |
| Scheduler | 256 MB | Shared | Lightweight, mostly sleeping |
| API | 256 MB | Shared | Lightweight, event-driven |
| Prometheus | 256 MB | Shared | 30-day / 2GB retention |
| Grafana | 256 MB | Shared | Dashboards |
| Dozzle | 128 MB | Shared | Live log viewer |
| Raspberry Pi OS | 1.5 GB | — | Base system + Docker daemon |
| **Buffer** | **1.5 GB** | — | Headroom for spikes |

### Throughput (measured, Vejle 204 domains)

| Phase | Duration | Per-domain |
|-------|----------|------------|
| Subfinder enrichment (cold) | 5.5 min | 3 parallel batches of 68 |
| Core scan (warm cache) | 3.0 min | 879ms avg |
| **Total (first run)** | **~8.5 min** | — |
| **Total (warm cache)** | **~3 min** | — |

Previous sequential approach: ~75 min for 204 domains (~66s/domain). **9x improvement.**

Cache hit rate on second run: 100% (1827 hits, 0 misses).

## Network

- **Outbound only** — no inbound ports except monitoring UIs. Connectivity via Tailscale VPN.
- Workers make HTTPS requests to target domains and third-party APIs (GrayHatWarfare).
- CT collector maintains persistent WebSocket to CertStream (`wss://certstream.calidog.io/`).
- API communicates with Telegram Bot API via HTTPS.
- Claude API called via HTTPS for finding interpretation.
- All inter-container traffic on Docker bridge network (never leaves the Pi).
- Monitoring ports: Dozzle (:8080), Grafana (:3000), Prometheus (:9090) — local network only.

## Scaling Path

| Scale | Architecture |
|-------|-------------|
| 5-50 clients | Pi5, 3 workers, Redis |
| 50-200 clients | Pi5, 3 workers, Redis, aggressive caching |
| 200-500 clients | VPS (4 vCPU, 8 GB), 6 workers, Redis |
| 500-1000 clients | VPS (8 vCPU, 16 GB), 12 workers, Redis |
| 1000+ clients | Multi-node: dedicated Redis server, multiple worker nodes |

The worker count is the only knob. Everything else scales linearly. The same docker-compose.yml works on Pi5 and VPS — only `deploy.replicas` changes.

## Valdí Compliance in Docker

- Workers validate approval tokens on startup (fail-fast if any token is invalid)
- Approval tokens mounted via `/data/valdi/approvals.json` volume
- Forensic logs written to `/data/valdi/logs/` volume
- Compliance checks written to `/data/valdi/compliance/` volume
- robots.txt check runs before every domain scan, regardless of cache
- No Level 1 scan types are registered in the approval file — workers cannot execute them
