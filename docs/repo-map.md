# Repo Map

Directory index for Heimdall. CLAUDE.md keeps the always-needed pointers; this file documents the rest of the tree so the model has somewhere to look without expanding CLAUDE.md back into a status doc.

When a directory's purpose changes, update the row here. When a row is wrong or stale, fix or delete it. This file is allowed to drift slightly behind a one-off rename — `ls` is the source of truth for what exists; this file is the source of truth for *why* it exists.

---

## docs/

| File | Contents |
|------|----------|
| `docs/briefing.md` | **Read first.** Primary context: architecture, pilot plan, go-to-market, legal framework, Danish policy. |
| `docs/development.md` | Mac dev workflow — prerequisites, daily loop, isolation, troubleshooting. |
| `docs/runbook-prod-deploy.md` | Deploy discipline — branch model, 6-step flow, rollback, NOT-allowed list. |
| `docs/decisions/log.md` | Decision log — dated entries for architectural choices, rejections, reasoning. |
| `docs/digital-twin-use-cases.md` | Digital twin architecture, use cases, legal foundation. |
| `docs/analysis/pipeline-analysis-2026-04-05.md` | 1,173-site pipeline analysis with SIRI-ready market evidence. |
| `docs/reference/incidents/` | Post-incident reports. Read before building any scanning functionality. |
| `docs/architecture/pi5-docker-architecture.md` | Pi5 Docker stack design: containers, queues, caching, resource budget. |
| `docs/architecture/client-db-schema.sql` | Authoritative client DB schema (12 tables, 10 views, 34+ indexes). |
| `docs/architecture/console-db-schema.sql` | Console DB schema (D2 split — operators / sessions / console.audit_log). |
| `docs/architecture/stage-a-implementation-spec.md` | **Stage A master spec** — auth-plane carve. Cite by section number from per-slice specs; never restate contracts. §3 (auth router), §4 (security), §5 (WS auth), §6 (router layout), §7 (audit), §8 (test plan), §9 (rollback), §11 (out of scope). |
| `docs/architecture/stage-a-slice-3g-spec.md` | Stage A slice 3g spec. SPA login + whoami bootstrap + CSRF helper + handler-level WS auth + legacy retirement per §7.10 Option B. |
| `docs/design/design-system.md` | Operator console design system — tokens, colors, components, severity mapping. |
| `docs/legal/Heimdall_Legal_Risk_Assessment.md` | Danish legal analysis under Straffeloven §263. |
| `docs/legal/compliance-checklist.md` | Compliance checklist for scanning operations. |
| `docs/legal/legal-briefing-outreach-20260414.md` | 16-question briefing (outreach + §263 + NIS2/CRA). |
| `docs/legal/legal-briefing-summary-internal.md` | Internal "what hinges on legal advice" decision matrix. |
| `docs/business/heimdall-siri-application.md` | SIRI application targeting 4 scoring criteria (Innovation, Market, Scalability, Team). |
| `docs/business/siri-application-outline.md` | Outline / structure reference for the SIRI application. |
| `docs/business/marketing-strategy-draft.md` | Marketing strategy draft — channels, legal constraints, outreach plan. |
| `docs/campaign/` | Danish campaign materials: operational guide, social posts, email/DM templates. Authoritative tone doc: `marketing-keys-denmark.md`. |

---

## .claude/

| File | Contents |
|------|----------|
| `.claude/agents/README.md` | Agent system overview, handoff protocols, chain architecture. |
| `.claude/agents/valdi/SKILL.md` | **Valdí** — legal compliance. Enforces SCANNING_RULES, validates scans, writes forensic logs. |
| `.claude/agents/valdi/approvals.json` | 14-entry approval registry. Regen: `scripts/valdi/regenerate_approvals.py`. |
| `.claude/agents/osint/SKILL.md` | OSINT agent — passive fingerprinting, REST API namespaces, CSS signatures. |
| `.claude/agents/product-marketing-context.md` | Marketing context: positioning, personas, brand voice, Danish cultural constraints. |
| `.claude/settings.json` + `.claude/hooks/` | Project-scoped settings + mechanical-enforcement hooks. See CLAUDE.md "Hook contracts". |

---

## src/

