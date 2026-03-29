# Backlog

Organised by sprint. Each sprint is broken into **increments** — self-contained deliverables that ship with tests, benchmarks, and logs. Nothing ships without meeting its Definition of Done.

Status: `[ ]` pending · `[~]` in progress · `[x]` done

### Quality gates (apply to every increment)

Every increment must satisfy:
- **Tests:** automated tests pass, covering the delivered functionality
- **Performance:** benchmarks measured and recorded, targets met
- **Logs:** structured logging in place, observable in production

---

## Sprint 1 — Consolidate & Ship [COMPLETE]

Merged to main. 153 tests, structured logging, benchmarks, README, .env.example.

### Increment 1.1 — Test foundation

Set up the testing framework and write tests for existing code.

| Item | Description |
|------|-------------|
| pytest + conftest | Set up pytest, conftest.py with fixtures (mock Redis, mock HTTP responses, sample Company/ScanResult objects) |
| Unit tests: scanner functions | Test each scan function (_check_ssl, _get_response_headers, _extract_page_meta, _run_httpx, etc.) with mocked HTTP responses |
| Unit tests: brief_generator | Test findings generation, GDPR determination, severity assignment |
| Unit tests: bucketer | Test bucket classification for each CMS/platform type |
| Unit tests: filters | Test pre-scan and post-scan filter logic, empty-list edge case |
| Unit tests: config loader | Test JSON config loading, missing file handling |
| Integration test: mini pipeline | Test full pipeline with 3 mocked domains end-to-end (no real HTTP) |

**Definition of Done:**
- [ ] `pytest` runs from project root with zero failures
- [ ] Coverage report generated (`pytest --cov`), baseline recorded
- [ ] All scan functions have at least 1 test each
- [ ] Brief generator findings tested for each severity level
- [ ] CI-ready: tests can run without network access (all HTTP mocked)

### Increment 1.2 — Logging foundation

Replace ad-hoc logging with structured, production-grade logging.

| Item | Description |
|------|-------------|
| Structured log format | JSON log output (timestamp, level, module, message, context) configurable via env var |
| Per-domain scan log | Each domain scan logs: domain, scan types executed, cache hits/misses, duration, finding count |
| Pipeline run log | Full run summary: total domains, scanned, skipped, duration, errors, findings breakdown |
| Log levels | DEBUG: HTTP responses, tool output. INFO: domain progress, stage completion. WARNING: timeouts, rate limits. ERROR: failures, Valdí blocks. |

**Definition of Done:**
- [ ] `--log-format json` flag produces machine-readable JSON logs
- [ ] Every scan function logs its duration
- [ ] Pipeline run produces a single summary line with: domains scanned, duration, findings count, errors
- [ ] Log output does not contain API keys, client PII, or target response bodies

### Increment 1.3 — Performance baseline

Measure current performance and set targets.

| Item | Description |
|------|-------------|
| Benchmark script | `scripts/benchmark.py` — runs pipeline against N domains (configurable), records per-stage timing |
| Baseline measurement | Run against 5, 20, 50 domains (small, medium, large). Record: total time, per-stage time, per-domain average |
| Performance targets | Define targets for Docker architecture: <30s per domain, <5min for 50 domains, <30min for 1000 domains |
| Regression detection | Benchmark results saved to `data/benchmarks/`. Compare across runs. |

**Definition of Done:**
- [ ] `python scripts/benchmark.py --domains 5` completes and produces timing report
- [ ] Baseline numbers recorded for 5/20/50 domains
- [ ] Per-stage timing breakdown available (resolver, httpx, webanalyze, subfinder, crt.sh, dnsx, per-domain, brief generation)
- [ ] Performance targets documented in architecture doc

### Increment 1.4 — Merge & housekeeping

| Item | Description |
|------|-------------|
| Clean git history | Squash or rebase to remove revert commit noise |
| Merge to main | PR with summary of all changes |
| README.md | Update with new structure, run instructions, test instructions |
| .env.example | Document all env vars |

**Definition of Done:**
- [ ] `feature/siri-pivot` merged to `main`
- [ ] `README.md` has current project structure, run command, test command
- [ ] `.env.example` exists with all env vars documented
- [ ] `pytest` passes on `main`

---

## Sprint 2 — Docker Architecture (Pi5) [COMPLETE]

Production scanning infrastructure deployed on Pi5. Architecture: `docs/architecture/pi5-docker-architecture.md`.

**Results:** 204 domains in 8.5 min (9x improvement over sequential). Subfinder batch enrichment, local CT database, observability stack (Prometheus + Grafana + Dozzle). 217 tests. API deferred to Sprint 3.

