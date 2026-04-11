# MVP Hardening — Design Spec

**Date:** 2026-04-11
**Goal:** Move Heimdall from Late Prototype to Pilot-Ready MVP (5 Vejle clients)
**Approach:** Two phases — Phase 1 (Safe to Operate) changes no application architecture; Phase 2 (Safe to Maintain) refactors with CI safety net in place.

---

## Phase 1: Safe to Operate

**Question this phase answers:** "Can I sleep the night after onboarding client #1?"

### 1.1 — Git Hygiene

- Add to `.gitignore`: `data/**/*.db`, `*.key`, `*.pem`, `*.env.*`, `secrets/`
- Path-specific DB ignore (not global `*.db`) to avoid ignoring test fixtures
- Verify no SQLite databases are tracked (`git ls-files '*.db'`)
- Pin Dozzle to a specific tag in `docker-compose.yml` (replace `latest`)

### 1.2 — CI Pipeline

Moved early — protects every subsequent change.

**Pre-commit hooks** (`.pre-commit-config.yaml`):
- `ruff check`
- `ruff format --check`

**Pre-push hook**:
- `pytest tests/ -x -q` with `pytest-timeout` plugin for per-test timeout (confirm in dev deps)

**GitHub Actions** (`.github/workflows/ci.yml`):
- Trigger: push and PR to `main`
- Matrix: Python 3.11
- Steps: checkout, setup Python, `pip install uv && uv sync`, `ruff check`, `ruff format --check`, `pytest -x --tb=short`
- Quality gate only — no deployment

### 1.3 — Bug Fixes

Each is a one-file fix for a real bug found during audit.

| # | Bug | File | Fix |
|---|-----|------|-----|
| 1 | **Scheduler daemon crash** — `_publish_result()` inside `except Exception` has no guard; Redis failure during error handling kills the daemon | `scheduler/daemon.py:73` | Wrap `_publish_result` in try/except with stderr fallback |
| 2 | **Worker BRPOP spin-loop** — Redis disconnect causes `continue` with no sleep, CPU spins at 100% | `worker/main.py:293` | Add exponential backoff: `time.sleep(min(2 ** consecutive_failures, 30))`, reset on success |
| 3 | **Delivery runner deaf after one Redis failure** — tries one resubscribe, then `except ConnectionError: pass` forever | `delivery/runner.py:147-150` | Replace with reconnection loop using backoff `[1, 2, 5, 10, 30]` (matches API pattern) |
| 4 | **Telegram Forbidden/BadRequest unhandled** — bot blocked or invalid chat_id causes unhandled exception, delivery event lost | `delivery/sender.py:57` | Catch `Forbidden` and `BadRequest` explicitly, mark delivery `permanently_failed` with reason |
| 5 | **request_approval() no error handling** — operator chat_id wrong or network error silently drops scan event | `delivery/approval.py:109` | Wrap in try/except, log error, mark `approval_failed` |
| 6 | **feedparser blocks indefinitely** — RSS feed server hangs, worker thread blocks with no timeout | `vulndb/rss_cve.py:129` | Set `socket.setdefaulttimeout(30)` before parse, restore after |
| 7 | **Slug map silent failure** — `except Exception: return {}` with no logging | `worker/scan_job.py:103` | Add `logger.warning("slug_map_load_failed", exc_info=True)` |
| 8 | **Opaque scheduler console errors** — always shows "Command failed — check logs" | `scheduler/daemon.py:73` | Bind exception to `exc`, publish `str(exc)` to console |

### 1.4 — Delivery Resilience

**Problem:** A scan completes but the client never gets a message, and nobody knows. Claude API timeout, Telegram error, or Redis blip — the event is permanently lost.

**Solution:** Lightweight retry table in `clients.db`:

```sql
CREATE TABLE delivery_retry (
    id INTEGER PRIMARY KEY,
    delivery_log_id INTEGER REFERENCES delivery_log(id),
    domain TEXT NOT NULL,
    brief_path TEXT NOT NULL,
    attempt INTEGER DEFAULT 0,
    next_retry_at TEXT NOT NULL,
    last_error TEXT,
    status TEXT DEFAULT 'pending',  -- pending | exhausted
    created_at TEXT DEFAULT (datetime('now'))
);
```

