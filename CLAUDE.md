<!-- CLAUDE.md v2.6 — Last updated: 2026-03-24 -->

# CLAUDE.md

MANDATORY: Before performing any task, determine which agent(s) from `.claude/agents/` own this task. Read their SKILL.md. Do not proceed without confirming you are operating within that agent's stated boundaries and responsibilities.

## Before Every Task
1. Identify which agent(s) this task falls under (see `.claude/agents/README.md`)
2. Read the relevant SKILL.md file(s)
3. If the task involves scanning, target selection, or client data — read `.claude/agents/valdi/SKILL.md` and `SCANNING_RULES.md` (project root), and verify compliance gates before proceeding
4. Confirm you are operating within that agent's boundaries

---

## What This Repository Is

Heimdall is an External Attack Surface Management (EASM) service for small businesses. It uses a Claude API agent (Anthropic SDK with tool use) to interpret findings in plain language and delivers results through Telegram. No client dashboard.

This repository is in **Phase 0 — Lead Generation Pipeline**, building on the laptop via Claude Code. Pi infrastructure comes later.

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

Without written consent, only Layer 1 activities are permitted. With written consent (Sentinel/Guardian clients), Layer 1 and Layer 2 activities are permitted within the agreed scope.

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
| `src/interpreter/` | Finding Interpreter — LLM-powered scan interpretation (Claude API / Ollama abstraction). Tier-aware: Watchman gets `title`, `severity`, `explanation`, `provenance` only; Sentinel/Guardian adds `action` (fix instructions). No `who` field (removed — clients know who built their website). Telegram prompt: no plugin names in titles/explanations, GDPR sentence (flexible adaptation) for confirmed data findings only, calm tone for potential findings. |
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
| `src/prospecting/` | Lead generation pipeline — CVR ingestion, domain resolution, Layer 1 scanning, bucketing, brief generation, agency detection. Core pipeline orchestration. |
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
| `docs/campaign/facebook-posts-week1-4.md` | 12 Facebook posts in Danish (weeks 1-4), psychology-annotated, ready to copy-paste. |
| `docs/campaign/email-and-dm-templates.md` | 2 email templates (first finding free + follow-up) + 3 DM templates (engagement, lead form, report follow-up). Danish, provenance-correct. |
| `.claude/agents/product-marketing-context.md` | Product marketing context — positioning, personas, customer language glossary, brand voice, competitive landscape, objections, proof points. Reference for all outreach copy. |
| `docs/architecture/client-db-schema.sql` | Authoritative SQLite schema for client management DB (12 tables incl. prospects, 10 views incl. v_campaign_summary, 34+ indexes) |
| `scripts/test_delivery.py` | E2E delivery test — seeds test client (jellingkro.dk, real brief data), saves brief, publishes Redis event. Run inside delivery container. |
| `scripts/preview_message.py` | Message preview tool — runs interpret → compose pipeline, prints output to terminal and saves to file. `--send` flag delivers directly to operator's Telegram with client buttons (bypasses Redis/approval/DB). Permanent dev tool for message iteration. |
| `scripts/test_telegram_e2e.py` | Automated E2E Telegram test using Telethon — loads real brief, interprets via LLM, composes, sends with buttons, Telethon receives and clicks buttons, verifies response. `--click-fix` tests fix-request flow. `--brief` overrides brief selection. Dev dependency: `telethon`. |

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

## Build Priority: Sprint 3 — Consent-Gated Pipeline

**Sprints 1-3 complete (692 tests). Sprint 4 in progress — Telegram delivery implemented, pilot launch (5 Vejle clients).** Sprint 3 delivered: Results API, consent management, Layer 2 scanners (Nuclei/CMSeek), finding interpreter, message composer, client memory + delta detection, digital twin, mobile console, deployment hardening (smoke tests, version pinning). Sprint 4 delivered so far: mid-scan bucket filter, CVR column fix, WPScan sidecar replaced by WPVulnerability API + local SQLite cache (saves 512MB RAM), CVR enrichment tool with SQLite DB, WordPress plugin version extraction (HTML `?ver=` params + REST API namespaces + meta generators + CSS class signatures), wordpress.org outdated plugin checks, OSINT agent, Pi5 alias fixes (`--force-recreate`, `heimdall-quick`), **client SQLite DB** (`src/db/`, 11 tables, 150 tests), **Telegram bot delivery** (`src/delivery/`, operator approval flow, `python -m src.delivery`), **Telegram message redesign** (10 content rules, HTML format, 🔴 Critical: / 🟠 High: severity labels, Confirmed/Potential sections, single "Got it" inline button, per-client language, `preview_message.py` dev tool), **tier-aware interpreter** (Watchman: plain language only, Sentinel/Guardian: + fix instructions, `--tier` flag on preview_message.py), **provenance rename** (`twin-derived` → binary `confirmed`/`unconfirmed`, source-agnostic), **Telegram test tooling** (`preview_message.py --send`, Telethon E2E `test_telegram_e2e.py`), **simplified status flow** (`open→sent→acknowledged`, remediation service cut — Heimdall scans/interprets/alerts only), **GDPR sentence flexibility** (adaptation allowed, not verbatim), **loguru migration** (31 modules, stdlib logging replaced), **TLS version/cipher extraction** from SSL handshake (flags deprecated TLS 1.0/1.1), **additional HTTP header capture** (Permissions-Policy, Referrer-Policy, X-Powered-By, Server value), **KEV interpreter signal** (`[ACTIVELY EXPLOITED]` marker in interpreter prompt for CISA KEV findings), **RSS CVE watch** (`src/vulndb/rss_cve.py`, polls Wordfence/CISA/Bleeping Computer, regex CVE extraction, SQLite cache, enriches findings with "actively discussed" context), **CISA KEV module** (`src/vulndb/kev.py`, fetches KEV catalog, SQLite cache, flags `known_exploited` on findings), **TLS/cve_id pipeline fix** (wired TLS extraction + `cve_id` field through worker scan_job.py), **prospect lifecycle** (`src/outreach/`, prospects table in clients.db, campaign-based promote → interpret → send workflow), **Redis channel split** (`scan-complete` → `client-scan-complete` for clients only, prospects don't publish), **interpretation cache** (`src/interpreter/cache.py`, 3.8x savings on Claude API calls), **pipeline analysis** (`scripts/analyze_stats.py`, provenance-aware stats report). Sprint 4 delivered (continued): **operator console** (`src/api/frontend/`, Svelte 5 SPA at `/app`, 6 views + Logs, 80 KB JS + 18 KB CSS), **scheduler daemon** (`--mode daemon`, BRPOP on `queue:operator-commands`), **console REST API** (8 endpoints on `/console/*` — dashboard, pipeline, campaigns, prospects, clients, settings read/write, commands), **console WebSocket** (`/console/ws` — live queue status, Redis pub/sub forwarding, log batching, command dispatch), **Redis log streaming** (`src/logging/redis_sink.py`, background thread + bounded queue, `HEIMDALL_SOURCE` env var, all 5 containers wired), **Logs view** (source/level/timeframe/text filters, auto-scroll with pause-on-scroll-up, 5,000 entry ring buffer), **schema migration** (`src/db/migrate.py`), **53 new console tests** (endpoints, WebSocket, scheduler daemon, Redis sink, log filtering). **Nmap port scanning** (`_run_nmap()` in `src/prospecting/scanner.py`, top-100 + 13 critical infrastructure ports, `-sV` service detection, 4-tier severity mapping, 23 tests).

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