### Increment 2.1 — Redis cache layer

Build the caching layer that workers will use. Test it standalone before building the worker.

| Item | Description |
|------|-------------|
| `src/worker/cache.py` | Redis cache check/store with configurable TTL per scan type |
| Cache key schema | `cache:{scan_type}:{domain}` with TTLs from config |
| Unit tests | Test cache hit, cache miss, cache expired, Redis down (graceful fallback) |
| Benchmark | Measure: cache write time, cache read time, serialization overhead |

**Definition of Done:**
- [ ] `cache.py` works with a real Redis instance (docker run redis)
- [ ] Unit tests pass with mocked Redis (fakeredis)
- [ ] Cache hit returns result without calling scan function
- [ ] Cache miss calls scan function and stores result
- [ ] Graceful fallback: if Redis is down, scan runs without cache (logs warning)
- [ ] Benchmark: cache read < 5ms, cache write < 10ms

### Increment 2.2 — Worker: single-domain scan job

Build the worker that executes one domain scan from a Redis job.

| Item | Description |
|------|-------------|
| `src/worker/scan_job.py` | Execute all scan types for one domain, using cache layer |
| `src/worker/main.py` | BRPOP loop, Valdí validation on startup, graceful shutdown |
| Logging | Per-domain: scan types run, cache hits, duration, findings count. JSON structured. |
| Unit tests | Test scan_job with mocked scan functions + mocked Redis |
| Integration test | Test worker against 1 real domain (conrads.dk) — verify same results as current pipeline |
| Benchmark | Single-domain scan time: cold cache vs warm cache |

**Definition of Done:**
- [ ] Worker starts, validates Valdí, waits for jobs
- [ ] Worker processes a domain and produces identical ScanResult to current pipeline
- [ ] Cache-warm rescan of same domain completes in < 2s
- [ ] Worker logs every scan type duration, cache hit/miss, total domain time
- [ ] Worker handles: Redis down, scan function timeout, malformed job
- [ ] Benchmark recorded: cold scan time, warm scan time, per-scan-type breakdown

### Increment 2.3 — Scheduler

Build the scheduler that creates scan jobs.

| Item | Description |
|------|-------------|
| `src/scheduler/main.py` | APScheduler, reads client configs, creates jobs per tier schedule |
| `src/scheduler/job_creator.py` | Reads CVR data or client list, applies filters, pushes jobs to Redis |
| Logging | Jobs created count, next scheduled run, errors |
| Unit tests | Test job creation for each tier schedule |

**Definition of Done:**
- [ ] Scheduler creates correct jobs for Watchman (weekly), Sentinel (daily), Guardian (daily)
- [ ] Prospecting mode: reads CVR data, applies filters, creates one job per domain
- [ ] Jobs appear in Redis queue with correct structure
- [ ] Scheduler logs: jobs created, next run time, any errors
- [ ] Unit tests cover: empty client list, invalid client config, Redis down

### Increment 2.4 — Docker containers

Package everything into containers. Validate on local Docker, then Pi5.

| Item | Description |
|------|-------------|
| Dockerfile.worker | Python 3.11 + Go tools (httpx, subfinder, dnsx, webanalyze) |
| Dockerfile.scheduler | Python 3.11, lightweight |
| Dockerfile.api | Python 3.11 + FastAPI (placeholder) |
| docker-compose up | Full stack runs locally |
| Logging | All containers log to stdout in JSON format (Docker collects) |
| Integration test | docker-compose up → scheduler creates jobs → workers process → results appear in /data/results |
| Benchmark | 50-domain run on Docker: total time, per-domain average, cache effectiveness |

**Definition of Done:**
- [ ] `docker compose up` starts all services, health checks pass
- [ ] Worker containers find and execute Go CLI tools (httpx, subfinder, etc.)
- [ ] 50-domain prospecting run completes in < 10 minutes
- [ ] Results appear in `/data/results/` volume
- [ ] All container logs are JSON-structured, collected by `docker compose logs`
- [ ] Benchmark: 50 domains cold < 10min, 50 domains warm < 2min

### Increment 2.5 — Full Vejle run [DONE] + API [MOVED TO SPRINT 3]

| Item | Status |
|------|--------|
| Full Vejle run | **Done** — 204 domains, 203 completed, 8.5 min total |
| Performance report | **Done** — GitHub issue #5, architecture doc updated |
| Subfinder batch enrichment | **Done** — 3 batches, 5.5 min, 100% cache hit |
| Local CT database | **Done** — ct-collector running, SQLite WAL mode |
| Observability | **Done** — Prometheus + Grafana + Dozzle + Docker metrics |
| `src/api/main.py` | **Moved** — first task of Sprint 3 |