**Behavior:**
- On interpretation or send failure: insert into `delivery_retry` instead of returning silently
- Retry coroutine in the delivery runner's existing async loop: runs every 15 minutes
- Picks up entries where `next_retry_at <= now() AND status = 'pending' AND attempt < 3`
- Exponential backoff: retry at +15min, +1hr, +4hr
- After 3 failures: set `status = 'exhausted'`, send Telegram to **operator**: "Delivery to {client} failed 3 times: {last_error}"
- On success: delete the retry entry
- FK to `delivery_log` so retry history links to the original delivery record

**Known gap (not fixed for pilot):** Approval-state messages stored in-memory (`bot_data["pending_messages"]`) are lost on delivery container restart. Acceptable because Federico reviews approvals quickly.

### 1.5 — SQLite Hardening

- **Integrity check on process startup** (not every connection): `PRAGMA integrity_check` on `clients.db`, `companies.db`, `certificates.db`. If any fails, log CRITICAL and refuse to start. Better to stop than serve corrupted data.
- **Verify WAL mode** is active at startup
- **Enable foreign keys**: `PRAGMA foreign_keys=ON` on every connection (FK constraints exist in schema but are not enforced at runtime)
- **Clean startup in delivery runner**: `init_db()` in `delivery/runner.py` has no try/except. Add try/except that logs CRITICAL and exits cleanly instead of unhandled traceback.

### 1.6 — Application-Level Health Checks

| Service | Signal | Healthy when |
|---------|--------|--------------|
| Worker | Touch `/tmp/healthcheck` after each completed job **AND** after each BRPOP poll tick (including timeouts) | File modified < 5 minutes ago |
| Delivery | Track `last_event_at` in memory (set on each pub/sub message or retry tick) | Event loop running AND last event < 30 minutes ago (or no clients onboarded) |
| Twin | HTTP GET `/` on the twin HTTP server | Returns 200 |

Health check command for worker: `test $(( $(date +%s) - $(stat -c %Y /tmp/healthcheck 2>/dev/null || echo 0) )) -lt 300`

Add Docker health checks in `docker-compose.yml` for worker, delivery, and twin. Scheduler already has one.

### 1.7 — Alerting

`scripts/healthcheck.sh` — cron every 5 minutes:

1. Check each container's health via `docker inspect --format='{{.State.Health.Status}}'` (not `docker compose ps` — more reliable across Compose versions)
2. Check restart counts via `docker inspect --format='{{.RestartCount}}'`
3. Check SQLite DB file sizes (disk space proxy)
4. If unhealthy or restart count > 2: send Telegram via `curl` to Bot API

Why cron and not Prometheus: for 5 clients on a Pi5, Prometheus adds 400+ MB RAM. The cron script uses zero runtime resources, has zero application dependencies, and works even when Redis, the delivery runner, and the API are all down. Revisit when moving to VPS or exceeding 20 clients.

### 1.8 — Backup

`scripts/backup.sh`:

1. Use `sqlite3 /path/to/db ".backup /path/to/backup.sqlite"` — **not** `cp`. Plain `cp` of a WAL-mode SQLite database can produce a corrupt backup if `-wal`/`-shm` files are inconsistent.
2. Run `PRAGMA integrity_check` on each backup copy (not the source — avoid locking production)
3. Delete backups older than 30 days
4. Log success/failure to a file
5. Restore instructions as a comment block at the top

Cron: daily at 03:00. Portable (Pi5 and VPS).

---

## Phase 2: Safe to Maintain

**Question this phase answers:** "Can I confidently change this code 3 months from now?"

All Phase 2 changes are protected by the CI pipeline from Phase 1.

### 2.1 — Ruff + Formatting

Add to `pyproject.toml`:

```toml
[tool.ruff]
target-version = "py311"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "W", "I", "B", "UP", "SIM", "RUF"]

[tool.ruff.format]
quote-style = "double"
```

Rules: `E/F/W` (pyflakes + pycodestyle), `I` (import sorting), `B` (bugbear), `UP` (pyupgrade), `SIM` (simplify), `RUF` (Ruff-specific: mutable class defaults, unused noqa, f-string issues).

Baseline strategy:
1. Run `ruff check --fix` to auto-fix trivials (import sorting, unused imports)
2. Fix remaining violations in files being touched by Phase 2
3. `# noqa` the rest with a tracking comment
4. CI enforces: no new violations

### 2.2 — Scanner Decomposition

Break `src/prospecting/scanner.py` (1,353 lines, 22 functions) into a package.