| File | Contents |
|------|----------|
| `src/api/` | Results API + operator console (FastAPI + Svelte 5 SPA at `/app`). REST endpoints in `src/api/console.py`; WebSocket `/console/ws`; signup router `src/api/signup.py`; auth router `src/api/routers/auth.py`; session middleware `src/api/auth/middleware.py`; audit writer `src/api/auth/audit.py`. Frontend at `src/api/frontend/` (Vite → `src/api/static/dist/`). |
| `src/api/frontend/` | Operator console SPA (Svelte 5). Views: Dashboard, Pipeline, Campaigns, Prospects, Briefs, Clients (3-tab host: Onboarded / Trial expiring / Retention queue), Logs, Live Demo, Settings, Login. Hash-based router at `src/lib/router.svelte.js`. Auth state machine at `src/lib/auth.svelte.js`. Theme toggle (light + dark) persists in `localStorage['heimdall.theme']`. |
| `apps/signup/` | SvelteKit signup site, independent of `src/api/frontend/`. Adapter-static; Vite dev server `:5173` proxies `/api/*` → host `:8001`. Routes: `/`, `/pricing`, `/legal/{privacy,terms,dpa}`, `/signup/start?t=<token>`. i18n via `src/lib/i18n.js` (EN + DA). Tests: `make signup-test`. |
| `src/consent/validator.py` | Consent validator — Gate 2 enforcement, fail-closed on all error paths. |
| `src/interpreter/` | Finding Interpreter (Claude API / Ollama). Tier-aware: Watchman explanation-only, Sentinel adds fix instructions. Cache: `src/interpreter/cache.py`. |
| `src/composer/telegram.py` | Telegram HTML composer. Severity labels, confirmed/potential split, 4096-char auto-splitting. |
| `src/delivery/` | Telegram bot. Subscribes to Redis `client-scan-complete`, interprets → composes → sends. Single "Got it" client button. |
| `src/prospecting/` | Lead-gen pipeline (CVR → domain → bucketing → brief). Scanners in `src/prospecting/scanners/`. |
| `src/prospecting/scanners/` | Scanner package. Shared: `models`, `registry`, `runner`, `compliance`. One module per tool: tls, headers, robots, httpx, webanalyze, subfinder, dnsx, ct, grayhat, nuclei, cmseek, nmap, wordpress. |
| `src/core/` | Shared infra: `config.py`, `logging_config.py` (loguru), `exceptions.py`, `secrets.py` (`get_secret` with `/run/secrets/` priority + env fallback). |
| `src/worker/` | Worker process. Executes scan jobs, manages caching, runs twin scans. Pydantic validation: `src/worker/models.py`. |
| `src/scheduler/` | Scan-job creator + daemon. `--mode daemon` = BRPOP on `queue:operator-commands`. Hosts CT-monitor + retention-execution timers. |
| `src/db/` | Client SQLite DB (CRUD). Schema: `docs/architecture/client-db-schema.sql`. DB: `data/clients/clients.db`. Migration auto-applied by `init_db`. Onboarding modules: `signup.py`, `subscriptions.py`, `conversion.py`, `retention.py`, `onboarding.py`. |
| `src/retention/` | Retention-execution cron (D16 enforcement). `runner.py` — `tick()` claim-and-dispatch. `actions.py` — `anonymise_client`, `purge_client`, `purge_bookkeeping`. |
| `src/client_memory/` | Client history, delta detection. `ct_monitor.py` = Sentinel CT monitoring. `trial_expiry.py` = Watchman trial-expiry scanner + reconciler. |
| `src/logging/redis_sink.py` | Shared loguru sink → Redis `console:logs`. `HEIMDALL_SOURCE` env var per container. |
| `src/enrichment/` | CVR enrichment (7-step pipeline). Outputs to `data/enriched/companies.db`. Entry: `python -m src.enrichment`. |
| `src/vulndb/` | CVE lookups: `lookup.py` (WPVulnerability API), `wp_versions.py` (WordPress.org), `rss_cve.py` (Wordfence/CISA/Bleeping Computer RSS), `kev.py` (CISA KEV), `cache.py`. |
| `src/outreach/` | Batch commands: `promote` / `interpret` / `send` / `export`. Entry: `python -m src.outreach <cmd> --campaign MMYY-industry`. |

---

## infra/

| File | Contents |
|------|----------|
| `infra/compose/docker-compose.yml` | Production compose stack. Bind-mount paths parameterised via `${INPUT_HOST_DIR}` etc. so dev can override. |
| `infra/compose/docker-compose.dev.yml` | Dev stack overlay (Mac). `make dev-up` uses project `-p heimdall_dev`. |
| `.github/workflows/` | CI: `publish-images.yml` (5 arm64 images → GHCR on push to main), `prune-ghcr.yml` (monthly retention of last 30 SHAs/service). |
| `.githooks/pre-push` | Refuses `git push origin prod` unless `HEIMDALL_APPROVED=1`. Activate: `git config core.hooksPath .githooks`. |

---

## scripts/

