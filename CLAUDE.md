<!-- CLAUDE.md v2.8 — Last updated: 2026-04-12 -->

# CLAUDE.md

MANDATORY: Before performing any task, determine which agent(s) from `.claude/agents/` own this task. Read their SKILL.md. Do not proceed without confirming you are operating within that agent's stated boundaries and responsibilities.

## Before Every Task
1. Identify which agent(s) this task falls under (see `.claude/agents/README.md`)
2. Read the relevant SKILL.md file(s)
3. If the task involves scanning, target selection, or client data — read `.claude/agents/valdi/SKILL.md` and `SCANNING_RULES.md` (project root), and verify compliance gates before proceeding
4. Confirm you are operating within that agent's boundaries

---

## Workflow Rules

### Plan Mode Default
- Enter plan mode for any non-trivial task (3+ steps or architectural decisions)
- If something goes sideways, STOP and re-plan immediately — don't keep pushing
- Use plan mode for verification steps, not just building
- Write detailed specs upfront to reduce ambiguity

### Verification Before Done
- Never mark a task complete without proving it works
- Diff behavior between main and your changes when relevant
- Ask yourself: "Would a staff engineer approve this?"
- Run tests, check logs, demonstrate correctness

### Demand Elegance (Balanced)
- For non-trivial changes: pause and ask "is there a more elegant way?"
- If a fix feels hacky: "knowing everything I know now, implement the elegant solution"
- Skip this for simple, obvious fixes — don't over-engineer
- Challenge your own work before presenting it

---

## What This Repository Is

Heimdall is an External Attack Surface Management (EASM) service for small businesses. It uses a Claude API agent (Anthropic SDK with tool use) to interpret findings in plain language and delivers results through Telegram. No client dashboard.

Business phase: **pre-pilot, blocked by SIRI approval.** Infrastructure runs as a Docker Compose stack on a Raspberry Pi 5 (NVMe SSD primary, microSD backup). Code is developed on the laptop and deployed to Pi5 via `git pull` + `heimdall-deploy` aliases (see `scripts/pi5-aliases.sh`).

---

## Document Hierarchy

When documents conflict, this is the precedence order:

| Priority | Document | Role |
|----------|----------|------|
| 1 | `SCANNING_RULES.md` (project root) | Authoritative source for what scanning actions are allowed or forbidden at each level. All other documents defer to it on scanning legality. |
| 2 | `.claude/agents/valdi/SKILL.md` (Valdí) | Enforces SCANNING_RULES.md. Defines the validation workflow, forensic logging, approval tokens, and consent registry. |
| 3 | This file (`CLAUDE.md`) | Orchestration and general project rules. Points to the above documents for scanning constraints — does not restate them. |
| 4 | `docs/briefing.md` | Business context, strategy, architecture. Single source of truth for non-scanning project details. |

If this file says something about scanning that contradicts `SCANNING_RULES.md`, follow `SCANNING_RULES.md`.

---

## Terminology

**Layer** describes the *type of activity*:
- **Layer 1 (Passive):** Reading publicly served information (HTTP headers, HTML source, DNS, SSL certs, tech fingerprinting). What a normal browser visit would produce.
- **Layer 2 (Active probing):** Sending crafted requests to test for specific vulnerabilities, probing paths not linked from public pages, port scanning.
- **Layer 3 (Exploitation):** Exploiting discovered vulnerabilities. Always blocked.

Without written consent, only Layer 1 activities are permitted. With written consent (Sentinel clients), Layer 1 and Layer 2 activities are permitted within the agreed scope.

The complete definition of what is allowed and forbidden at each Layer and consent state is in `SCANNING_RULES.md`. Do not rely on summaries elsewhere — read the source document.

---

## Key Documents