**Target structure:**

```
src/prospecting/scanners/
    __init__.py          # re-exports for backward compat (transitional — removed in same PR)
    models.py            # ScanResult dataclass (22 fields) + ScanTypeInfo(id, layer, function)
    registry.py          # scan type registration, approval token validation, _SCAN_TYPE_FUNCTIONS
    runner.py            # scan_domains() orchestrator: robots gate, batch phase, per-domain fan-out
    compliance.py        # _write_pre_scan_check(), compliance record output
    tls.py               # check_ssl() — renamed from ssl.py to avoid shadowing stdlib ssl
    headers.py           # get_response_headers()
    robots.py            # check_robots_txt()
    httpx_scan.py        # run_httpx()
    webanalyze.py        # run_webanalyze()
    subfinder.py         # run_subfinder()
    dnsx.py              # run_dnsx() — renamed from dns.py to avoid shadowing stdlib dns
    ct.py                # query_ct_logs(), query_ct_single()
    grayhat.py           # query_grayhatwarfare()
    nuclei.py            # run_nuclei()
    cmseek.py            # run_cmseek()
    nmap.py              # run_nmap(), parse_nmap_xml(), nmap_ports_to_findings()
    wordpress.py         # extract_page_meta(), extract_rest_api_plugins()
```

**Design decisions:**
- **Drop underscore prefix** — `scan_job.py` already imports 14 "private" functions. They are the public API.
- **Avoid stdlib name collisions** — `ssl.py` → `tls.py`, `dns.py` → `dnsx.py` (matches the tool name)
- **Each module owns its constants** — timeouts, lookup tables, rate limits that are currently module-level in scanner.py
- **`registry.py` owns mutable state** — `_LEVEL0_SCAN_FUNCTIONS`, `_LEVEL1_SCAN_FUNCTIONS`, `_SCAN_TYPE_FUNCTIONS`, approval token validation
- **`runner.py` owns orchestration** — ThreadPoolExecutor fan-out, the `_scan_single_domain` closure, batch sequencing
- **Fix the tuple unpacking bug** — `_scan_single_domain` only unpacks 3 of 5 values from `_extract_page_meta` (drops `plugin_versions` and `themes`). Fix during decomposition.
- **NOT a Protocol/ABC** — each scanner has different signatures (list[str] vs str, dict vs list returns). Forcing a common interface would mean adapter boilerplate without value.
- **Two commits in one PR**: (1) decompose with `__init__.py` re-exports, all tests pass; (2) update consumer imports, remove re-exports. Re-exports do not survive past merge.

### 2.3 — Shared Infrastructure Extraction

Move cross-cutting code from `src/prospecting/` to `src/core/`:

```
src/core/
    __init__.py
    config.py            # PROJECT_ROOT, CONFIG_DIR, DATA_DIR, BRIEFS_DIR, CMS_KEYWORDS,
                         # HOSTING_PROVIDERS, REQUEST_TIMEOUT, USER_AGENT
    logging_config.py    # setup_logging() — already 100% generic
    exceptions.py        # ScanToolError, DeliveryError, ConfigError (from 2.4)
```

**`src/core/` not `src/common/`** — "common" is a junk drawer name. "core" signals foundational, stable, depended-on-by-everything.

**Config side effects made lazy:**
- `os.environ["PATH"]` mutation → wrap in `ensure_go_bin_on_path()`, called explicitly by scheduler and worker entry points only
- 5 JSON file loads at import time → use `@functools.cache` on getter functions, loaded on first access. Faster test suite (most tests never need those config files).

**Prospecting-specific stays in `src/prospecting/config.py`:** `COL_*` Excel columns, `BUCKET_*` config, `GDPR_*` signals, `FREE_WEBMAIL`, `CRT_SH_*`, `SUBFINDER_*`, tool API keys, PATH side effect.

**No backward-compat re-exports.** Clean cut. Update all import sites (6 for config, 4 for logging_config). One commit.

### 2.4 — Exception Hygiene

**New exception types** in `src/core/exceptions.py`:

| Exception | Purpose | Used in |
|-----------|---------|---------|
| `ScanToolError(Exception)` | Scan tool subprocess failure, timeout, missing binary | Each scanner module |
| `DeliveryError(Exception)` | Telegram send/approval failure | `sender.py`, `runner.py`, `approval.py` |
| `ConfigError(Exception)` | Missing/invalid config file | `llm.py`, `delivery/bot.py` |

