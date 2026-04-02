# Decision Log

Running record of architectural decisions, rejections, and reasoning made during Claude Code sessions.

---
<!-- Entries added by /wrap-up. Format: ## YYYY-MM-DD — [topic] -->

## 2026-04-02 — Client DB schema design, 1,179-domain pipeline run, loguru migration planned

**Decided**
- Client management SQLite schema designed: 10 tables (industries, clients, client_domains, consent_records, scan_history, finding_definitions, finding_occurrences, brief_snapshots, delivery_log, pipeline_runs), 8 analytics views, 33 indexes. ADR-001 and ADR-002 document rationale.
- CVR as natural primary key — no synthetic client_id. Danish company registration is unique.
- Industry normalization — `industries` table with code/name_da/name_en. Client rows reference code only.
- Operators removed from DB — config-level setting, not a table. One operator (Federico) during pilot.
- Consent is binary — `consent_granted` boolean on clients. No `layers_permitted` array. Only Layer 2 requires consent.
- GDPR sensitivity on clients table, not per-finding or per-brief — it's a company property.
- Findings normalized into definitions + occurrences — "Missing HSTS header" stored once (1 definition) instead of 900 times. ~200 unique definitions vs ~14,678 occurrences.
- `brief_snapshots` stores full JSON as archive, extracted columns for queries. JSON nullable after 90-day retention.
- `pipeline_runs` table replaces JSON file iteration for aggregate stats.
- Loguru migration planned (40+ files) — replace stdlib logging with loguru. Plan at `.claude/plans/loguru-migration.md`. Dedicated session.
- Full pipeline run: 1,179 domains, 14,678 findings, 457 critical, 931 high. First scale validation.
- Filters broadened: removed industry_code and contactable restrictions. Bucket filter (A, B, E) keeps actionable sites.
- Stale filter flag pre-flight check added to scheduler — warns when <10% of domains ready.
- analyze_pipeline.py cleaned up: one value per line, CVE findings grouped by plugin name.
- NCC-DK grant removed from all plans — SIRI evaluation takes months, dependency chain unreachable.
- API keys rotated (SERPER_API_KEY, CLAUDE_API_KEY). TELEGRAM_BOT_TOKEN and GRAYHATWARFARE_API_KEY added to Pi5 .env.
- Logly evaluated and rejected — early-stage logging library (not production-ready, deadlock bugs, 830 downloads/month). Not a storage/search system.
- HackerTarget competitive analysis: their $10/month tier includes Nmap+OpenVAS+Nikto+WordPress testing. Our value: AI interpretation in Danish, ongoing monitoring, GDPR assessment, digital twin, Telegram delivery.

**Rejected**
- Logly as logging/storage solution — not production-ready, fundamental bugs, sole maintainer
- HackerTarget as data source — adds dependency, $10/month, couples pipeline to third-party uptime
- Synthetic client_id — CVR is the natural key for Danish companies
- Operators table — overengineered for pilot with one operator
- `layers_permitted` in consent records — consent is binary, only Layer 2 needs it
- GDPR per-finding — it's a company property, not a finding property
- Flat findings table — massive text duplication at scale

**Unresolved**
- Client DB schema implementation — designed and reviewed, not yet coded
- Loguru migration — planned, not executed (40+ files, dedicated session)
- Telegram bot — still the #1 delivery gap
- Finding confidence split (Confirmed vs Potential) — decided, not implemented
- Lawyer consultation outcome — determines consent storage details and outreach channels
- Grafana pipeline dashboard — nice to have, post-pilot
- Non-WordPress passive detection (SPF/DKIM/DMARC, JS library versions) — identified gap from pipeline data
- Nikto + Nmap — still pending

---

## 2026-04-02 — WordPress plugin version extraction, OSINT agent, HackerTarget gap analysis

