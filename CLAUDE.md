<!-- CLAUDE.md v3.0 — Last updated: 2026-04-18 -->

# CLAUDE.md

MANDATORY: Before performing any task, determine which agent(s) from `.claude/agents/` own this task. Read their SKILL.md. Do not proceed without confirming you are operating within that agent's stated boundaries and responsibilities.

## Before Every Task
1. Identify which agent(s) this task falls under (see `.claude/agents/README.md`)
2. Read the relevant SKILL.md file(s)
3. If the task involves scanning, target selection, or client data — read `.claude/agents/valdi/SKILL.md` and `SCANNING_RULES.md`, verify compliance gates
4. Confirm you are operating within that agent's boundaries

---

## Workflow Rules

**Plan mode.** Enter for any non-trivial task (3+ steps or architectural). If something goes sideways, STOP and re-plan — don't keep pushing. Write detailed specs upfront.

**Verification before done.** Never mark a task complete without proving it works. Run tests, check logs, diff behavior vs `main`. Ask "would a staff engineer approve this?"

**Demand balanced sophistication.** For non-trivial changes, pause and ask "is there a more elegant, simpler way?" If a fix feels hacky: "knowing everything I know now, implement a better solution." Skip for simple fixes.

**Codex review before the commit, not after.** Any commit that touches `src/**/*.py` or `tests/**/*.py` must be Codex-reviewed *before* `git commit` runs. Run `/codex:review` (or `node ~/.claude/plugins/cache/openai-codex/codex/1.0.4/scripts/codex-companion.mjs review ""`), read the output, address findings. The `precommit_codex_review_guard.py` hook (see "Hook-Based Enforcement" below) soft-blocks Python commits without review. Bypass — only when you have actually reviewed — by prefixing with `HEIMDALL_CODEX_REVIEWED=1`. Pure-docs / config commits are unaffected.

**Graph before Grep.** When exploring code, the first stop is the code-review-graph MCP tools (`semantic_search_nodes`, `query_graph`, `get_review_context`, `get_impact_radius`, `get_affected_flows`). They are faster, cheaper, and surface structural context (callers, tests, impact) that text scans cannot. Fall back to Grep / Glob / Read only when the graph genuinely does not cover the question.

---

## What This Repository Is

Heimdall is an External Attack Surface Management (EASM) service for small businesses, with aspiration to have enterprise-greade architecture and maturity. A Claude API agent interprets findings in plain language, delivered via Telegram. No client dashboard.

**Pi5 is PROD. Macbook is DEV.** Develop locally (`make dev-up` / `make dev-smoke`, see `docs/development.md`). Deploy: `main` → dev-smoke green → fast-forward `prod` → `HEIMDALL_APPROVED=1 git push origin prod` → SSH Pi5 `heimdall-deploy` (see `docs/runbook-prod-deploy.md`). Business phase: **pre-pilot, blocked by SIRI approval.** Recently merged (2026-04-27): PR #46 (operator console V1 trial-expiring + V6 retention queue tabs — V1+V6 render but stay empty in DEV until the DRYRUN-CONSOLE seed plan ships) and PR #47 (M37 dev/prod bind-mount separation + operator-console pipeline-progress emission + worker healthcheck heartbeat thread + dev subfinder tuning so the dev pipeline completes in ~30s with a smoothly-moving bar). Operator-console bounded-context reframe **all four open decisions resolved 2026-04-27 evening**: Notifications becomes 7th context; `config_changes` uses DB triggers for capture + repository wrappers for validation/intent/actor; RBAC v1 ships as `Permission` enum + `require_permission` decorator (table-backed RBAC deferred until >2 roles); three-sprint sequence locked (Stage A identity/auth/session/router carve → Stage A.5 control-plane guarantees → V2 onboarding feature). Next active feature work: DRYRUN-CONSOLE seed (parallel) and Stage A foundation. See `docs/decisions/log.md` 2026-04-27 (evening) entry.

---

## Document Hierarchy

When documents conflict, precedence is:

| # | Document | Role |
|---|----------|------|
| 1 | `SCANNING_RULES.md` | Authoritative — what's allowed/forbidden per Layer & consent state. |
| 2 | `.claude/agents/valdi/SKILL.md` | Enforces SCANNING_RULES. Validation workflow, forensic logs, approval tokens. |
| 3 | `CLAUDE.md` (this file) | Orchestration + general project rules. Points to the above; never restates scanning rules. |
| 4 | `docs/briefing.md` | Business context, strategy, architecture. Single source of truth for non-scanning details. |

If this file conflicts with `SCANNING_RULES.md`, follow `SCANNING_RULES.md`.

---

## Terminology

**Layer** = the type of activity:
- **Layer 1 (Passive):** Reading publicly served info (HTTP headers, HTML, DNS, SSL certs, fingerprinting). Browser-equivalent.
- **Layer 2 (Active probing):** Crafted requests, probing unlinked paths, port scanning.
- **Layer 3 (Exploitation):** Always blocked.

Without written consent, only Layer 1 is permitted. With written consent (Sentinel clients), Layer 1 + Layer 2 within the agreed scope. Full definition lives in `SCANNING_RULES.md` — do not rely on summaries elsewhere.

---

## Key Documents

| File | Contents |
|------|----------|
| `docs/briefing.md` | **Read first.** Primary context: architecture, pilot plan, go-to-market, legal framework, Danish policy. |
| `SCANNING_RULES.md` | **Authoritative** — what's allowed/forbidden per Layer/consent. Read before any scanning code change. |
| `.claude/agents/valdi/SKILL.md` | **Valdí** — legal compliance. Enforces SCANNING_RULES, validates scans, writes forensic logs. |
| `.claude/agents/README.md` | Agent system overview, handoff protocols, chain architecture. |
| `.claude/agents/osint/SKILL.md` | OSINT agent — passive fingerprinting, REST API namespaces, CSS signatures. |
| `.claude/agents/product-marketing-context.md` | Marketing context: positioning, personas, brand voice, Danish cultural constraints. |
| `.claude/agents/valdi/approvals.json` | 14-entry approval registry. Regen: `scripts/valdi/regenerate_approvals.py`. |
| `.claude/settings.json` + `.claude/hooks/` | Project-scoped settings + mechanical-enforcement hooks. See "Hook-Based Enforcement" below. |
| `docs/legal/Heimdall_Legal_Risk_Assessment.md` | Danish legal analysis under Straffeloven §263. |
| `docs/legal/compliance-checklist.md` | Compliance checklist for scanning operations. |
| `docs/legal/legal-briefing-outreach-20260414.md` | 16-question briefing (outreach + §263 + NIS2/CRA). Plesner dropped 2026-04-23; brief being re-sent to Anders Wernblad, Aumento Law. |
| `docs/legal/legal-briefing-summary-internal.md` | Internal "what hinges on legal advice" decision matrix. |
| `docs/business/heimdall-siri-application.md` | SIRI application targeting 4 scoring criteria (Innovation, Market, Scalability, Team). |
| `docs/business/siri-application-outline.md` | Outline/structure reference for the SIRI application. |
| `docs/business/marketing-strategy-draft.md` | Marketing strategy draft — channels, legal constraints, outreach plan. |
| `docs/campaign/` | Danish campaign materials: operational guide, social posts, email/DM templates. Authoritative tone doc: `marketing-keys-denmark.md`. |
| `docs/decisions/log.md` | Decision log — dated entries for architectural choices, rejections, reasoning. |
| `docs/architecture/pi5-docker-architecture.md` | Pi5 Docker stack design: containers, queues, caching, resource budget. |
| `docs/architecture/client-db-schema.sql` | Authoritative client DB schema (12 tables, 10 views, 34+ indexes). |
| `docs/design/design-system.md` | Operator console design system — tokens, colors, components, severity mapping. |
| `docs/development.md` | Mac dev workflow — prerequisites, daily loop, isolation, troubleshooting. |
| `docs/runbook-prod-deploy.md` | Deploy discipline — branch model, 6-step flow, rollback, NOT-allowed list. |
| `docs/digital-twin-use-cases.md` | Digital twin architecture, use cases, legal foundation. |
| `docs/analysis/pipeline-analysis-2026-04-05.md` | 1,173-site pipeline analysis with SIRI-ready market evidence. |
| `docs/reference/incidents/` | Post-incident reports. Read before building any scanning functionality. |
| `src/api/` | Results API + operator console (FastAPI + Svelte 5 SPA at `/app`). Router: `src/api/console.py` (REST endpoints incl. `/console/briefs/list`, V1+V6 onboarding views, retention-job interventions; WebSocket `/console/ws`). New 2026-04-26 (PR #46): `GET /console/clients/trial-expiring` (V1, `window_days=1..30`), `GET /console/clients/retention-queue` (V6, `limit/offset` paginated), `POST /console/retention-jobs/{id}/{force-run\|cancel\|retry}` — all atomic CAS UPDATEs on `retention_jobs`, audit via loguru `event=operator_retention_action` + `console:activity` Redis publish (`type='activity'` envelope), errors map `KeyError→404 / OperationalError→503 / DatabaseError→500`. Read functions live in `src/db/console_views.py`. Signup router: `src/api/signup.py` (`POST /signup/validate` — read-only magic-link check; calls `src.db.signup.get_signup_token`, never mutates state; Origin allowlist via `SIGNUP_ALLOWED_ORIGINS`, 503 if `TELEGRAM_BOT_USERNAME` env unset). Frontend: `src/api/frontend/` (Vite build → `src/api/static/dist/`). Views: Dashboard, Pipeline, Campaigns, Prospects, Briefs, **Clients (3-tab host: Onboarded \| Trial expiring \| Retention queue — tab state via `router.params.tab`)**, Logs, **Live Demo** (`src/api/frontend/src/views/LiveDemo.svelte` — brief selector with prefix search + 24/page pagination, WebSocket-driven scan replay via `demo_orchestrator.run_demo_replay`, streamed findings with typewriter effect sorted by severity desc, spotlight Assessment Complete summary), Settings. Clients sub-views in `src/api/frontend/src/views/clients/{Onboarded,TrialExpiring,RetentionQueue}.svelte`. V6 actions go through `components/ConfirmModal.svelte` (destructive style, Esc-to-cancel, busy-state lockout). Hash-based router at `src/api/frontend/src/lib/router.svelte.js` (`#/view?k=v` — `router.params` bag for deep-links; persists across refresh). Dashboard stat cards are clickable and navigate to their populated list view. **Theme:** light + dark, toggle in Topbar (`ThemeToggle.svelte` + `src/api/frontend/src/lib/theme.svelte.js`), defaults to `prefers-color-scheme`, override persists in `localStorage['heimdall.theme']`. Design system at `docs/design/design-system.md` v1.3 (warm-only severity in both themes, 11 type utility classes incl. `.t-help` for explanatory prose). |
| `apps/signup/` | SvelteKit signup site (slice 1 dev-ready 2026-04-25; bilingual toggle + Telegram-only positioning shipped 2026-04-26 in PR #45). Independent of `src/api/frontend/` — own `package.json`, `node_modules`, `vite.config.js`. Adapter-static; Vite dev server `:5173` proxies `/api/*` → host `:8001` (dev FastAPI host port). Six routes: `/`, `/pricing`, `/legal/{privacy,terms,dpa}`, `/signup/start?t=<token>` (magic-link landing — calls `POST /api/signup/validate`, renders Telegram CTA + QR, strips token from URL via `history.replaceState(history.state, ...)` to preserve SvelteKit router state). Tokens copied verbatim from `src/api/frontend/src/styles/tokens.css`. i18n in `src/lib/i18n.js` — `t` is a Svelte derived store invoked as `$t(key)`; `locale` writable + `setLocale`/`initLocale` (precedence: URL `?lang=` > `localStorage['signup.locale']` > default `en`; EN-fallback when DA missing). Topbar carries `LocaleToggle.svelte` (EN \| DA). Home-page sections grid order: `howitworks → whatwemonitor → why_telegram → pricing → faq`. API wrapper in `src/lib/api.js`. Pricing reads `src/lib/pricing.json` (i18n key references in `tagline` + `features[]`) — single Sentinel plan, 30-day free trial as a feature (no client-facing "Watchman" codename). Vitest 21/21 (`make signup-test`). Browser-eyeball QA still needed; visual tune-up deferred. |
| `src/consent/validator.py` | Consent validator — Gate 2 enforcement, fail-closed on all error paths. |
| `src/interpreter/` | Finding Interpreter (Claude API / Ollama). Tier-aware: Watchman explanation-only, Sentinel adds fix instructions. Cache: `src/interpreter/cache.py` (sha256 of findings+tier+lang+prompt; 3.8× API-call savings). |
| `src/composer/telegram.py` | Telegram HTML composer. Severity labels, confirmed/potential split, 4096-char auto-splitting. |
| `src/delivery/` | Telegram bot. Subscribes to Redis `client-scan-complete`, interprets → composes → sends. Client button = single "Got it" (`src/delivery/buttons.py`). |
| `src/prospecting/` | Lead-gen pipeline (CVR → domain → bucketing → brief). Scanners in `src/prospecting/scanners/`. |
| `src/prospecting/scanners/` | Scanner package. Shared: `models`, `registry`, `runner`, `compliance`. One module per tool: tls, headers, robots, httpx, webanalyze, subfinder, dnsx, ct, grayhat, nuclei, cmseek, nmap, wordpress. |
| `src/core/` | Shared infra: `config.py`, `logging_config.py` (loguru), `exceptions.py`, `secrets.py` (`get_secret` with `/run/secrets/` priority + env fallback). |
| `src/worker/` | Worker process. Executes scan jobs, manages caching, runs twin scans. Pydantic validation: `src/worker/models.py`. |
| `src/scheduler/` | Scan-job creator + daemon. `--mode daemon` = BRPOP on `queue:operator-commands`, dispatches pipeline/interpret/send, publishes progress to Redis pub/sub. Hosts the CT-monitor timer + the retention-execution timer (300s cadence) — both go through `_resolve_retention_db_path()` for the same DB-path precedence as `init_db` (no dev/prod drift). |
| `src/db/` | Client SQLite DB (CRUD). Schema: `docs/architecture/client-db-schema.sql`. DB: `data/clients/clients.db`. Migration: `src/db/migrate.py` (auto-applied by `init_db` since PR #39). Onboarding modules: `src/db/signup.py` (magic-link token handshake — 30-min TTL, single-use; nulls `email` at consumption per GDPR Art 5(1)(e)), `src/db/subscriptions.py` (Sentinel subscriptions + Betalingsservice `payment_events` append log, øre integer math), `src/db/conversion.py` (conversion_events funnel log + onboarding_stage_log; 17 event-types including the 7-row Sentinel consent audit trail per Q5), `src/db/retention.py` (`schedule_churn_retention` tiered policy per D16 revised: Watchman immediate hard-purge, Sentinel 30d anonymise + 5y `purge_bookkeeping`; plus `claim_due_retention_jobs` / `reap_stuck_running_jobs` claim-lock helpers for the cron), `src/db/onboarding.py` (`activate_watchman_trial` — atomic single-transaction signup→Watchman activation: token consume, client upsert, trial window, conversion event, forensic logline). |
| `src/retention/` | Retention-execution cron (D16 enforcement). `runner.py` — `tick()`: reap stuck claims, atomically claim due rows, dispatch action handlers via `_emit_event_in_txn` (audit writes commit alongside the action, not before), exponential backoff (15m/1h/4h/24h/terminal) with operator Telegram alert on attempt 5, re-fetches each claimed row before dispatch (defends against intra-tick sibling-purge cascades), skips DRYRUN- CVRs. `actions.py` — `anonymise_client` (Sentinel only; nulls scraped-PII columns including `prospects.brief_json`/`interpreted_json`/`error_message`; preserves `consent_records` structured PII per Valdí §263 ruling), `purge_client` (hard-delete cascade, two-tier path-traversal guard with distinct `retention_fs_base_dir_rejected` + `retention_fs_path_escape_rejected` log events), `purge_bookkeeping` (Sentinel +5y delete of subscriptions + payment_events). |
| `src/client_memory/` | Client history, delta detection. `ct_monitor.py` = Sentinel CT monitoring (CertSpotter daily poll, post-commit publish since PR #40). `trial_expiry.py` = Watchman trial-expiry scanner: `find_expired_trials` / `expire_watchman_trial` (CAS UPDATE returns `(client, transitioned)` so multi-worker races don't over-count) / `run_trial_expiry_sweep` (skips `DRYRUN-` CVRs) / `reconcile_watchman_expired_orphans` (catches drift between status flip and retention schedule). |
| `src/logging/redis_sink.py` | Shared loguru sink → Redis `console:logs`. `HEIMDALL_SOURCE` env var per container. |
| `src/client_memory/` | Client history, delta detection. `ct_monitor.py` = Sentinel CT monitoring (CertSpotter daily poll, post-commit publish since PR #40). |
| `src/enrichment/` | CVR enrichment (7-step pipeline). Outputs to `data/enriched/companies.db`. Entry: `python -m src.enrichment`. |
| `src/vulndb/` | CVE lookups: `lookup.py` (WPVulnerability API), `wp_versions.py` (WordPress.org), `rss_cve.py` (Wordfence/CISA/Bleeping Computer RSS), `kev.py` (CISA KEV → `[ACTIVELY EXPLOITED]` marker), `cache.py`. |
| `src/outreach/` | Batch commands: `promote`/`interpret`/`send`/`export`. Entry: `python -m src.outreach <cmd> --campaign MMYY-industry`. |
| `Makefile` | Mac dev ergonomics. Lifecycle, seed, tests, `dev-ops-smoke`, `dev-cert-dry-run`, `dev-interpret-dry-run`, `signup-{dev,build,test,verify,issue-token}` (SvelteKit signup site). See `docs/development.md`. |
| `infra/compose/docker-compose.dev.yml` | Dev stack overlay (Mac). `make dev-up` uses project `-p heimdall_dev`. |
| `.github/workflows/` | CI: `publish-images.yml` (5 arm64 images → GHCR on push to main), `prune-ghcr.yml` (monthly retention of last 30 SHAs/service). |
| `.githooks/pre-push` | Refuses `git push origin prod` unless `HEIMDALL_APPROVED=1`. Activate: `git config core.hooksPath .githooks`. |
| `scripts/backup.sh` | Atomic SQLite backup. Honors `HEIMDALL_BACKUP_DIR` (Pi5 microSD). Cron 03:00 daily. |
| `scripts/healthcheck.sh` | Cron (5 min) — docker inspect health + restart counts, Telegram alert on failure. |
| `scripts/migrate_env_to_secrets.sh` | Idempotent split of `.env` credentials → per-secret files. Auto-invoked by `make dev-secrets`. |
| `scripts/valdi/regenerate_approvals.py` | Valdí token regen. `--apply` writes; dry-run by default. Use after any refactor that changes function source. |
| `scripts/analyze_pipeline.py` + `scripts/analyze_stats.py` | Pipeline + deep-stats analysis. `--deep` for full breakdown + outreach prioritization. |
| `scripts/audit.py` | Project audit — Dockerfile, compose, tests, configs, known gaps. |
| `scripts/preview_message.py` | Message preview. `--send` delivers to operator's Telegram (bypasses Redis/approval/DB). |
| `scripts/test_delivery.py` + `scripts/test_telegram_e2e.py` | E2E delivery tests (Telethon-based E2E auto-clicks buttons and verifies). |
| `scripts/dev/seed_dev_db.py` | Dev DB seed from `config/dev_dataset.json` (30-site fixture). `--check` verifies without writing. Writes host-only `data/dev/clients.db` (offline analysis); the dev container's `/data/clients/clients.db` lives in the `heimdall_dev_client-data` named volume and is NOT touched by this script. |
| `scripts/dev/seed_dev_briefs.py` | Copies the 30 fixture brief JSONs from `data/output/briefs/` to `data/dev/briefs/` so the api container's bind-mount serves only fixture data. Idempotent (prunes stray `*.json` on re-run). Fail-loud on missing source briefs or empty dataset. `--check` for dry mode. Run via `make dev-fixture-bootstrap`. |
| `scripts/dev/seed_dev_enriched.py` | Filters the prod `data/enriched/companies.db` to the 30 fixture domains, writes `data/dev/enriched/companies.db` preserving `companies` + `domains` schema (skips `enrichment_log`). Normalises `domains.ready_for_scan = 1` so prod quarantine flags can't shrink the dev pipeline below 30. `--check` for dry mode. Run via `make dev-fixture-bootstrap`. |
| `data/dev/{briefs,enriched,input,results}/` | Dev fixture bind-mount targets, gitignored. PROD's `infra/compose/docker-compose.yml` parameterises the four host bind-mounts as `${INPUT_HOST_DIR:-../../data/input}` etc.; `.env.dev` overrides each to a `data/dev/*` sibling so DEV containers never read prod data. Populated by `make dev-fixture-bootstrap` (auto-runs as a prereq of `make dev-up`); `make dev-fixture-refresh` for explicit re-pull, `make dev-fixture-check` for `--check` validation across all seeders. M37 finalisation, PR #47. |
| `scripts/dev/cert_change_dry_run.py` | Sentinel cert-change dry run. `make dev-cert-dry-run`. Synthetic target, no Telegram send. ~10s. |
| `scripts/dev/interpret_dry_run.py` | M33 interpret dry run. `make dev-interpret-dry-run`. `MODE=observe\|send-to-operator`. CI cost guard. |
| `scripts/dev/verify_signup_slice1.py` | SvelteKit signup-site slice-1 backend verifier. `make signup-verify`. Issues a synthetic-CVR token (`DRYRUN-VERIFY-SIGNUP`), POSTs `/signup/validate`, asserts read-only contract + invalid-token branch. Runs inside dev `delivery` container (RW client-data + scripts mounted). |
| `scripts/dev/issue_signup_token.py` | Issues a fresh signup token bound to `DRYRUN-BROWSER` and prints the `/signup/start?t=<token>` URL. `make signup-issue-token`. For browser-eyeball QA of the magic-link landing. |
| `config/filters.json` | Configurable pipeline filters (industry_code, contactable, bucket). |
| `config/industry_codes.json` | Static: industry code → English name mapping. |
| `config/interpreter.json` | LLM backend, model, tone, default language. Per-client override via `clients.preferred_language`. |
| `config/delivery.json` | Telegram delivery settings (require_approval, retry, rate limit). |
| `config/monitoring.json` | CT monitoring schedule. Read by scheduler daemon at startup. |
| `config/consent_schema.json` | Consent authorisation JSON schema. |
| `config/synthetic_targets.json` | Synthetic target registry for twin consent bypass. |
| `config/dev_dataset.json` | Static 30-site dev fixture (5 worst × 6 hosting buckets). |
| `config/ct_dry_run.json` + `config/interpret_dry_run.json` | Configs for the two dev dry-run scripts. |
| `data/input/CVR-extract.xlsx` | Input: manually-extracted CVR company list. Not committed. |
| `data/enriched/companies.db` | SQLite: pre-enriched CVR data. Scheduler auto-detects and skips the legacy Excel pipeline. |
| `data/clients/clients.db` | SQLite: client management DB. Created by `src/db/connection.init_db()`. |
| `data/output/prospects-list.csv` + `data/output/briefs/{domain}.json` | Pipeline outputs. |
| `tools/twin/slug_map.json` | Plugin/theme slug → version mapping for twin reconstruction. |

---

## Scanning Workflow

All scanning code passes through Valdí before execution:

1. Write or modify a scanning function
2. Submit to Valdí (Gate 1) — scan-type validation against `SCANNING_RULES.md`
3. If rejected: Valdí logs the rejection with reasoning. Rewrite. No execution.
4. If approved: Valdí logs the approval, generates an approval token, registers the scan type
5. Federico reviews and gives final go-ahead
6. Execute the scan, referencing the approval token

Before a scan batch runs, Valdí does a Gate 2 check: approval token valid + target's consent state permits the scan's Layer.

**No scanning code executes without a valid Valdí approval token.** This applies to new code and all existing code (backfill through Valdí before further use).

The pipeline: CVR Excel → pre-scan filters (`config/filters.json`) → domain resolution (robots.txt honored) → Layer 1 scan (Valdí-approved: httpx, webanalyze, subfinder, dnsx, crt.sh, GrayHatWarfare, WordPress passive detection) → bucketing A>B>E>C>D (see `.claude/agents/prospecting/SKILL.md`) → GDPR + agency detection → per-site briefs → WordPress twin-derived Layer 2 + WPVulnerability lookups. Full details: `docs/briefing.md` + `docs/architecture/pi5-docker-architecture.md`.

---

## Build Priority: Stage A Foundation → Stage A.5 Control-Plane Guarantees → V2 Onboarding

**Status (2026-04-28):** 1,471 unit tests passing on `feat/stage-a-foundation`, coverage above the 65% floor. Sentinel onboarding backend (signup-token magic-link, `activate_watchman_trial`, Telegram `/start <token>`, `src/db/conversion.py` + `src/db/retention.py` + `src/db/onboarding.py`, `src/retention/` execution cron, trial-expiry scanner + reconciler, Valdí-cleared §263 evidence preservation) fully landed in the prior `feat/sentinel-onboarding` cycle. The active branch advances Stage A's auth-plane carve per `docs/architecture/stage-a-implementation-spec.md`. Slices shipped: 1 (decision-log + spec hardening), 2 (argon2-cffi + `_seed_operator_zero`), 3a (session ticket lifecycle), 3b (`console.audit_log` writer), 3c (per-IP login rate limiter), 3d (`SessionAuthMiddleware` HTTP-only ASGI module + tests), 3e (auth router `/console/auth/{login,logout,whoami}` + harmonised response shape + middleware disabled-operator audit hook). Remaining: 3f (`LegacyBasicAuthMiddleware` rename + `HEIMDALL_LEGACY_BASIC_AUTH=1` env flag + `SessionAuthMiddleware` mount in `create_app` + `git mv tests/test_console_auth.py tests/test_session_auth.py` with cookie-flow rewrite). `main` still on the 2026-04-18 hardening baseline; the active feature branch is far ahead. **Pilot launch blocked by SIRI approval, not by code.** Next critical-path after Stage A: A.5 (`Permission` enum + `require_permission` decorator + X-Request-ID middleware + `config_changes` triggers + `/console/config/history`) → V2 onboarding view.

Full sprint history, per-PR scope, and any unresolved threads live in `docs/decisions/log.md` and `data/project-state.json`. Do not duplicate here.

---

## Do Not

- Do not write or run scanning code without a valid Valdí approval token.
- Do not scan, probe, or make automated requests to a domain whose `robots.txt` denies automated access. Hard skip, log, move on. All layers including Layer 1. No exceptions.
- Do not overengineer solutions (Occam's razor principle).
- Do not restate scanning rules from `SCANNING_RULES.md` in other documents — reference the source.
- Do not write client-facing text mentioning Raspberry Pi, specific hardware, or internal infrastructure. Use abstract language ("dedicated secure infrastructure", "cloud-based AI interpretation layer").
- Do not store API keys, tokens, or secrets in any committed file.
- Do not modify files in `.claude/agents/` without explicit instruction.
- Do not duplicate business data (pricing, statistics, policy figures) that already exists in `docs/briefing.md` — reference the briefing.
- Do not modify code without running `git pull` first.
- Features → branch + PR. Bug fixes → direct to `main`.
- Do not create large monolithic commits — commit logically grouped changes separately with descriptive messages.
- Do not add or remove a scanning tool without updating the tool table in `docs/briefing.md` in the same commit.
- Do not make business, architecture, or technical decisions — present options with trade-offs, Federico decides.

---

## Hook-Based Enforcement (`.claude/hooks/`)
Do not overengineer solutions (Occam's razor principle).
Hooks defined in `.claude/settings.json`. **Mechanical enforcement** for rules that repeatedly failed as passive memory. They run in the harness, cannot be bypassed by model intent, and take precedence over anything in this file.

| Hook | Event | Behaviour |
|------|-------|-----------|
| `infra_danger_zone.py` | PreToolUse / `Edit\|Write` | Injects decision-log matches as context when editing infra files (`.gitignore`, `.env*`, compose, `Dockerfile*`, `infra/`, `.github/`, `pyproject.toml`, `requirements.txt`, `CLAUDE.md`, `SCANNING_RULES.md`, `.pre-commit-config.yaml`, `scripts/*.sh`). Non-blocking. |
| `destructive_git_guard.py` | PreToolUse / `Bash` | Blocks `git reset --hard`, `git checkout --`, `git restore .`, `git clean -f`, `git branch -D`, `git push --force`. Shlex-tokenized (danger strings in quoted args don't false-match). |
| `secret_exposure_guard.py` | PreToolUse / `Bash` | Blocks `source .env`, `cat .env`, bare `env`/`printenv`, `echo $*_KEY/*_TOKEN/*_SECRET/*_PASSWORD`. |
| `inline_script_guard.py` | PreToolUse / `Bash` | Soft-blocks inline `python -c` / `node -e` scripts > 150 chars or multi-line. |
| `main_branch_push_guard.py` | PreToolUse / `Bash` | Soft-blocks `git push origin main` when local commits contain `src/**/*.py` changes. |
| `precommit_codex_review_guard.py` | PreToolUse / `Bash` | Soft-blocks `git commit` when the staged diff includes `src/**/*.py` or `tests/**/*.py` and the command is missing the `HEIMDALL_CODEX_REVIEWED=1` self-attestation prefix. Forces a conscious "did I run Codex first?" before any Python commit. |
| `ci_config_reminder.py` | PostToolUse / `Edit\|Write` | Reminder to push + `gh run watch` after editing CI/dep files. |
| `session_start_context.py` | SessionStart | Injects current branch, `git status`, recent commits, latest decision-log headline, top rules. |

**Known limitations.** shlex doesn't understand shell heredocs — `git commit -F - <<'EOF'` with dangerous text in the body can false-fire the destructive/secret guards. Workaround: write the message to a tempfile, use `git commit -F /tmp/msg.txt`. Hooks run per tool call; multi-step plans may hit the same hook multiple times (intended — re-injection).

**When a hook misfires.** Either the hook is right and you were about to do something wrong (reconsider), or the hook has a bug (fix the script, test against the misfire, commit the fix). Never silently skip or phrase around it.

---

## Content & Copywriting

- **Pricing always in kr. (Danish kroner)**, not euros.
- **Recurring example:** "restaurant with online booking system" — not "bakery owner".
- **No phrases like** "stated honestly", "full transparency", "to be honest" — confidence is implicit.
- **Citations:** numbered superscripts → References section at end (not inline "Source: ...").
- **All scanning tool references** must include GitHub repository links.
- **For policy data, statistics, and pricing** — pull from `docs/briefing.md`, do not rely on memory.

---

## MCP Tools: code-review-graph

**Always use graph tools before Grep/Glob/Read** — faster, cheaper, gives structural context (callers, tests, impact) file scans can't.

- Exploring code → `semantic_search_nodes`, `query_graph`
- Impact analysis → `get_impact_radius`, `get_affected_flows`
- Code review → `detect_changes`, `get_review_context`
- Relationships → `query_graph` with `callers_of`/`callees_of`/`imports_of`/`tests_for`
- Architecture → `get_architecture_overview`, `list_communities`

Graph auto-updates on file changes (via hooks). Fall back to Grep/Glob/Read only when the graph doesn't cover what you need.

---

MANDATORY: Before performing any task, determine which agent(s) from `.claude/agents/` own this task. Read their SKILL.md. Do not proceed without confirming you are operating within that agent's stated boundaries and responsibilities.