**Log level corrections:**

| File:line | Current | Corrected | Reason |
|-----------|---------|-----------|--------|
| `scanner.py:104` (SSL check) | DEBUG | WARNING | Unexpected SSL errors should not be invisible |
| `scanner.py:582` (crt.sh thread) | DEBUG | WARNING | CT query failures should be visible |
| `scanner.py:1332` (domain scan) | WARNING, no traceback | WARNING + `.opt(exception=True)` | Tracebacks needed for debugging |
| `twin_scan.py:168` (server start) | ERROR, no traceback | ERROR + `.opt(exception=True)` | Traceback currently lost |

**Silent swallows to fix:**

| File:line | Current | Fix |
|-----------|---------|-----|
| `scan_job.py:103` (slug map) | `except Exception: return {}` | Add `logger.warning()` |
| `delivery/runner.py:119` (DB close) | `except Exception: pass` | Add `logger.debug()` |

**Bare `except Exception` to keep** (these are correct safety nets):
- `consent/validator.py:99` — correctly fail-closed with double wrap
- `worker/main.py:409` — correctly isolates job failures
- `delivery/runner.py:152` — correctly keeps event loop alive
- `api/app.py:49` — correctly logs and re-raises in middleware

### 2.5 — Input Validation at Trust Boundaries

Redis job payloads cross a process boundary. Add Pydantic models in `src/worker/models.py`:

```python
from pydantic import BaseModel

class ScanJob(BaseModel):
    domain: str
    level: int = 0
    company_name: str = ""
    cvr: str = ""
    industry_code: str = ""
    # ... fields matching current dict shape

class EnrichmentJob(BaseModel):
    batch_id: int
    domains: list[str]
```

Validation in `worker/main.py`:
- Use `ScanJob.model_validate_json(raw_bytes)` directly on Redis BRPOP bytes (skips intermediate dict, handles encoding errors with `ValidationError`)
- Invalid payloads → log ERROR with the raw JSON, skip the job
- Today: a malformed payload causes a `KeyError` deep in `scan_job.py` with no indication of what the input was

### 2.6 — Test Coverage

**Coverage baseline:** Run `pytest --cov=src --cov-report=term-missing` first. Set `fail_under` to current baseline (expected 50-65%). Target 70 after golden-path test lands.

**Tests for Phase 1 bug fixes:**
- Scheduler daemon: Redis failure during error handling does not crash the process
- Worker: BRPOP backoff actually sleeps on disconnect (mock `time.sleep`, assert called with increasing values)
- Delivery runner: reconnection loop retries after Redis disconnect (mock pub/sub, simulate `ConnectionError`, assert resubscribe attempts with backoff)
- Delivery retry: failed deliveries are retried up to 3 times, then operator is alerted
- Telegram sender: `Forbidden` and `BadRequest` set `permanently_failed` status in DB

**Reconnection tests (architect recommendation):**
- One test per component (daemon, worker, delivery) that simulates `ConnectionError` mid-loop and verifies backoff + recovery

**Golden-path smoke test** (`tests/test_golden_path.py`):
- Mock: Redis (fakeredis), SQLite (in-memory), Claude API (fixture response), Telegram Bot API (mock)
- Exercise: create scan job → execute scan (mocked tool subprocesses) → interpret brief → compose message → send (mocked Telegram)
- Assert: `delivery_log` entry exists with status `sent`, message contains expected severity labels, HTML is well-formed

---

## Execution Order

```
Phase 1 (no architecture changes):
  1.1  Git hygiene + pin Dozzle           [5 min]
  1.2  CI pipeline (pre-commit + GH Actions)
  1.3  Bug fixes (8 one-file fixes)
  1.4  Delivery resilience (retry table)
  1.5  SQLite hardening (pragmas + startup)
  1.6  Health checks (worker, delivery, twin)
  1.7  Alerting (healthcheck.sh + cron)
  1.8  Backup (backup.sh + cron)

Phase 2 (code changes under CI):
  2.1  Ruff + formatting (baseline + enforce)
  2.2  Scanner decomposition (scanners/ package)
  2.3  Shared infra extraction (src/core/)
  2.4  Exception hygiene (types + log levels)
  2.5  Input validation (Pydantic on Redis payloads)
  2.6  Test coverage (baseline + bug fix tests + golden-path)
```