**Decided**
- Plugin version extraction from HTML `?ver=` params — two-pass regex captures slug + version from `/wp-content/plugins/` paths. Extended to handle `&#038;ver=` and `&amp;ver=` HTML entities.
- REST API namespace enumeration — if WordPress advertises `/wp-json/` via `<link rel="https://api.w.org/">`, fetch it and parse `namespaces` array. One HTTP request replaces thousands of fingerprinting rules. Layer 1 compliant (site explicitly links to it).
- Meta generator tag parsing — multiple `<meta name="generator">` tags per page (WooCommerce, Elementor add their own). Extracts plugin name + version.
- CSS class signature detection — `.woocommerce`, `.et_pb_` (Divi), `.elementor` body classes reveal plugins not visible in asset paths.
- Tech_stack → detected_plugins merge — httpx/webanalyze detect plugins (Yoast SEO, WP Rocket) in tech_stack but these never reached vulndb lookup. Now merged via `slug_map.json` display-name-to-slug mapping.
- WordPress.org API for latest version checks — new `wp_versions.py` queries `api.wordpress.org/plugins/info/1.0/{slug}.json`, caches 24h in vulndb SQLite. Generates "Outdated plugin" findings (medium severity).
- Outdated plugin check moved from `generate_brief` (pure compute) to `scan_job.py` (I/O layer) — network calls don't belong in brief generation.
- `slug_map.json` expanded: LiteSpeed Cache corrected from `null` to `litespeed-cache` (it IS a plugin), Divi Builder, Tablepress, Complianz GDPR added.
- Pi5 aliases fixed: `--no-cache` removed (caused 15-30 min ARM64 rebuilds), replaced with `--force-recreate` (uses layer cache, ~1 min). New `heimdall-quick` alias for Python-only deploys (~20-30s).
- Finding confidence split (Option C): brief findings will be split into "Confirmed" (version-matched) and "Potential" (version unknown) sections. Prevents false alarm from critical CVEs on unknown-version plugins. Queued for interpretation/delivery sprint.
- OSINT agent created — web application fingerprinting, passive recon, technology detection. Carries forward REST API namespace tables, CSS signature patterns, lessons from HackerTarget comparison and March 22 Layer 2 incident.
- WPVulnerability API `impact` field handled as list (was crashing on Pi5 — `AttributeError: 'list' object has no attribute 'get'`).
- Enriched CVR database deployed to Pi5 via git commit (5.6MB). Scheduler auto-detects SQLite DB, skips legacy Excel pipeline.

**Rejected**
- Volume-mounting `src/` in Docker containers for instant code updates — Docker expert recommended against it: partial git pulls during active scans can load half-updated code, `__pycache__` issues with `:ro` mounts, doesn't translate to multi-node/CI.
- Using HackerTarget as a data source — adds $10/month dependency, couples pipeline to third-party uptime. The only gap (IP reputation) is better covered by planned abuse.ch URLhaus + WHOIS integration with free, direct sources.
- Keeping all CVE findings at original CVSS severity regardless of confidence — cries wolf, erodes trust. A restaurant owner's developer runs HackerTarget free scan, sees no CVE mentions, concludes we're inflating findings.

**Unresolved**
- Confidence split implementation — brief structure change affects Finding Interpreter, Message Composer, Telegram templates. Queued for interpretation sprint.
- conrads.dk still shows 6 plugins (not 9 like HackerTarget) — REST API + meta generator + CSS detection deployed but pipeline ran before these commits on Pi5. Next run should improve. 3 remaining gaps: `divi-builder` (may need REST API namespace `divi/v1` or `et/v1`), `woocommerce` (should appear via meta generator or CSS class), `gravityforms` duplicate (dedup difference, not a real gap).
- Nikto + Nmap implementation still pending
- API key rotation still pending (SERPER_API_KEY, CLAUDE_API_KEY)
- Network Security SKILL.md still references WPScan sidecar in Layer 2 tools table

---

## 2026-04-01 — Enriched DB deployment to Pi5, WPVulnerability docs gap identified

**Decided**
- Enriched CVR database (`data/enriched/companies.db`) committed to git for Pi5 deployment — `heimdall-deploy` pulls it automatically via `git pull`
- SQLite WAL journal files (`*.db-shm`, `*.db-wal`) added to `.gitignore` — only the checkpointed `.db` is committed
- WAL checkpoint (`PRAGMA wal_checkpoint(TRUNCATE)`) added to enrichment pipeline exit — ensures `.db` is self-contained before commit
- Scheduler container gets `data/enriched:/data/enriched:ro` bind mount + `/data/enriched` directory in Dockerfile
- DB path derivation confirmed: scheduler reads `/data/input/CVR-extract.xlsx` → resolves to `/data/enriched/companies.db` → auto-detects and skips legacy Excel pipeline
- Enrichment pipeline filter step (Step 7) removed — filtering happens at scan time in the scheduler, not destructively in the enrichment DB
- WPScan references replaced with WPVulnerability across CLAUDE.md, SCANNING_RULES.md, briefing.md
- audit.py stale WPScan checks replaced with enrichment/WPVulnerability equivalents
- Latent `enriched_at` double-set bug fixed in `enrichment/db.py`

**Rejected**
- SCP/rsync-based DB sync to Pi5 — unnecessary complexity when git handles it and the file is ~5.6MB
- Keeping filter step in enrichment pipeline — destructive (marks domains not-ready), requires re-run to change filters

**Unresolved**
- Enrichment pipeline test coverage not written
- API key rotation still pending (SERPER_API_KEY, CLAUDE_API_KEY exposed in conversation)
- Nikto + Nmap implementation still pending