| File | Contents |
|------|----------|
| `docs/briefing.md` | **Primary context doc — read this first.** Architecture, pilot plan, go-to-market, legal framework, Danish policy context. Single source of truth for all business and technical details. |
| `SCANNING_RULES.md` | **Authoritative scanning constraint document.** What is allowed and forbidden at each Layer/Level. Read before writing or modifying any scanning code. |
| `.claude/agents/valdi/SKILL.md` | **Valdí — Legal Compliance Agent.** Enforces SCANNING_RULES.md. Validates scan types, manages consent registry, produces forensic logs. |
| `docs/legal/Heimdall_Legal_Risk_Assessment.md` | Danish legal analysis of scanning under Straffeloven §263. |
| `docs/legal/compliance-checklist.md` | Compliance checklist for scanning operations. |
| `.claude/agents/README.md` | Agent system overview, chain architecture, handoff protocols. |
| `docs/reference/incidents/` | Post-incident reports. Read before building any scanning functionality. |
| `docs/business/heimdall-siri-application.md` | **Startup Denmark (SIRI) application.** Business plan targeting the SIRI expert panel's four scoring criteria (Innovation, Market Potential, Scalability, Team). |
| `docs/business/siri-application-outline.md` | Outline and structure reference for the SIRI application. |
| `docs/decisions/log.md` | Decision log for project-level choices. |
| `docs/architecture/pi5-docker-architecture.md` | Pi5 Docker stack design: containers, queues, caching, resource budget, measured throughput. |
| `src/api/` | Results API + Operator Console — FastAPI service serving scan results, pub/sub listener, Svelte 5 SPA console at `/app` |
| `src/api/console.py` | Console API router — 8 REST endpoints (dashboard, pipeline, campaigns, prospects, clients, settings, commands, logs) + WebSocket `/console/ws` (live queue status, log streaming, command dispatch) + demo replay endpoints |
| `src/api/frontend/` | Svelte 5 SPA (Vite build). Views: Dashboard, Pipeline, Campaigns, Prospects, Clients, Logs, Settings. Build output: `src/api/static/dist/`. Dev: `npm run dev` (proxies to FastAPI at :8000). |
| `src/consent/validator.py` | Consent validator — Gate 2 enforcement, fail-closed on all error paths |
| `src/interpreter/` | Finding Interpreter — LLM-powered scan interpretation (Claude API / Ollama abstraction). Tier-aware: Watchman (trial) gets `title`, `severity`, `explanation`, `provenance` only; Sentinel adds `action` (fix instructions). No `who` field (removed — clients know who built their website). Telegram prompt: no plugin names in titles/explanations, GDPR sentence (flexible adaptation) for confirmed data findings only, calm tone for potential findings. |
| `src/composer/telegram.py` | Message Composer — Telegram HTML formatting with 🔴 Critical: / 🟠 High: severity labels, Confirmed/Potential sections, greeting, footer, 4096-char auto-splitting. Also `compose_celebration()` for fix acknowledgements. Provenance: binary `confirmed`/`unconfirmed` (source-agnostic). |
| `docs/digital-twin-use-cases.md` | Digital twin architecture, use cases, legal foundation |
| `config/synthetic_targets.json` | Config: synthetic target registry for twin consent bypass |
| `docs/legal/legal-briefing-outreach-2026-03-29.md` | Legal briefing for lawyer meeting — 16 questions on outreach (§10, Reklamebeskyttet), scanning (§263), consent, and GDPR |
| `docs/business/marketing-strategy-draft.md` | Marketing strategy draft — channels, legal constraints, outreach plan |
| `scripts/analyze_pipeline.py` | Pipeline analysis (`--deep` for full breakdown with outreach prioritization) |
| `scripts/audit.py` | Project audit — Dockerfile, compose, tests, configs, known gaps |
| `src/enrichment/` | CVR enrichment tool — 7-step pipeline: Excel ingestion → static enrichments → email domain extraction → name-match validation → search-based discovery → deduplication → summary. Outputs to `data/enriched/companies.db`. Run with `python -m src.enrichment`. Filtering happens at scan time in the scheduler, not here. |
| `src/vulndb/lookup.py` | WPVulnerability API client — free plugin/core CVE lookups with CVSS scores, replaces WPScan sidecar |
| `src/vulndb/wp_versions.py` | WordPress.org API client — checks installed plugin versions against latest release, 24h SQLite cache |
| `src/vulndb/rss_cve.py` | RSS CVE watch — polls Wordfence, CISA, Bleeping Computer feeds, regex-extracts CVE IDs into SQLite cache (12h TTL), enriches findings with "actively discussed" context. No LLM. |
| `src/vulndb/kev.py` | CISA KEV enrichment — fetches Known Exploited Vulnerabilities catalog (~1,100 CVEs), SQLite cache with 24h TTL, sets `known_exploited: True` on matching findings for `[ACTIVELY EXPLOITED]` interpreter marker. |
| `src/outreach/` | Outreach module — four batch commands: `promote` (filter briefs → prospects table), `interpret` (Claude API on filtered subset with `--min-severity` flag), `send` (compose for delivery), `export` (CSV mail merge — joins prospects with enriched companies DB, outputs domain/email/top confirmed finding/GDPR flag/interpretation snippet, sorted by severity for Brevo import). Entry: `python -m src.outreach promote\|interpret\|send\|export --campaign MMYY-industry`. |
| `src/interpreter/cache.py` | Interpretation cache — keyed by sha256(sorted findings + tier + language + prompt_version). Avoids re-interpreting identical finding sets. 3.8x savings (153 unique fingerprints for 589 sites). |
| `scripts/analyze_stats.py` | Deep statistical analysis — provenance-aware severity breakdown, header adoption, SSL, WordPress-specific, GDPR exposure, industry, cross-correlations, marketing-ready headlines. |
| `docs/analysis/pipeline-analysis-2026-04-05.md` | Pipeline analysis report — 1,173 sites, provenance-aware stats, SIRI-ready market evidence with version-match disclaimer. |
| `.claude/agents/osint/SKILL.md` | **OSINT Agent** — web application fingerprinting, passive recon, REST API namespace tables, CSS signature patterns, technology detection |
| `src/db/` | Client SQLite DB — CRUD layer for clients, findings (normalised definitions + occurrences), scans, briefs, consent, delivery log. Schema loaded from `docs/architecture/client-db-schema.sql`. DB at `data/clients/clients.db`. |
| `src/delivery/` | Telegram delivery bot — separate process (`python -m src.delivery`). Subscribes to Redis `client-scan-complete` (clients only, not prospects), pre-filters to High/Critical, interprets findings, composes HTML messages, delivers to client. |
| `src/delivery/buttons.py` | Client inline button — single "Got it" (silent ack, `sent→acknowledged`). Button removed after click to prevent double-actions. Status flow: `open→sent→acknowledged`. Writes to `finding_occurrences` + `finding_status_log`. |
| `src/prospecting/` | Lead generation pipeline — CVR ingestion, domain resolution, bucketing, brief generation, agency detection. Scanning lives in `src/prospecting/scanners/` (next row). `src/prospecting/scanner.py` is a thin backward-compat shim. |
| `src/prospecting/scanners/` | Scanner package (18 modules). `models.py` (`ScanResult` dataclass), `registry.py` (`_init_scan_type_map`, `_validate_approval_tokens`, mutable level maps), `runner.py` (`scan_domains` orchestrator + robots gate + ThreadPoolExecutor fan-out), `compliance.py` (pre-scan check writer), plus one module per tool: `tls.py`, `headers.py`, `robots.py`, `httpx_scan.py`, `webanalyze.py`, `subfinder.py`, `dnsx.py`, `ct.py`, `grayhat.py`, `nuclei.py`, `cmseek.py`, `nmap.py`, `wordpress.py`. Each module owns its tool-specific constants. All approved via Valdí tokens in `.claude/agents/valdi/approvals.json`. |
| `src/core/` | Shared infrastructure (lives above prospecting in the dependency graph). `config.py` — `PROJECT_ROOT`, `CONFIG_DIR`, `DATA_DIR`, `BRIEFS_DIR`, `REQUEST_TIMEOUT`, `USER_AGENT`, `CMS_KEYWORDS`, `HOSTING_PROVIDERS`. `logging_config.py` — `setup_logging()` with loguru + JSON sink + stdlib intercept. `exceptions.py` — `ScanToolError`, `DeliveryError`, `ConfigError`. |
| `src/worker/models.py` | Pydantic models for Redis job payloads (`ScanJob`, `EnrichmentJob`). Validated with `model_validate_json` at BRPOP time; invalid payloads logged and skipped. |
| `src/scheduler/` | Scan job creator + daemon mode. `--mode prospect`: one-shot from CVR data. `--mode daemon`: BRPOP loop on `queue:operator-commands` dispatching run-pipeline, interpret, send commands. |
| `src/scheduler/daemon.py` | Scheduler daemon — BRPOP on `queue:operator-commands`, dispatches pipeline/interpret/send, publishes progress to Redis pub/sub (`console:pipeline-progress`, `console:activity`, `console:command-results`). |
| `src/logging/redis_sink.py` | Shared loguru sink — background thread publishes log entries to Redis `console:logs` channel. All containers import this. `HEIMDALL_SOURCE` env var for readable source names. |
| `src/db/migrate.py` | Schema migration — applies `CREATE IF NOT EXISTS` to existing `clients.db`. Run inside Docker: `python -m src.db.migrate`. |
| `src/worker/` | Worker process — executes scan jobs, manages caching, runs twin scans. Entry point for all scanning operations. |
| `src/ct_collector/` | CertStream CT log collector — subscribes to Certificate Transparency logs for .dk domains, maintains local SQLite CT database (replaces remote crt.sh API). |
| `src/client_memory/` | Client history and remediation tracking — delta detection, remediation state machine, client profiles. JSON-based storage (migration to src/db/ in progress). |
| `config/delivery.json` | Config: Telegram delivery settings (require_approval toggle, retry, rate limit) |
| `config/interpreter.json` | Config: LLM backend, model, tone, language (default: English). Per-client language override via `clients.preferred_language` column. |
| `docs/design/design-system.md` | Operator console design system — tokens, colors, typography, components, layout, animation, severity mapping. Source of truth for `src/api/frontend/` visual system. |
| `docs/campaign/operational-guide.md` | **Campaign operational guide** — full pipeline flow (steps 1-6), every CLI command with examples, CSV column reference, batching strategy, 8-week timing plan. Start here for running the marketing campaign. |
| `docs/campaign/facebook-posts-week1-4.md` | 12 Facebook posts in Danish (weeks 1-4), Danish-psychology-aligned, ready to copy-paste. |
| `docs/campaign/email-and-dm-templates.md` | 2 email templates (first finding free + follow-up) + 3 DM templates (engagement, lead form, report follow-up). Danish, provenance-correct, craftsperson tone. |
| `docs/campaign/email-pitch-strategies.md` | 3 Danish-cultural-psychology-aligned email pitch frameworks (Open Window/Nabohjælp, Solidarity/collective trust, Ordentlighed/common decency) + combined Danish pitch draft. Acquisition stage, not yet deployed. |
| `docs/campaign/remediation-objection-handling.md` | Churn-prevention: "you found it but won't fix it" objection handling — 5 framing strategies, 5 Danish-resonant analogies, pre-emptive onboarding copy, escalation scripts (3 stages), green light loop, Danish translations. |
| `docs/campaign/marketing-keys-denmark.md` | **Danish consumer psychology brief.** 10 cultural keys (Janteloven, trust dynamics, egalitarianism, AI trust gap, etc.), Hofstede profile, 3 campaign rules. Authoritative source for all client-facing tone. |
| `.claude/agents/product-marketing-context.md` | Product marketing context — positioning, personas, customer language glossary, brand voice, Danish cultural constraints (10 hard rules), competitive landscape, objections, proof points. Reference for all outreach copy. |
| `docs/architecture/client-db-schema.sql` | Authoritative SQLite schema for client management DB (12 tables incl. prospects, 10 views incl. v_campaign_summary, 34+ indexes) |
| `scripts/test_delivery.py` | E2E delivery test — seeds test client (jellingkro.dk, real brief data), saves brief, publishes Redis event. Run inside delivery container. |
| `scripts/preview_message.py` | Message preview tool — runs interpret → compose pipeline, prints output to terminal and saves to file. `--send` flag delivers directly to operator's Telegram with client buttons (bypasses Redis/approval/DB). Permanent dev tool for message iteration. |
| `scripts/test_telegram_e2e.py` | Automated E2E Telegram test using Telethon — loads real brief, interprets via LLM, composes, sends with buttons, Telethon receives and clicks buttons, verifies response. `--click-fix` tests fix-request flow. `--brief` overrides brief selection. Dev dependency: `telethon`. |
| `scripts/backup.sh` | Atomic SQLite backup via `sqlite3 .backup`. Backs up `data/enriched/companies.db` from host path and `clients.db` from the Docker named volume via `docker exec api python -c sqlite3.backup`. Respects `HEIMDALL_BACKUP_DIR` env var (Pi5 microSD mount at `/mnt/sdbackup/heimdall`). Runs via cron at 03:00 daily. |
| `scripts/healthcheck.sh` | Cron-based operator alerting. Runs every 5 min, checks `docker inspect` health status + restart counts for each service, sends Telegram message via `curl` on failure. Works even when the application stack is down (no Redis or API dependency). |
| `scripts/valdi/regenerate_approvals.py` | Reproducible Valdí approval token regeneration tool. Imports each scan function from its module, computes `sha256(inspect.getsource(fn))`, writes new `approvals.json` + forensic log. `--apply` to write; dry-run by default. Use after refactors that change function source (ruff reformats, module moves, renames). |
| `.claude/settings.json` | Claude Code harness settings (project-scoped). Registers the hooks in `.claude/hooks/` plus existing `code-review-graph` integration. Precedence over user-level `~/.claude/settings.json`. |
| `.claude/hooks/` | PreToolUse, PostToolUse, and SessionStart hooks that enforce rules mechanically (not via memory). See the "Hook-Based Enforcement" section below for the full list and behaviour. |
| `.claude/agents/valdi/approvals.json` | Valdí approval token registry. 14 entries (one per approved scan function) with SHA-256 hash, UUID token, level, layer, and forensic log pointer. Read at worker startup by `_validate_approval_tokens`. Regenerate via `scripts/valdi/regenerate_approvals.py` after any refactor that changes function source. |