---

## Verification

After Phase 1:
- `pytest` passes in CI on every push
- `ruff check` passes
- All containers show `healthy` in `docker inspect`
- `healthcheck.sh` sends a test alert to Telegram
- `backup.sh` produces intact backup copies (integrity check passes)
- Kill Redis → verify worker backs off (not spin-loop), delivery runner reconnects, scheduler survives
- Simulate Claude API failure → verify delivery_retry entry created, retried after 15 min

After Phase 2:
- All 922+ tests pass
- `ruff check` clean (no violations)
- Coverage >= baseline `fail_under` threshold
- `scanner.py` no longer exists (replaced by `scanners/` package)
- `src/core/` exists with config, logging, exceptions
- Golden-path smoke test passes
- `from src.prospecting.scanners import ScanResult, run_httpx` works (consumer imports unchanged via __init__.py, then updated)

---

## Files Modified

### Phase 1
| File | Change |
|------|--------|
| `.gitignore` | Add `data/**/*.db`, `*.key`, `*.pem`, `*.env.*`, `secrets/` |
| `infra/docker/docker-compose.yml` | Pin Dozzle tag, add health checks for worker/delivery/twin |
| `.pre-commit-config.yaml` | New — ruff check, ruff format, pre-push pytest |
| `.github/workflows/ci.yml` | New — Python 3.11, uv sync, ruff, pytest |
| `src/scheduler/daemon.py` | Fix crash bug (line 73), fix opaque error messages |
| `src/worker/main.py` | Add BRPOP backoff, touch healthcheck file on poll tick |
| `src/delivery/runner.py` | Reconnection loop with backoff, delivery_retry coroutine |
| `src/delivery/sender.py` | Catch Forbidden/BadRequest, mark permanently_failed |
| `src/delivery/approval.py` | Add try/except around request_approval |
| `src/vulndb/rss_cve.py` | Set socket timeout around feedparser |
| `src/worker/scan_job.py` | Add logging to slug map load failure |
| `docs/architecture/client-db-schema.sql` | Add delivery_retry table |
| `src/db/connection.py` | Add integrity check, WAL verify, FK enforcement at startup |
| `src/db/migrate.py` | Add delivery_retry table migration |
| `scripts/healthcheck.sh` | New — container health + restart check + Telegram alert |
| `scripts/backup.sh` | New — SQLite atomic backup + integrity check + retention |

### Phase 2
| File | Change |
|------|--------|
| `pyproject.toml` | Add ruff config, coverage fail_under |
| `src/prospecting/scanner.py` | Deleted — replaced by `src/prospecting/scanners/` package |
| `src/prospecting/scanners/` | New package — 18 modules (see 2.2) |
| `src/core/` | New package — `config.py`, `logging_config.py`, `exceptions.py` |
| `src/prospecting/config.py` | Remove shared constants (moved to src/core/config.py), make side effects lazy |
| `src/prospecting/logging_config.py` | Deleted — moved to `src/core/logging_config.py` |
| `src/worker/main.py` | Update imports (core.config, core.logging_config, scanners.*) |
| `src/worker/scan_job.py` | Update imports (scanners.*) |
| `src/worker/models.py` | New — Pydantic models for Redis job payloads |
| `src/scheduler/job_creator.py` | Update imports (core.config) |
| `src/scheduler/main.py` | Update imports (core.logging_config) |
| `src/api/app.py` | Update imports (core.logging_config) |
| `tests/test_golden_path.py` | New — end-to-end smoke test |
| Various test files | Tests for Phase 1 bug fixes + reconnection tests |

---

## Reviewed By

- **Architect agent** — validated Phase ordering, delivery_retry in SQLite (not Redis), scanner functions-as-modules approach, cron alerting. Flagged: path-specific gitignore, CI should move earlier, approval-state loss as known gap, coverage baseline check.
- **Docker expert** — validated heartbeat-file pattern, docker inspect over compose ps, cron over Prometheus. Flagged: SQLite backup must use `.backup` command (not cp) for WAL safety, worker heartbeat must touch on idle ticks, pin Dozzle tag.
- **Python expert** — validated decomposition, config split, ruff rules. Flagged: dns.py/ssl.py shadow stdlib (renamed to dnsx.py/tls.py), config side effects should be lazy, use src/core/ not src/common/, use model_validate_json() for Redis payloads, add RUF to ruff rules.