---

## 2026-04-01 — Session wrap-up: legal document package, SIRI quotes, channel decisions

**Decided**
- Physical letter removed as outreach channel — contradicts Heimdall's modern positioning. All remaining channels are electronic (email, contact form, Messenger).
- Phone calls removed as outreach channel — will not happen.
- Old Q3 (physical letter to Reklamebeskyttet) removed from legal briefing. 17 questions → 16, renumbered. Cross-references updated across 6 files.
- Legal briefing trimmed for semantic economy (390 → 295 lines). Removed verbose reasoning, redundant context, source annotations.
- Documents Attached cut from 7 to 2 (notification + template). Internal docs available on request — lawyer doesn't need to read scanning rules or compliance checklists.
- Sample security notification reworked from physical letter to channel-neutral message template.
- Incident details (March 22: dates, paths, domain counts, 5-step response) removed from all outward-facing documents. Incident described only as "a scanning function crossed the Layer 1 boundary undetected."
- Valdí sections in SIRI application (4.3, 5.5) rewritten for persuasion: contrast framing, two-gate reasoning, rejection logs as key evidence, honest limitations, "pre-revenue startup with compliance system" positioning.
- Three industry quotes added to SIRI application: McLoughlin (SMB mandates), Microsoft (71% shadow AI), ISO 42001 (governance frameworks). References 18–20 added.

**Rejected**
- Keeping all 7 legal documents as attachments — lawyer bills by the hour, most are internal docs already summarized in the briefing.
- Aggressive trim of legal briefing (removing "Our reasoning" sections entirely) — moderate trim chosen instead, keeping the three-part structure.

**Unresolved**
- Compliance checklist "Open Questions" section (6 items) is now a stale subset of the 16-question briefing — consider updating or adding a pointer to the briefing.
- Lawyer meeting outcome will determine which outreach channels are viable — decisions on Q1 (notification ≠ marketing) are now existential since physical mail and phone were removed.

## 2026-03-30 — Session wrap-up: twin networking, bucket filter, tool audit, terminology purge

**Decided**
- Twin WPScan networking fix: `socket.gethostname()` → `_get_container_ip()` (UDP socket trick to discover container IP on Docker bridge network). Sidecar was failing because container IDs aren't resolvable cross-container.
- WPScan exit code 4 root cause identified: "Could not connect to server" (networking) + "HTTP Error 401" (missing API token). Both addressed.
- Mid-scan bucket filter: worker classifies bucket after cheap CMS detection (httpx + webanalyze), returns early for filtered buckets. Skips expensive scans (subfinder, dnsx, nuclei, twin) for unwanted buckets.
- CVR Excel column indices fixed: shifted by 2 (Startdato, Ophørsdato columns were missing). Industry code, email, and Reklamebeskyttet were all reading wrong columns.
- `heimdall-deploy` alias sequenced: build worker first (heavy Go compilation), then lighter images, then `up -d`. Prevents OOM on Pi5.
- `heimdall-pipeline` now flushes `cache:wpscan:*` keys alongside queue flush.
- WPScan API token moved from hardcoded default to Docker Compose env var (`${WPSCAN_API_TOKEN:-}`).
- "Level" terminology purged from all 15 active docs. Replaced with Layer 1/2 + consent state language + Watchman/Sentinel/Guardian plan names.
- CLAUDE.md rules added: tool table must update with tool changes; no decisions without Federico.

**Rejected**
- Claude making tool scope decisions ("sufficient", "replaced by") — all decisions are Federico's.
- "Level 0/1/2" as terminology — replaced by consent state descriptions.

**Unresolved**
- Twin WPScan still failing on Pi5 — networking fix deployed but WPScan API 401 errors need `.env` token on Pi5
- Nikto implementation (decided: implement now, code not written)
- Nmap implementation (decided: implement now, code not written)
- "Level" terminology still in Python code (`job.level`, `_LEVEL0_SCAN_FUNCTIONS`, etc.) — code purge deferred
- SSLyze backlog milestone not assigned
- GrayHatWarfare API key not configured on Pi5
- WPScan commercial API pricing research for SIRI cost projections
- Subfinder 300s timeout for large batches

---

## 2026-03-30 — Tool audit: align documentation with implementation reality

**Context:** Briefing and SIRI application listed tools never implemented (SSLyze, testssl.sh). Tools actively used (dnsx, CMSeek, GrayHatWarfare, CertStream) were missing from docs. 22 documents referenced tools inconsistently.