**Vejle run results:**
- 204 domains, 203 completed, 1 skipped (robots.txt), 0 failed
- 8.5 min total (enrichment 5.5 min + scan 3 min), warm cache 3 min
- 974 findings (33 critical, 1 high, 245 medium, 618 low, 77 info)
- 100% cache hit rate (1827 hits, 0 misses)

---

## Sprint 3 — Level 1 Pipeline (Consent-Gated Scanning) [NEXT]

Build the paid-service scanning pipeline. Requires written client consent (Level 1).

### Increment 3.0 — Results API (moved from Sprint 2)

| Item | Description |
|------|-------------|
| `src/api/main.py` | FastAPI: `/health`, `/results/{domain}`, scan-complete pub/sub listener |
| Logging | API request logs, scan-complete event logs |
| Tests | Health endpoint, result retrieval, missing domain |

**Definition of Done:**
- [x] API health endpoint responds
- [x] API serves scan results as JSON
- [x] Unit tests with mocked results
- [x] Logs: request latency, errors

### Increment 3.1 — Consent management + Valdí Level 1

| Item | Description |
|------|-------------|
| Client authorization template | Legal document for client signature |
| Consent registry | `.claude/agents/valdi/consent/{client_id}.json` with scope, dates, signatures |
| Valdí Gate 2 for Level 1 | Verify consent exists and is current before Level 1 scan |
| Tests | Test consent validation: valid, expired, wrong scope, missing |

**Definition of Done:**
- [x] Consent registry schema documented
- [x] Valdí blocks Level 1 scans for clients without valid consent
- [x] Unit tests cover all consent edge cases
- [x] Logs: consent check result per client per scan

### Increment 3.2 — Level 1 scan types

| Item | Description |
|------|-------------|
| WPScan integration | WordPress vulnerability scanning (requires commercial API) |
| CMSeek integration | CMS admin panel detection |
| Nuclei integration | Template-based vulnerability scanning |
| Valdí Gate 1 approvals | Approval tokens + forensic logs for each Level 1 tool |
| Tests | Test each tool with mocked output |
| Benchmark | Level 1 scan time per domain (additional over Level 0) |

**Definition of Done:**
- [ ] Each Level 1 tool has Valdí approval token with function hash
- [ ] Workers execute Level 1 tools only when job.level == 1 and consent is valid
- [ ] Unit tests for each tool with mocked responses
- [ ] Benchmark: Level 1 adds < 60s per domain over Level 0
- [ ] Forensic logs written for every Level 1 scan execution

### Increment 3.3 — Finding Interpreter + Message Composer

| Item | Description |
|------|-------------|
| Finding Interpreter | Claude API translates raw findings to plain Danish |
| Message Composer | Format for Telegram (4096 char limit, markdown) |
| Tests | Test interpretation with sample findings, test message formatting |
| Benchmark | Claude API latency per finding batch |

**Definition of Done:**
- [x] Interpreter produces Danish plain-language explanations for all finding types
- [x] Messages fit Telegram limits, render correctly in markdown
- [x] Unit tests with mocked Claude API responses
- [x] Benchmark: interpretation latency < 5s per client brief
- [x] Logs: API call duration, token usage, interpretation confidence

### Increment 3.4 — Client Memory + Remediation workflow

| Item | Description |
|------|-------------|
| Client Memory agent | Per-client state, scan history, remediation tracking |
| Delta detection | Compare current scan to previous — only notify on changes |
| Remediation workflow | Per-event request, tracking, verification |
| Tests | Test delta detection, remediation state transitions |

**Definition of Done:**
- [ ] Client profile stores scan history, last notification, remediation state
- [ ] Delta detection correctly identifies: new finding, resolved finding, unchanged
- [ ] Remediation workflow: request → in-progress → completed → verified
- [ ] Unit tests for all state transitions
- [ ] Logs: delta summary per client, remediation state changes

---

## Sprint 4 — Pilot Launch (Vejle, 5 clients)

First paying clients. Human-in-the-loop for every message.

### Increment 4.1 — Telegram delivery

| Item | Description |
|------|-------------|
| Telegram bot setup | Bot token, webhook or polling |
| Message delivery | Send formatted findings to client Telegram |
| Human-in-the-loop | Federico reviews and approves every message before send |
| Tests | Test message delivery with Telegram test bot |
| Logs | Delivery status per message: sent, delivered, read |

