# Heimdall Project Plan

**Owner:** Project Coordinator Agent
**Last updated:** 2026-03-27
**Status tracker:** `data/project-state.json`

---

## Current state

Sprint 1 complete (merged to main). Sprint 2 code complete (cache, worker, scheduler, Dockerfiles). Pi5 validated and ready (18/18 checks pass). Awaiting first Docker build on Pi5 for Vejle run (Increment 2.5).

**153 tests passing.** Structured JSON logging. Benchmark script with mock mode.

**Next:** Deploy to Pi5 → full Vejle run → Sprint 3 (Level 1 scanning).

---

## Sprint 1 — Consolidate & Ship

**Target:** 2026-04-02
**Goal:** Establish quality foundations and merge to main.

```
Week 1 (parallel start):
├── 1.1 Test foundation        → pytest, unit tests, coverage baseline
├── 1.2 Logging foundation     → structured JSON logging, per-domain observability
└── 1.3 Performance baseline   → benchmark script, 5/20/50 domain measurements

Week 1 (after 1.1-1.3):
└── 1.4 Merge & housekeeping   → clean history, merge to main, README, .env.example
```

| Increment | Owner | Depends on | Deliverables |
|-----------|-------|------------|-------------|
| 1.1 Tests | Application Architect | — | pytest setup, unit tests for all scan functions, brief generator, bucketer, filters |
| 1.2 Logging | DevOps | — | JSON log format, per-domain scan log, pipeline run summary |
| 1.3 Benchmarks | Application Architect | 1.1 | Benchmark script, baseline for 5/20/50 domains, performance targets |
| 1.4 Merge | Project Coordinator | 1.1, 1.2, 1.3 | Clean feature branch merged to main |

**Exit criteria:** `pytest` passes on `main`, structured logs working, performance baseline recorded.

---

## Sprint 2 — Docker Architecture (Pi5)

**Target:** 2026-04-16
**Goal:** Production-ready scanning on Docker. Full Vejle run completes in < 30 minutes.

```
Week 1:
├── 2.1 Redis cache layer      → cache.py, TTL per scan type, tested with fakeredis
└── 2.2 Worker                 → scan_job.py, main.py, Valdí on startup, single-domain scan

Week 2:
├── 2.3 Scheduler              → APScheduler, client configs, job creation
├── 2.4 Docker containers      → Dockerfiles, docker compose up, 50-domain benchmark
└── 2.5 Full Vejle run + API   → 183+ domains, API health endpoint, performance report
```

| Increment | Owner | Depends on | Deliverables |
|-----------|-------|------------|-------------|
| 2.1 Cache | Application Architect | 1.4 | cache.py with TTL, unit tests, benchmark (read < 5ms, write < 10ms) |
| 2.2 Worker | Application Architect | 2.1 | Worker processes domain, identical results to current pipeline, warm rescan < 2s |
| 2.3 Scheduler | Application Architect | 2.1 | Creates jobs per tier schedule, tested for empty/invalid configs |
| 2.4 Docker | DevOps | 2.2, 2.3 | Compose stack runs, 50 domains cold < 10min, warm < 2min |
| 2.5 Vejle run | Prospecting | 2.4 | 183+ domains < 30min cold, < 10min warm, API serving results, zero Valdí violations |

**Exit criteria:** Full Vejle run on Docker, performance targets met, all containers logging in JSON.

---

## Sprint 3 — Level 1 Pipeline

**Target:** 2026-04-30
**Goal:** Consent-gated scanning for paying clients.

```
Week 1:
├── 3.1 Consent management     → authorization template, consent registry, Valdí Level 1
└── 3.2 Level 1 scan types     → WPScan, CMSeek, Nuclei, Valdí approvals

Week 2:
├── 3.3 Finding Interpreter    → Claude API translation, Message Composer, Telegram format
└── 3.4 Client Memory          → Per-client state, delta detection, remediation workflow
```

**Exit criteria:** Level 1 scan runs for a test client with consent, findings interpreted in Danish, message formatted for Telegram.

---

## Sprint 4 — Pilot Launch

**Target:** 2026-05-14
**Goal:** 5 paying clients in Vejle.

```
Week 1:
├── 4.1 Telegram delivery      → Bot setup, human-in-the-loop approval
└── 4.2 Client onboarding      → 5 real clients, real scans, real messages

Week 2:
└── 4.3 SIRI submission        → Final application, video pitch, submit
```

**Exit criteria:** 5 clients receiving weekly findings via Telegram. SIRI application submitted.

---

## Dependency chain

```
Sprint 1                    Sprint 2                       Sprint 3              Sprint 4
─────────                   ─────────                      ─────────             ─────────
1.1 Tests ──┐               2.1 Cache ─── 2.2 Worker ─┐   3.1 Consent ─┐       4.1 Telegram
1.2 Logging ┼─ 1.4 Merge ──┤                          ├── 2.4 Docker   │       4.2 Onboarding
1.3 Bench ──┘               2.3 Scheduler ─────────────┘       │        ├─ 3.3 Interpreter
                                                           2.5 Vejle    │       4.3 SIRI
                                                                │       │
                                                                └───────┼─ 3.2 Level 1 tools
                                                                        └─ 3.4 Client Memory
```

---

## Risk register

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| WPScan commercial license cost unknown | Medium | Medium | Contact Automattic early (Sprint 2). Fallback: skip WPScan, use Nuclei WordPress templates. |
| Pi5 resource constraints (8 GB RAM) | Low | High | Benchmarked: 3 workers fit in budget. Scale to VPS if needed. |
| crt.sh rate limiting at scale | High | Low | 7-day cache TTL. Subfinder provides overlapping subdomain data. crt.sh is enrichment, not critical. |
| SIRI application rejected | Low | Critical | Strong technical evidence (working product, real scan data). Video pitch rehearsed. |
| Solo founder — bus factor | High | High | All knowledge in SKILL.md files + documented architecture. Claude Code as force multiplier. Network security partner. |

---

## External deadlines

| Deadline | Date | Status | Action required |
|----------|------|--------|-----------------|
| Startup Denmark application | TBD | Drafting | Video pitch script needed. Submit after pilot data collected (Sprint 4). |
| NCC-DK grant | 2026-04-15 | Blocked | Requires CVR. Becomes actionable after SIRI approval. |

---

## Next actions (immediate)

1. Start Increment 1.1 — set up pytest, write unit tests for scan functions
2. Start Increment 1.2 — implement structured JSON logging
3. Start Increment 1.3 — create benchmark script, measure baseline
4. These three are independent — work in parallel