**Decided (by Federico)**
- **Nikto**: Implement now — install in Docker, write `_run_nikto()`, add to Layer 2 pipeline.
- **Nmap**: Implement now — install in Docker, write `_run_nmap()`, add to Layer 2 pipeline.
- **SSLyze**: Defer — keep current Python ssl module for TLS checks. SSLyze goes to backlog for deeper analysis (cipher suites, protocol versions, HSTS, OCSP). Docs updated to reflect current state.
- **testssl.sh**: Discard permanently — overlaps with SSLyze, bash-based, harder to integrate into Python pipeline.
- Briefing tool table updated: 9 tools → 11 tools. Added dnsx, CMSeek, CertStream, GrayHatWarfare. Removed SSLyze, testssl.sh.
- CLAUDE.md rule added: "Do not add or remove a scanning tool without updating the tool table in `docs/briefing.md` in the same commit"
- CLAUDE.md rule added: "Do not make business, architecture, or technical decisions — present options with trade-offs, Federico decides"
- "Level" terminology to be purged from all docs — replaced by Layer 1/2 for scan classification, Watchman/Sentinel/Guardian for plan tiers.

**Rejected**
- testssl.sh as part of the tool chain — overlaps with SSLyze, bash dependency, no Python integration path.

**Unresolved**
- Nikto and Nmap code implementation (Docker install, scanner functions, scan_job.py integration, tests)
- "Level" terminology purge across all docs and code
- SSLyze backlog milestone not yet assigned
- GrayHatWarfare API key not configured — free tier evaluation pending
- WPScan API pricing research for SIRI cost projections

---

## 2026-03-29 — OpenClaw removal, twin WPScan fix, SIRI doc correction, backlog audit

**Decided**
- OpenClaw permanently removed from Heimdall architecture. Replaced by Claude API agent (Anthropic SDK tool_use + agentic loops) + python-telegram-bot. Reasons: 512 known vulns, plaintext API key storage, 1,184 malicious ClawHub skills, Node.js/Python runtime mismatch, zero integration code after 3+ sprints. OpenClaw references retained only where it appears as a scanning TARGET (exposed instance detection).
- Human-in-the-loop message approval is pilot-only (5 clients). At scale the agent sends autonomously with confidence-gated escalation. "It is unthinkable that I can review hundreds of messages every week."
- Twin WPScan fix: added `--force` (bypasses NotWordPress error), `--disable-tls-checks`, `--api-token` passthrough, HTTP/1.1, oEmbed link, RSS feed, slash-agnostic routing, WordPress HTML comments. 15 new tests, 484 total pass. Not yet verified on Pi5.
- SIRI docs corrected: replaced "353 live Vejle-area domains" with "203" (actual clean pipeline output) in all achievement/metric contexts.
- WPScan cache flush added to `heimdall-flush` alias (clears `cache:wpscan:*` keys that cached stale "not_wordpress" results for 24h).
- Full backlog audit by TPMO + architect: identified 5 blockers, 6 high-priority items, 7 medium items for Sprint 4 readiness.

**Rejected**
- OpenClaw as Heimdall runtime — security posture incompatible with a security product. See above.
- Claude Agent SDK (`claude-agent-sdk`) for the delivery agent — wraps Claude Code CLI with file/web/shell tools, wrong abstraction for domain-specific tools. Vanilla `anthropic` SDK with manual agentic loop is simpler and gives approval gates.
- Single Telegram bot for both operator and client — separation of concerns requires two bots (operator: approve/reject/edit; client: receive reports, ask questions).

**Unresolved**
- Twin WPScan fix not verified on Pi5 — `heimdall-deploy` then `heimdall-pipeline` needed
- Telegram bot does not exist — no bot created, no `python-telegram-bot` in requirements, no delivery code
- Agent coordinator not built — Claude API agentic loop with tools for scan results, client memory, message composition, Telegram delivery
- Cron scheduling not implemented — `src/scheduler/main.py` `--mode scheduled` returns error
- Client onboarding workflow missing — no way to create client profile, link Telegram chat, set scan tier
- Scanning authorization template missing — lawyer meeting (week of 2026-03-31) should produce this
- Industry names empty for all 203 briefs — data flow issue from CVR extract
- Agency detection producing no results — `meta_author`/`footer_credit` empty upstream
- Subfinder 300s timeout for 68-domain batches
- Video pitch script for SIRI — mandatory, unstarted
- Project plan (`docs/plans/project-plan.md`) materially stale
- `docs/briefing.md` last-updated header says March 22

---

## 2026-03-29 — Late session: concurrent scheduler fix, twin WPScan, OpenClaw