| File | Contents |
|------|----------|
| `scripts/backup.sh` | Atomic SQLite backup. Honors `HEIMDALL_BACKUP_DIR` (Pi5 microSD). Cron 03:00 daily. |
| `scripts/healthcheck.sh` | Cron (5 min) — docker inspect health + restart counts, Telegram alert on failure. |
| `scripts/migrate_env_to_secrets.sh` | Idempotent split of `.env` credentials → per-secret files. Auto-invoked by `make dev-secrets`. |
| `scripts/valdi/regenerate_approvals.py` | Valdí token regen. `--apply` writes; dry-run by default. Use after any refactor that changes function source. |
| `scripts/analyze_pipeline.py` + `scripts/analyze_stats.py` | Pipeline + deep-stats analysis. `--deep` for full breakdown + outreach prioritization. |
| `scripts/audit.py` | Project audit — Dockerfile, compose, tests, configs, known gaps. |
| `scripts/preview_message.py` | Message preview. `--send` delivers to operator's Telegram (bypasses Redis/approval/DB). |
| `scripts/test_delivery.py` + `scripts/test_telegram_e2e.py` | E2E delivery tests (Telethon-based E2E auto-clicks buttons and verifies). |
| `scripts/dev/seed_dev_db.py` | Dev DB seed from `config/dev_dataset.json` (30-site fixture). `--check` verifies without writing. |
| `scripts/dev/seed_dev_briefs.py` | Copies the 30 fixture brief JSONs to `data/dev/briefs/`. Idempotent. Run via `make dev-fixture-bootstrap`. |
| `scripts/dev/seed_dev_enriched.py` | Filters prod `data/enriched/companies.db` to the 30 fixture domains. Run via `make dev-fixture-bootstrap`. |
| `scripts/dev/cert_change_dry_run.py` | Sentinel cert-change dry run. `make dev-cert-dry-run`. Synthetic target, no Telegram send. |
| `scripts/dev/interpret_dry_run.py` | M33 interpret dry run. `make dev-interpret-dry-run`. `MODE=observe \| send-to-operator`. CI cost guard. |
| `scripts/dev/verify_signup_slice1.py` | SvelteKit signup-site slice-1 backend verifier. `make signup-verify`. |
| `scripts/dev/issue_signup_token.py` | Issues a fresh signup token bound to `DRYRUN-BROWSER` and prints the `/signup/start?t=<token>` URL. `make signup-issue-token`. |

---

## config/

| File | Contents |
|------|----------|
| `config/filters.json` | Configurable pipeline filters (industry_code, contactable, bucket). |
| `config/industry_codes.json` | Static: industry code → English name mapping. |
| `config/interpreter.json` | LLM backend, model, tone, default language. Per-client override via `clients.preferred_language`. |
| `config/delivery.json` | Telegram delivery settings (require_approval, retry, rate limit). |
| `config/monitoring.json` | CT monitoring schedule. Read by scheduler daemon at startup. |
| `config/consent_schema.json` | Consent authorisation JSON schema. |
| `config/synthetic_targets.json` | Synthetic target registry for twin consent bypass. |
| `config/dev_dataset.json` | Static 30-site dev fixture (5 worst × 6 hosting buckets). |
| `config/ct_dry_run.json` + `config/interpret_dry_run.json` | Configs for the two dev dry-run scripts. |

---

## data/

| File | Contents |
|------|----------|
| `data/input/CVR-extract.xlsx` | Input: manually-extracted CVR company list. Not committed. |
| `data/enriched/companies.db` | SQLite: pre-enriched CVR data. Scheduler auto-detects and skips the legacy Excel pipeline. |
| `data/clients/clients.db` | SQLite: client management DB. Created by `src/db/connection.init_db()`. |
| `data/output/prospects-list.csv` + `data/output/briefs/{domain}.json` | Pipeline outputs. |
| `data/dev/{briefs,enriched,input,results}/` | Dev fixture bind-mount targets, gitignored. Populated by `make dev-fixture-bootstrap`. |

---

## tools/

| File | Contents |
|------|----------|
| `tools/twin/slug_map.json` | Plugin/theme slug → version mapping for twin reconstruction. |

---

## Top-level

| File | Contents |
|------|----------|
| `Makefile` | Mac dev ergonomics. Lifecycle, seed, tests, `dev-ops-smoke`, `dev-cert-dry-run`, `dev-interpret-dry-run`, `signup-{dev,build,test,verify,issue-token}`. See `docs/development.md`. |
| `SCANNING_RULES.md` | Authoritative — what's allowed/forbidden per Layer & consent state. |
| `CLAUDE.md` | Orchestration + general project rules. Points here for repo detail. |