---

## Scanning Workflow

All scanning code must pass through Valdí before execution. The workflow is:

1. **Write or modify** a scanning function
2. **Submit to Valdí** (Gate 1) for scan-type validation against `SCANNING_RULES.md`
3. **If rejected:** Valdí logs the rejection with full reasoning. Rewrite the function. No execution.
4. **If approved:** Valdí logs the approval, generates an approval token, registers the scan type
5. **Federico reviews** Valdí's log entry and gives final go-ahead
6. **Execute** the scan, referencing the approval token

Before a scan batch runs, Valdí performs a lightweight Gate 2 check: confirming the approval token is valid and the target's consent state permits the scan type's layer.

**No scanning code executes without a valid Valdí approval token.** This applies to new code and to all existing code (which must be backfilled through Valdí before further use).

---

## Build Priority: MVP Hardening Complete → Pilot Prep

**Status (2026-04-12):** MVP hardening Phase 1/2 shipped (PRs #23, #25). Scanner decomposed. 947 tests passing on main. Valdí tokens regenerated post-refactor. Pi5 microSD backup operational. `.claude/hooks/` enforcing rules mechanically. **Pilot launch blocked by SIRI approval, not by code.**

**Phase 1 (Safe to Operate) delivered:** CI pipeline (GitHub Actions + ruff + pre-commit), 8 production bug fixes (scheduler daemon crash when Redis down, worker BRPOP spin-loop, delivery reconnection backoff `[1,2,5,10,30]`, Telegram `Forbidden`/`BadRequest` handled as permanent failure, feedparser socket timeout, slug map load logging, opaque scheduler errors, approval flow safety), `delivery_retry` table + retry coroutine, SQLite `verify_integrity` on startup, Docker health checks (worker + twin), cron-based Telegram alerting (`scripts/healthcheck.sh`), atomic WAL-safe SQLite backup via `scripts/backup.sh` with `HEIMDALL_BACKUP_DIR` env var (Pi5 microSD target), HTTP Basic Auth on `/console/*` and `/app`, error boundaries on all SQLite console endpoints, `Send Next 10` button in Campaigns view, dead code cleanup.

**Phase 2 (Safe to Maintain) delivered:** `scanner.py` (1,353 lines) decomposed into `src/prospecting/scanners/` package (18 modules). Shared infra extracted to `src/core/` (`logging_config`, `config`, `exceptions`). Pydantic validation on Redis job payloads (`src/worker/models.py`). Coverage floor `fail_under=65` enforced (measured 69%). Golden-path smoke test (`tests/test_golden_path.py`). Log levels corrected (DEBUG→WARNING for scan failures). `wpscan_wordpress_scan` approval dropped (obsolete since Sprint 4).

**Follow-up hardening (2026-04-12 same session):** Seven `.claude/hooks/` registered for mechanical enforcement — decision log injection on infra edits, destructive git guard, secret exposure guard, inline script guard, main branch push guard, CI config reminder, session start context. Six failure-prone memories deleted (replaced by hooks). Valdí approval tokens regenerated for all 14 scan functions after Phase 1/2 refactor invalidated the hashes, via `scripts/valdi/regenerate_approvals.py` + batched forensic log. CI `--deselect` flag removed; full test suite runs without exclusions again.

---

### Historical sprint work

**Sprints 1-3 (now historical):** Sprints 1-3 delivered (692 tests originally): Results API, consent management, Layer 2 scanners (Nuclei/CMSeek), finding interpreter, message composer, client memory + delta detection, digital twin, mobile console, deployment hardening (smoke tests, version pinning). Sprint 4 delivered so far: mid-scan bucket filter, CVR column fix, WPScan sidecar replaced by WPVulnerability API + local SQLite cache (saves 512MB RAM), CVR enrichment tool with SQLite DB, WordPress plugin version extraction (HTML `?ver=` params + REST API namespaces + meta generators + CSS class signatures), wordpress.org outdated plugin checks, OSINT agent, Pi5 alias fixes (`--force-recreate`, `heimdall-quick`), **client SQLite DB** (`src/db/`, 11 tables, 150 tests), **Telegram bot delivery** (`src/delivery/`, operator approval flow, `python -m src.delivery`), **Telegram message redesign** (10 content rules, HTML format, 🔴 Critical: / 🟠 High: severity labels, Confirmed/Potential sections, single "Got it" inline button, per-client language, `preview_message.py` dev tool), **tier-aware interpreter** (Watchman: plain language only, Sentinel: + fix instructions, `--tier` flag on preview_message.py), **provenance rename** (`twin-derived` → binary `confirmed`/`unconfirmed`, source-agnostic), **Telegram test tooling** (`preview_message.py --send`, Telethon E2E `test_telegram_e2e.py`), **simplified status flow** (`open→sent→acknowledged`, remediation service cut — Heimdall scans/interprets/alerts only), **GDPR sentence flexibility** (adaptation allowed, not verbatim), **loguru migration** (31 modules, stdlib logging replaced), **TLS version/cipher extraction** from SSL handshake (flags deprecated TLS 1.0/1.1), **additional HTTP header capture** (Permissions-Policy, Referrer-Policy, X-Powered-By, Server value), **KEV interpreter signal** (`[ACTIVELY EXPLOITED]` marker in interpreter prompt for CISA KEV findings), **RSS CVE watch** (`src/vulndb/rss_cve.py`, polls Wordfence/CISA/Bleeping Computer, regex CVE extraction, SQLite cache, enriches findings with "actively discussed" context), **CISA KEV module** (`src/vulndb/kev.py`, fetches KEV catalog, SQLite cache, flags `known_exploited` on findings), **TLS/cve_id pipeline fix** (wired TLS extraction + `cve_id` field through worker scan_job.py), **prospect lifecycle** (`src/outreach/`, prospects table in clients.db, campaign-based promote → interpret → send workflow), **Redis channel split** (`scan-complete` → `client-scan-complete` for clients only, prospects don't publish), **interpretation cache** (`src/interpreter/cache.py`, 3.8x savings on Claude API calls), **pipeline analysis** (`scripts/analyze_stats.py`, provenance-aware stats report). Sprint 4 delivered (continued): **operator console** (`src/api/frontend/`, Svelte 5 SPA at `/app`, 6 views + Logs, 80 KB JS + 18 KB CSS), **scheduler daemon** (`--mode daemon`, BRPOP on `queue:operator-commands`), **console REST API** (8 endpoints on `/console/*` — dashboard, pipeline, campaigns, prospects, clients, settings read/write, commands), **console WebSocket** (`/console/ws` — live queue status, Redis pub/sub forwarding, log batching, command dispatch), **Redis log streaming** (`src/logging/redis_sink.py`, background thread + bounded queue, `HEIMDALL_SOURCE` env var, all 5 containers wired), **Logs view** (source/level/timeframe/text filters, auto-scroll with pause-on-scroll-up, 5,000 entry ring buffer), **schema migration** (`src/db/migrate.py`), **53 new console tests** (endpoints, WebSocket, scheduler daemon, Redis sink, log filtering). **Nmap port scanning** (`_run_nmap()` in `src/prospecting/scanner.py`, top-100 + 13 critical infrastructure ports, `-sV` service detection, 4-tier severity mapping, 23 tests).

Goal: consent-gated scanning for paying clients, AI-interpreted findings in client's preferred language, Telegram delivery.

The pipeline runs as a Docker Compose stack on Pi5 with a two-phase architecture: subfinder batch enrichment (3 parallel batches) → per-domain core scans (with warm cache). Local CertStream CT database replaces remote crt.sh API. See `docs/architecture/pi5-docker-architecture.md` for full details.

### Input

Federico manually extracts a company list from CVR (`https://datacvr.virk.dk`) and saves it as `data/input/CVR-extract.xlsx`. The pipeline does **not** scrape or access datacvr.virk.dk.

### Pipeline Steps

1. Read CVR Excel export
2. Apply pre-scan filters from `config/filters.json` (industry_code, contactable) — see `.claude/agents/prospecting/SKILL.md` for filter config
3. Derive website domains from company email addresses
4. Resolve domains (check website exists + robots.txt compliance)
5. Layer 1 scanning with Valdí-approved scan types (httpx, webanalyze, subfinder, dnsx, CertStream, GrayHatWarfare) + WordPress-specific passive detection (plugin `?ver=` extraction, REST API namespace enumeration, meta generator tags, CSS class signatures)
6. Bucket results: A > B > E > C > D (see `.claude/agents/prospecting/SKILL.md` for full bucketing logic)
7. Apply post-scan filters from `filters.json` (bucket)
8. Evidence-based GDPR sensitivity determination (from scan results + industry code)
9. Agency detection (footer credits, meta author tags) — included in brief JSON as `agency.meta_author` and `agency.footer_credit`
10. Generate per-site briefs
11. WordPress domains: check installed plugin versions against wordpress.org latest (flag outdated), enrich with twin-derived Layer 2 findings (Nuclei against local digital twin) + WPVulnerability API lookups for plugin/core CVEs (no consent required). See `SCANNING_RULES.md` for twin framework.
12. Output: `prospects-list.csv` + per-site JSON briefs + agency briefs

### Supporting Data Files

| File | Purpose |
|------|---------|
| `data/input/CVR-extract.xlsx` | Input: manually extracted CVR company list |
| `config/filters.json` | Optional: configurable pipeline filters |
| `config/industry_codes.json` | Static: industry code → English name mapping |
| `data/output/prospects-list.csv` | Output: bucketed prospect list (only companies with live websites) |
| `data/output/briefs/{domain}.json` | Output: per-site technology briefs |
| `config/interpreter.json` | Config: LLM backend, model, tone, language settings |
| `config/consent_schema.json` | Config: consent authorisation JSON schema |
| `config/synthetic_targets.json` | Config: synthetic target registry for twin consent bypass |
| `tools/twin/slug_map.json` | Static: plugin/theme slug → version mapping for twin reconstruction |
| `data/enriched/companies.db` | SQLite: pre-enriched CVR data (companies, domains, enrichment log). Scheduler auto-detects this and skips legacy Excel pipeline. |
| `data/clients/clients.db` | SQLite: client management DB (clients, findings, scans, briefs, delivery log). Created by `src/db/connection.init_db()`. |
| `src/vulndb/cache.py` | WPVulnerability local cache — SQLite store for plugin/core CVEs with 7-day TTL |
| `config/delivery.json` | Config: Telegram delivery (require_approval toggle, retry_max, rate_limit) |

---

## Do Not

- Do not write or run scanning code without a valid Valdí approval token — see Scanning Workflow above
- Do not scan, probe, or make any automated requests to a domain whose `robots.txt` denies automated access — hard skip, log the reason, and move on. This applies to ALL layers including Layer 1. No exceptions.
- Do not restate scanning rules from `SCANNING_RULES.md` in other documents — reference the source document instead
- Do not write client-facing text that mentions Raspberry Pi, specific hardware, or internal infrastructure details — use abstract language ("dedicated secure infrastructure," "cloud-based AI interpretation layer")
- Do not store API keys, tokens, or secrets in any committed file
- Do not modify files in `.claude/agents/` without explicit instruction — these are agent definitions, not working documents
- Do not duplicate business data (pricing, statistics, policy figures) that already exists in `docs/briefing.md` — reference the briefing instead
- Do not modify code without running `git pull` first
- Features go into a branch and merge via pull request. Bug fixes commit directly to `main`.
- Do not create large monolithic commits — commit logically grouped changes separately with descriptive messages
- Do not add or remove a scanning tool without updating the tool table in `docs/briefing.md` in the same commit
- Do not make business, architecture, or technical decisions — present options with trade-offs, Federico decides

---

## Hook-Based Enforcement (`.claude/hooks/`)

The Claude Code harness runs a set of hooks defined in `.claude/settings.json` and implemented in `.claude/hooks/`. These are **mechanical enforcement** for rules that repeatedly failed as passive memory instructions. They run in the harness (not in the model), cannot be bypassed by model intent, and take precedence over anything in this file.

| Hook | Event | Behaviour |
|------|-------|-----------|
| `infra_danger_zone.py` | PreToolUse / `Edit\|Write` | Greps `docs/decisions/log.md` for keywords when editing infra files (`.gitignore`, `.env*`, `docker-compose*.yml`, `Dockerfile*`, `infra/`, `.github/workflows/`, `pyproject.toml`, `requirements.txt`, `CLAUDE.md`, `SCANNING_RULES.md`, `.pre-commit-config.yaml`, `scripts/*.sh`) and injects results as `additionalContext`. Non-blocking. |
| `destructive_git_guard.py` | PreToolUse / `Bash` | Blocks `git reset --hard`, `git checkout --`, `git restore .`, `git clean -f`, `git branch -D`, `git push --force`. Uses `shlex.split(posix=True)` tokenization so danger strings inside quoted arguments (commit messages) don't false-match. |
| `secret_exposure_guard.py` | PreToolUse / `Bash` | Blocks `source .env`, `cat .env`, bare `env`/`printenv`, `echo $*_KEY/*_TOKEN/*_SECRET/*_PASSWORD`. Shlex-based. |
| `inline_script_guard.py` | PreToolUse / `Bash` | Soft-blocks (`ask` decision) inline `python -c` / `node -e` scripts longer than 150 characters or containing newlines. Trivial one-liners pass through. |
| `main_branch_push_guard.py` | PreToolUse / `Bash` | Soft-blocks `git push origin main` when the local commits contain changes to `src/**/*.py` (feature work should go via branch + PR per `feedback_git_branching_rule`). |
| `ci_config_reminder.py` | PostToolUse / `Edit\|Write` | Injects a reminder to push and run `gh run watch` after editing `.github/workflows/`, `.pre-commit-config.yaml`, `pyproject.toml`, `requirements.txt`. Also reminds to add new tools to dep management. |
| `session_start_context.py` | SessionStart | Injects current branch, `git status`, recent commits, latest decision log headline, and the top priority rules at every session start. |

### Known limitations

- **shlex does not understand shell heredocs.** If you run `git commit -F - <<'EOF'` with dangerous text in the body, the heredoc content becomes loose shlex tokens and the destructive/secret guards will false-fire. Workaround: write the commit message to a tempfile and use `git commit -F /tmp/msg.txt`.
- Hooks run per tool call, so a multi-step plan may hit the same hook multiple times. That is intended — context re-injection on each edit keeps the reminder active.

### When a hook misfires

Don't try to route around the hook. Either:

1. The hook is right and you were about to do something wrong — reconsider the action
2. The hook has a bug — fix the hook script in `.claude/hooks/`, test it against the misfire case, commit the fix

Never silently skip a hook or find a phrasing that sneaks past it.

---

## Content and Copywriting Rules

When generating any written output for this project:

- **Pricing always in kr. (Danish kroner)**, not euros
- **Recurring example:** "restaurant with online booking system" — not "bakery owner"
- **No phrases like** "stated honestly," "full transparency," "to be honest" — confidence is implicit
- **Citations:** numbered superscripts → References section at end (not inline "Source: ..." format)
- **All scanning tool references** must include GitHub repository links
- **For policy data, statistics, and pricing details** — pull from `docs/briefing.md`, do not rely on memory

---

MANDATORY: Before performing any task, determine which agent(s) from `.claude/agents/` own this task. Read their SKILL.md. Do not proceed without confirming you are operating within that agent's stated boundaries and responsibilities.

<!-- code-review-graph MCP tools -->
## MCP Tools: code-review-graph

**IMPORTANT: This project has a knowledge graph. ALWAYS use the
code-review-graph MCP tools BEFORE using Grep/Glob/Read to explore
the codebase.** The graph is faster, cheaper (fewer tokens), and gives
you structural context (callers, dependents, test coverage) that file
scanning cannot.

### When to use graph tools FIRST

- **Exploring code**: `semantic_search_nodes` or `query_graph` instead of Grep
- **Understanding impact**: `get_impact_radius` instead of manually tracing imports
- **Code review**: `detect_changes` + `get_review_context` instead of reading entire files
- **Finding relationships**: `query_graph` with callers_of/callees_of/imports_of/tests_for
- **Architecture questions**: `get_architecture_overview` + `list_communities`

Fall back to Grep/Glob/Read **only** when the graph doesn't cover what you need.

### Key Tools

| Tool | Use when |
|------|----------|
| `detect_changes` | Reviewing code changes — gives risk-scored analysis |
| `get_review_context` | Need source snippets for review — token-efficient |
| `get_impact_radius` | Understanding blast radius of a change |
| `get_affected_flows` | Finding which execution paths are impacted |
| `query_graph` | Tracing callers, callees, imports, tests, dependencies |
| `semantic_search_nodes` | Finding functions/classes by name or keyword |
| `get_architecture_overview` | Understanding high-level codebase structure |
| `refactor_tool` | Planning renames, finding dead code |

### Workflow

1. The graph auto-updates on file changes (via hooks).
2. Use `detect_changes` for code review.
3. Use `get_affected_flows` to understand impact.
4. Use `query_graph` pattern="tests_for" to check coverage.