**Decided**
- Concurrent scheduler fix: scheduler moved to Docker Compose profile `["run"]` (not started by `docker compose up`), Redis lock (`scheduler:lock`, NX, 1h TTL) prevents double execution, flush now clears enrichment counters
- Twin WPScan format mismatch fixed: `_request_twin_wpscan` now reads sidecar's flat `vulnerabilities` list instead of raw WPScan format. Two regression tests added with mocked sidecar responses.
- Queue labels: `heimdall-queue` now shows `scan: N`, `enrichment: N`, `wpscan: N`
- OpenClaw is the core runtime for Heimdall — not optional, not "worth exploring." Telegram delivery, cron scheduling, agent coordination all go through OpenClaw. Sprint 4 starts with OpenClaw installation on Pi5.

**Rejected**
- Building a custom Telegram bot for Sprint 4.1 — OpenClaw has built-in Telegram channel integration
- Treating OpenClaw as optional infrastructure — it's been in the architecture from day 1

**Unresolved**
- Twin WPScan exit code 4: WPScan likely doesn't recognize the twin as WordPress. Sidecar logging deployed but exit codes not yet verified. Twin WordPress emulation may need improvement.
- Subfinder times out at 300s for 68-domain batches — batch size vs timeout mismatch
- Industry names not flowing from CVR extract to briefs
- Agency detection producing no results

---

## 2026-03-29 — Sprint 3.5 hardening + pipeline operations + marketing strategy

**Decided**
- Deployment hardening (Sprint 3.5): Docker smoke test (bash, not pytest — no test framework in prod image), export script tests, all Go tool versions pinned (httpx v1.9.0, webanalyze v0.4.1, subfinder v2.13.0, dnsx v1.2.3, nuclei v3.7.1), CMSeek pinned to commit 20f9780
- Pi5 operational aliases: heimdall-pipeline (smoke → flush → schedule), heimdall-export, heimdall-analyze, heimdall-deep, heimdall-audit, heimdall-smoke
- Pipeline results: bind-mount data/results to host (not Docker named volume), CVR extract tracked in git, pipeline output tracked in git — enables laptop/Pi5 sync
- Twin WPScan: route through Redis sidecar (rpush for priority), sidecar handles http:// URLs
- PerimeterIQ evaluated by architect, docker-expert, network-security: cherry-pick threat feeds into Heimdall, don't build as separate product
- Marketing strategy: LinkedIn irrelevant for SMB target segment (<20 employees). Primary channels: phone, physical letters, Facebook, in-person. Legal briefing prepared (8 questions for lawyer meeting week of 2026-03-31)
- Threat feed integration planned (Sprint 4+): abuse.ch URLhaus + WHOIS domain age first, PhishTank/CrowdSec/GreyNoise deferred (rate limits)
- Deep analysis script: contactable breakdown, industry, timing, outreach prioritization matrix

**Rejected**
- PerimeterIQ as standalone product — no recurring revenue model, fleet management nightmare, architecturally incompatible with Heimdall
- PerimeterIQ as Heimdall tier — scope creep, DNS filtering catches ~40% of threats, SMBs won't understand "DNS anomaly"
- LinkedIn for end-customer outreach — target customers (restaurants, physios, barbershops) are not on LinkedIn
- pytest inside Docker container — production image shouldn't ship test framework
- Disposable inline analysis scripts — all analysis now in reusable scripts/analyze_pipeline.py

**Unresolved**
- Twin Nuclei produces 0 findings — templates don't match simplified twin responses (design limitation, not bug)
- Twin WPScan sidecar — jobs received but no completion logs visible. Needs debugging with better sidecar logging (added but not yet verified on Pi5)
- Industry names not flowing from CVR to briefs — empty in pipeline output
- Agency detection producing no results — meta_author/footer_credit empty in briefs
- 6 consecutive broken alias pushes — need better pre-push testing for infrastructure changes

---

## 2026-03-28 — Mobile console PWA + live twin demo mode

**Decided**
- Mobile console merged from `feature/mobile-console` as a PWA (vanilla JS, no framework, no build step) served from the existing FastAPI API container
- Two modes: Monitor (5s polling of Redis queue depths + recent scans) and Demo (theatrical brief replay with WebSocket streaming)
- Live Twin demo mode added: orchestrator starts a digital twin in-process, runs Nuclei/WPScan against it, streams findings to WebSocket as they arrive. Same event schema as replay — frontend animation code unchanged
- Concurrency guard: only one live demo at a time (asyncio.Lock), returns 429 if occupied. Falls back to replay if tools not installed
- `agents/fullstack-guy/SKILL.md` placed at `.claude/agents/fullstack-guy/SKILL.md` (consistent with agents/ refactor)
- Console explored as Svelte rewrite — user evaluated options via visual companion, preferred the existing vanilla JS design