**Definition of Done:**
- [ ] Bot sends test message to Federico's Telegram
- [ ] Human approval workflow: message queued → Federico reviews → approve/edit → send
- [ ] Message formatting renders correctly on mobile
- [ ] Delivery logs: timestamp, client, message ID, status
- [ ] Error handling: Telegram API down, message too long, rate limited

### Increment 4.2 — Client onboarding + first scans

| Item | Description |
|------|-------------|
| Onboarding flow | Add client to system, configure domains, set tier, Telegram setup |
| First 5 clients | Real Vejle businesses, real scans, real messages |
| Performance monitoring | Dashboard or log analysis: scan times, delivery times, error rates |

**Definition of Done:**
- [ ] 5 clients onboarded with profiles in `/data/clients/`
- [ ] Weekly Watchman scans running on schedule
- [ ] Clients receive findings via Telegram
- [ ] Performance: scan + interpret + deliver < 5 min per client
- [ ] Zero Valdí violations across all client scans
- [ ] Client feedback collected on message clarity

### Increment 4.3 — SIRI submission (soft dependency — never blocks product)

SIRI submission runs on its own timeline. Product roadmap continues regardless.

| Item | Description |
|------|-------------|
| SIRI application final | Update with available data — does not wait for pilot completion |
| Video pitch | Record 5-min video |
| Submit | Application + video + supporting documents |

**Definition of Done:**
- [ ] Application updated with strongest available evidence
- [ ] Video recorded, reviewed, under 5 minutes
- [ ] Application submitted on startupdenmark.info
- [ ] Receipt confirmed

---

## Sprint 4+ — Housekeeping

| Item | Description |
|------|-------------|
| Professional indemnity insurance | Required before commercial scanning |
| Legal counsel engagement | §263 confirmation, authorization template review |
| Domain + landing page | Public presence for sales conversations |
| Escalating follow-up system | Week 1/2/3 reminder logic |

---

## Observability [MERGED TO MAIN]

Two goals:
1. **Real-time run monitoring** — watch Heimdall scan in progress (live logs, active workers, queue depth, domains/min)
2. **Post-run analytics** — analyze metrics to improve performance and detect bottlenecks (scan type durations, cache effectiveness, error rates, per-domain timing trends)

### Done
- [x] Dozzle — real-time log viewer (port 8080)
- [x] Prometheus + Grafana — Docker engine metrics (cAdvisor removed — incompatible with Pi OS)
- [x] Docker built-in Prometheus metrics endpoint (:9323)
- [x] Prometheus retention: 30 days / 2GB
- [x] `scripts/analyze_results.py` — post-run scan analysis
- [x] `scripts/watch_and_analyze.py` — auto-analyze when queue drains

### Next
- [ ] Custom Prometheus metrics in worker — jobs completed, domains scanned, findings by severity, cache hit rate, scan duration histograms (`prometheus_client` Python package)
- [ ] Real-time run dashboard in Grafana — queue depth, active jobs, domains/min throughput, worker utilisation
- [ ] Post-run analytics dashboard in Grafana — per-scan-type duration trends, cache hit rate over time, slowest domains, error rate, subfinder/crt.sh bottleneck tracking
- [ ] Grafana Loki + Promtail — ingest structured JSON worker logs for log-based analytics (no code changes). For Docker, there's a native Loki Docker logging driver so containers ship logs directly. Grafana gives the Kibana-like dashboarding and query experience
- [ ] Redis exporter for Prometheus — expose queue length, cache key count, memory usage

---

## Parking Lot

Items with no sprint assignment yet.

- [ ] Agency detection improvements — better footer/meta parsing
- [ ] Agency pitch workflow — aggregate scan data per agency
- [ ] GrayHatWarfare premium subscription (~230 EUR/yr) — evaluate after pilot
- [ ] EU expansion research — Germany/Netherlands market sizing
- [ ] NCC-DK grant application (post-CVR, post Startup Denmark approval)
- [ ] Quarterly security report template (Guardian tier)
- [ ] Dashboard-vs-Telegram visual mockup for SIRI pitch deck
- [ ] Katana, FeroxBuster, SecretFinder, CloudEnum integration (Level 1 tools)
- [ ] Marketing sub-agent — translate technical findings to business-impact language
- [ ] Remote access to mobile console — Tailscale VPN or reverse proxy so the console is reachable from outside the home network (Pi Connect gives shell only, not HTTP). Critical for on-the-road monitoring and sales demos.
- [ ] Docker smoke test — container-level test that verifies Go binaries (httpx, webanalyze, subfinder, dnsx, nuclei) are executable after pip install. Catches dependency overwrites like the httpx binary incident.