**Rejected**
- Svelte/React rewrite — user saw mockups, preferred current vanilla JS (no build step, simpler deployment)
- Redesigned demo section with terminal + chips layout — user preferred the original radial progress + timeline design
- Separate Docker container for console — lives in existing API container, no additional resource cost

**Unresolved**
- Console not yet reflected in CLAUDE.md or briefing.md (PR #12 still open)
- `prefers-reduced-motion` media query not implemented in console CSS
- WebSocket auto-reconnect on network drop not implemented
- Multi-client simultaneous demo would need Redis pub/sub refactor (current: single asyncio.Queue per scan_id)

---

## 2026-03-28 — Digital twin: brief-to-website generator

**Decided**
- Digital twin tool reads prospect brief JSON, spins up a local Docker container that replicates the prospect's tech stack (WordPress version, plugin versions, missing headers, exposed endpoints)
- Lives in `tools/twin/`, Dockerfile at `infra/docker/Dockerfile.twin`, compose profile `["twin"]`
- Legal: scanning the twin is scanning our own infrastructure — Straffeloven §263 does not apply. Consent framework only applies to the prospect's actual servers. Validated by Valdi agent (`.claude/agents/valdi/SKILL.md`).
- Compliance framework amended: `SCANNING_RULES.md` now includes a "Heimdall-Owned Test Infrastructure" section. Twin-targeted scans require Gate 1 approval tokens but bypass Gate 2 consent checks via synthetic target registry (`config/synthetic_targets.json`).
- Key use case: Layer 2 tools (Nuclei, WPScan) can run against the twin without prospect consent, surfacing specific CVEs and vulnerability matches from Level 0 passive data. This is a significant competitive advantage — vulnerability-grade findings without a signed agreement.
- Six documented use cases: Layer 2 without consent, pre-consent sales reports, pipeline regression testing, new tool onboarding, remediation verification, interpreter training. See `docs/digital-twin-use-cases.md`.
- DevOps review: Dockerfile in `infra/docker/` (convention), ports 9080/9443 (avoids Dozzle conflict), compose profile pattern (matches ct-backfill), cert at build time, health check
- Network Security review: slug normalization table (Yoast SEO → `wordpress-seo`), added `/readme.html`, `/favicon.ico`, `X-Powered-By`, `Link`, `X-Pingback` headers, ~50KB HTML with Danish filler, response jitter

**Rejected**
- Separate repository for the twin — no independent users, no separate release cycle, sole input format is our brief JSON
- nginx/Apache container — over-engineered for what is purely HTTP response simulation; stdlib `http.server` keeps it simple and dependency-free
- Generate Dockerfiles per-brief — unnecessary complexity; a single server reads the brief at startup

**Unresolved**
- Twin-derived findings should be labelled as "derived from passive fingerprinting" in output — not yet implemented in the brief generator
- Automated pipeline extension (Layer 1 brief → twin → Layer 2 scan → enriched brief) — future sprint work
- Non-WordPress CMS support (Shopify, Drupal, Joomla) — extensible by adding CMS-specific template modules

---

## 2026-03-28 — Sprint 3.2 Level 1 scan types shipped (Nuclei, WPScan, CMSeek)

**Decided**
- Nuclei: Go binary in worker image, 12,763 templates baked at build. Safety flags: `-exclude-tags rce,exploit,intrusive,dos`, `-no-interactsh`, `-disable-redirects`. Verified on Pi5 ARM64 (v3.7.1)
- WPScan: Ruby sidecar container (`ruby:3.2-alpine`) — NOT embedded in worker image. Redis request-response delegation pattern (LPUSH queue:wpscan → BRPOP result). Security-reviewed: fixed UA, no TLS bypass, no user enum, API token via env var only. Verified on Pi5 ARM64 (v3.8.28)
- CMSeek: Pure Python, git clone in worker image (`/opt/cmseek`). File-based output adapter (reads `Result/<domain>/cms.json`, cleans up). Path traversal guard (regex + realpath). Verified on Pi5 ARM64
- Level-gated registry: `_LEVEL0_SCAN_FUNCTIONS` (9 types) / `_LEVEL1_SCAN_FUNCTIONS` (3 types) with `WORKER_MAX_LEVEL` env var. Workers only validate tokens for their level
- Re-queue with cap: Level 0 workers re-queue Level 1 jobs max 5 times, then drop with error log
- Full stack verified on Pi5: 3 workers + WPScan sidecar + Redis all healthy, Valdí tokens validated

**Rejected**
- WPScan embedded in worker image — 250-350 MB Ruby bloat, 200-400 MB runtime RAM, ARM64 gem compilation risk. Sidecar is lighter (single 150 MB container vs Ruby in 3 workers)
- `wpscanteam/wpscan` upstream Docker image — likely no ARM64 support. Built our own from `ruby:3.2-alpine`
- `--random-user-agent` for WPScan — evasion concern under Danish law
- `--disable-tls-checks` for WPScan — weakens forensic chain
- `u1-3` user enumeration for WPScan — may exceed consent scope
- `--api-token` on CLI — token visible in process list. WPScan reads from env natively

**Unresolved**
- WPScan commercial API pricing (Automattic quote still pending)
- CMSeek git clone has no version pin — supply chain risk (MEDIUM, deferred)
- CMSeek cache TTL 7d may be too long for version data (security-relevant)
- Digital twin for end-to-end Level 1 testing without real targets
- Orphan monitoring containers on Pi5 (prometheus, cadvisor, grafana) need cleanup or integration into compose

---

## 2026-03-28 — Sprint 3 increments 3.0, 3.1, 3.3, 3.2 planned

**Decided**
- Results API (3.0): FastAPI in existing 256 MB API container, reads from disk (not Redis), pub/sub listener wired for interpretation pipeline
- Consent framework (3.1): fail-closed on all error paths, `authorised_by.role` is informational only (legal standing question deferred to Danish counsel), subdomain scope is strict (explicit list, no wildcards), consent document existence verified on disk, path traversal protection on consent_document field
- Finding Interpreter (3.3): Claude API (Sonnet) over template-based — the contextual narrative (connecting findings across a business's specific situation) is the product differentiator. LLM backend abstraction allows Ollama swap via config change. Tone parameter (concise/balanced/detailed) configurable per client.
- Message Composer: Telegram formatting with 4096-char auto-splitting, ready for Sprint 4.1 bot delivery
- Level 1 scan types (3.2): Nuclei first (same Go ecosystem), WPScan + CMSeek deferred to follow-up (ARM64 Ruby gem risk). Level-gated registry refactor: `_LEVEL0_SCAN_FUNCTIONS` / `_LEVEL1_SCAN_FUNCTIONS` with `WORKER_MAX_LEVEL` env var
- Python-expert and docker-expert reviews run in parallel after each increment — caught path traversal via pub/sub, missing Docker volumes, client re-creation per API call, fragile JSON parsing

**Rejected**
- Template-based interpretation (Option C) — produces generic output indistinguishable from templates for the end client; the value is in contextual, industry-specific narratives
- Ollama on Pi5 alongside current stack — only 200 MB free RAM; would require stopping workers during interpretation phase
- Separate Level 0 vs Level 1 worker Docker images — doubles build time and deployment complexity for no operational benefit on a single Pi5
- Pydantic response models for the API — unnecessary overhead for serving worker-written JSON as-is

**Unresolved**
- Who is legally authorised to consent to active scanning under Danish law (§263) — pending legal counsel
- WPScan commercial API pricing (Automattic quote pending)
- WPScan Ruby gem ARM64 compilation — deferred until Nuclei is verified
- CMSeek pip package availability — may need git clone install
- Nuclei template size (~300 MB) — may need filtering to critical/high severity only
- CLAUDE.md Build Priority section still says "Phase 0" — needs update to reflect Sprint 3 state

---

## 2026-03-27 — Tiered enrichment: subfinder batch + local CT database + observability

**Decided**
- Subfinder batch pre-scan: two-phase scheduler (enrichment → scan), 3 parallel batches of 68 domains, Redis atomic counter for completion signaling
- Local CertStream CT database replaces remote crt.sh API: SQLite WAL mode on NVMe, `immutable=1` for readers, ct-collector Docker container
- cAdvisor replaced with Docker built-in Prometheus metrics endpoint (cAdvisor incompatible with Pi OS containerd snapshotter)
- Docker-expert agent reviews mandatory before merge (both branches reviewed, 9 findings fixed per branch)
- Prometheus retention: 30 days or 2GB whichever first
- Worker `stop_grace_period: 330s` (5 min subfinder + 20s stagger + 30s buffer)
- `ENRICHMENT_WORKERS` configurable via env var, not hardcoded
- Subfinder CLI flags: `-t 10` (threads) and `-max-time 3` (min/domain) to cap memory within 1GB container budget

**Rejected**
- cAdvisor for container metrics — incompatible with Pi OS overlayfs/containerd snapshotter
- Worker `depends_on: ct-collector` — .dk certificates too rare in CertStream for healthcheck timing
- Hardcoded `ENRICHMENT_WORKERS=3` — made env-configurable per docker-expert review

**Unresolved**
- Subfinder found 0 subdomains — most passive sources need API keys (not blocking, pipeline works)
- CT backfill from crt.sh not yet run — one-time step before first production deploy
- cgroup memory limits not supported on Pi OS kernel — `cgroup_enable=memory` added to cmdline.txt but container memory limits still show warnings
- Grafana dashboard needs customization for Heimdall-specific panels

---

## 2026-03-26 — Session wrap-up: tooling, pipeline enrichment, GDPR redesign, project restructure

**Decided**
- Integrate 4 new Level 0 tools: subfinder (subdomain enumeration), dnsx (DNS enrichment), crt.sh (CT log queries), GrayHatWarfare (exposed cloud storage index)
- Valdí classification: GrayHatWarfare → Layer 1 (third-party index), CloudEnum → Layer 2 (active enumeration)
- Add 5 Level 1 tools to SCANNING_RULES.md: CMSeek, Katana, FeroxBuster, SecretFinder, CloudEnum (not registered — no approval tokens until Level 1 pipeline is built)
- Replace flat `sales_hook` with structured `findings` array: severity (industry-standard), description, risk
- Evidence-based GDPR determination from scan results (plugins, tracking, e-commerce) replaces industry-code-only approach
- WPScan commercial API: flag as cost to investigate with Automattic, add to COGS in SIRI financials
- Three-phase project restructure: `pipeline/` → `src/prospecting/`, `docs/agents/` → `agents/`, docs reorganised

**Rejected**
- Flat per-event remediation pricing (Model A) — too rigid for variable-complexity work
- Bundled remediation credits (Model C) — premature before pilot validation
- Code-lives-with-agent structure (Option A) — awkward Python imports

**Unresolved**
- WPScan commercial API pricing (need quote from Automattic)
- crt.sh rate limiting (429s at 1s delay — increase to 2-3s)
- Hardcoded config values in config.py need extracting to `config/*.json` files (planned follow-up)
- Agent SKILL.md files have stale path references (data/prospects/, docs/Heimdall_Business_Case_v2.md)
- CLAUDE.md Scanning Workflow section still references `pipeline.main`
- Video pitch script (mandatory for SIRI) deferred
- Valdí forensic logs missing for the 4 new scan types (approval tokens reference files that don't exist yet)

---

## 2026-03-25 — Session wrap-up: SIRI pivot + pricing + remediation service

**Decided**
- Pricing finalized at aggressive tiers: Watchman 199 / Sentinel 399 / Guardian 799 kr./mo (annual: 599). All excl. moms. Source: Heimdall_Investor_Plan_v1_angel.docx (the manually maintained .docx had the final pricing, not the .md)
- Optional per-event remediation service added to all tiers: 599 kr. first hour, 399 kr./hr additional (reference pricing, subject to pilot adjustment, excl. moms). Model B — hourly with minimum
- Remediation service positioned as 4th durable differentiator: neither Intruder.io nor HostedScan offers hands-on fixes

**Rejected**
- Model A (flat per-event pricing) — too rigid for variable-complexity work
- Model C (bundled credits / unlimited add-on) — premature before pilot validation
- Premium pricing (499/799/1,199) — superseded by aggressive pricing strategy in .docx

**Unresolved**
- Video pitch script (mandatory 5-min for SIRI) — deferred to separate session
- Specific remediation pricing needs pilot validation
- CLAUDE.md Build Priority section has stale references that need cleanup

---

## 2026-03-25 — Pivot business documents from angel investor to Startup Denmark (SIRI) audience

**Context:** Federico is Argentinian, currently in Denmark on a Fast-Track employment scheme (Senior SAP Engineer at LEGO). The project was originally targeting angel investors and the NCC-DK grant pool. However, NCC-DK requires a CVR (Danish company registration), and Federico does not have one. The Startup Denmark program provides a path: a work/residence permit for non-EU founders to establish a company in Denmark — which then provides the CVR needed for grants.

**Decision:** Reframe all business case documents from "angel investor pitch" to "Startup Denmark residence permit application." The technical product is unchanged. The business case is reframed around SIRI's four scoring criteria: Innovation, Market Potential, Scalability, Team Competencies. Expert panel scores 1–5 per criterion; minimum average 3.5 required for approval.

**Consequences:**
- `heimdall-investor-plan.md` → `heimdall-siri-application.md` (major rewrite)
- `investor-plan-outline.md` → `siri-application-outline.md` (major rewrite)
- `Heimdall_Investor_Plan.docx` archived to `docs/business/archive/`
- Grant & Funding agent scope expanded to include SIRI application as Priority 0
- NCC-DK grant becomes Phase 2 (post-CVR), not primary goal
- New mandatory sections: "Why Denmark", "Scalability & Job Creation in Denmark", "Innovation"
- Sections removed: Risk Analysis, The Ask, Why Now (content folded into other sections)
- New future deliverable: 5-minute video pitch script (mandatory for SIRI submission)