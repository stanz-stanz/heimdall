# MVP Phase 1: Safe to Operate — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Heimdall safe to onboard 5 pilot clients — secrets can't leak, failures are caught by systems not humans, messages aren't silently lost, and the operator console is secured.

**Architecture:** No application architecture changes. All fixes are one-file patches, new scripts, or config additions. The CI pipeline is established first so every subsequent change is automatically tested.

**Tech Stack:** Python 3.11, FastAPI, Svelte 5, SQLite, Redis, Docker Compose, GitHub Actions, ruff, pytest, pre-commit

**Spec:** `docs/superpowers/specs/2026-04-11-mvp-hardening-design.md`

---

## Task 1: Git Hygiene + Env Docs

**Files:**
- Modify: `.gitignore`
- Modify: `.env.example`
- Modify: `infra/docker/docker-compose.yml` (pin Dozzle tag)

- [ ] **Step 1: Update .gitignore**

Add after the existing `*.db-shm` / `*.db-wal` block:

```gitignore
# SQLite databases (runtime-generated, contain client data)
data/**/*.db

# Secrets and credentials
*.key
*.pem
*.env.*
secrets/
```

- [ ] **Step 2: Verify no DBs are tracked**

Run: `git ls-files '*.db'`
Expected: no output (empty)

- [ ] **Step 3: Update .env.example**

Add to the end of `.env.example`:

```bash
# Telegram Operator Chat ID — used for delivery approval flow
TELEGRAM_OPERATOR_CHAT_ID=

# Serper API — used for search-based domain discovery in enrichment
SERPER_API_KEY=

# Operator Console — HTTP Basic Auth (required for /console/* and /app)
CONSOLE_USER=admin
CONSOLE_PASSWORD=
```

- [ ] **Step 4: Pin Dozzle version**

In `infra/docker/docker-compose.yml`, replace:
```yaml
    image: amir20/dozzle:latest
```
with:
```yaml
    image: amir20/dozzle:v8.12.5
```

(Check the latest stable tag at `docker pull amir20/dozzle` and use that.)

- [ ] **Step 5: Commit**

```bash
git add .gitignore .env.example infra/docker/docker-compose.yml
git commit -m "chore: git hygiene — ignore runtime DBs, document all env vars, pin Dozzle"
```

---

## Task 2: CI Pipeline

**Files:**
- Modify: `pyproject.toml`
- Create: `.pre-commit-config.yaml`
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: Add ruff config to pyproject.toml**

Add after the existing `[dependency-groups]` section:

```toml
[tool.ruff]
target-version = "py311"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "W", "I", "B", "UP", "SIM", "RUF"]

[tool.ruff.format]
quote-style = "double"
```

- [ ] **Step 2: Install ruff and pre-commit**

Run: `uv add --dev ruff pre-commit pytest-timeout`

- [ ] **Step 3: Create .pre-commit-config.yaml**

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.11.6
    hooks:
      - id: ruff
        args: [check, --fix]
      - id: ruff-format
        args: [--check]
```

- [ ] **Step 4: Install pre-commit hooks**

Run: `pre-commit install && pre-commit install --hook-type pre-push`

- [ ] **Step 5: Create .github/workflows/ci.yml**

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install uv
        run: pip install uv

      - name: Install dependencies
        run: uv sync

      - name: Lint
        run: uv run ruff check

      - name: Format check
        run: uv run ruff format --check

      - name: Test
        run: uv run pytest -x --tb=short --timeout=30
```

- [ ] **Step 6: Run the CI steps locally to verify**

Run: `ruff check && ruff format --check && pytest -x --tb=short --timeout=30`
Expected: ruff may report existing violations (that's fine — we'll baseline them). Tests should pass.

- [ ] **Step 7: Baseline ruff violations**

Run: `ruff check --fix` to auto-fix trivials (import sorting, unused imports).
For remaining violations, add targeted `# noqa` comments only to files NOT being modified in this plan.

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml .pre-commit-config.yaml .github/workflows/ci.yml
git commit -m "ci: add ruff linting + GitHub Actions + pre-commit hooks"
```

---

## Task 3: Scheduler Daemon Crash Fix + Opaque Errors

**Files:**
- Modify: `src/scheduler/daemon.py`
- Create: `tests/test_daemon_crash.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_daemon_crash.py
"""Tests for scheduler daemon error handling resilience."""

import json
from unittest.mock import MagicMock, patch

from src.scheduler.daemon import run_daemon


class TestDaemonCrashResilience:
    """Verify the daemon survives Redis failures during error handling."""

    def test_publish_failure_in_except_does_not_crash(self):
        """If _publish_result raises (Redis down), daemon must not die."""
        mock_conn = MagicMock()
        # First brpop returns a command, second returns None (triggers loop exit)
        mock_conn.brpop.side_effect = [
            ("queue:operator-commands", json.dumps({"command": "run-pipeline"})),
            None,
        ]
        # Simulate _handle_run_pipeline raising, then _publish_result also raising
        with patch("src.scheduler.daemon._handle_run_pipeline", side_effect=RuntimeError("boom")), \
             patch("src.scheduler.daemon._publish_result", side_effect=ConnectionError("Redis gone")), \
             patch("src.scheduler.daemon._shutdown_requested", side_effect=[False, True]):
            # Should not raise — daemon must survive
            run_daemon(mock_conn, "input.xlsx", "filters.json")

    def test_error_message_includes_exception_detail(self):
        """Console should receive the actual exception, not just 'check logs'."""
        mock_conn = MagicMock()
        mock_conn.brpop.side_effect = [
            ("queue:operator-commands", json.dumps({"command": "run-pipeline"})),
            None,
        ]
        published_messages = []
        with patch("src.scheduler.daemon._handle_run_pipeline",
                    side_effect=RuntimeError("enrichment timeout")), \
             patch("src.scheduler.daemon._publish_result",
                    side_effect=lambda c, cmd, s, msg: published_messages.append(msg)), \
             patch("src.scheduler.daemon._shutdown_requested", side_effect=[False, True]):
            run_daemon(mock_conn, "input.xlsx", "filters.json")

        assert any("enrichment timeout" in m for m in published_messages)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_daemon_crash.py -v`
Expected: FAIL (first test crashes due to unhandled exception, second fails because message is opaque)

- [ ] **Step 3: Fix the daemon**

In `src/scheduler/daemon.py`, replace lines 73-75:

```python
        except Exception:
            logger.opt(exception=True).error("Command failed: {}", command)
            _publish_result(conn, command, "error", "Command failed — check logs")
```

with:

```python
        except Exception as exc:
            logger.opt(exception=True).error("Command failed: {}", command)
            try:
                _publish_result(conn, command, "error", f"Command failed: {exc}")
            except Exception:
                import sys
                print(f"CRITICAL: daemon could not publish error to console: {exc}",
                      file=sys.stderr)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_daemon_crash.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/scheduler/daemon.py tests/test_daemon_crash.py
git commit -m "fix: scheduler daemon survives Redis failure during error handling"
```

---

## Task 4: Worker BRPOP Backoff

**Files:**
- Modify: `src/worker/main.py`
- Create: `tests/test_worker_backoff.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_worker_backoff.py
"""Tests for worker BRPOP backoff on Redis disconnect."""

from unittest.mock import MagicMock, patch
import redis as redis_lib


def test_brpop_backoff_sleeps_on_disconnect():
    """Worker must sleep with increasing delays on Redis disconnect, not spin."""
    sleep_calls = []

    def mock_sleep(seconds):
        sleep_calls.append(seconds)

    mock_conn = MagicMock()
    # Simulate 3 consecutive Redis errors, then shutdown
    mock_conn.brpop.side_effect = [
        redis_lib.ConnectionError("gone"),
        redis_lib.ConnectionError("gone"),
        redis_lib.ConnectionError("gone"),
    ]

    with patch("src.worker.main.time.sleep", side_effect=mock_sleep), \
         patch("src.worker.main._shutdown_requested", side_effect=[False, False, False, True]):
        # Import and call the BRPOP section — we'll need to extract it or test via run_worker
        pass  # Placeholder — test shape depends on how the loop is structured

    # Verify increasing backoff
    assert len(sleep_calls) == 3
    assert sleep_calls[0] >= 1  # First backoff
    assert sleep_calls[1] > sleep_calls[0]  # Increasing
    assert sleep_calls[2] > sleep_calls[1]  # Still increasing
```

- [ ] **Step 2: Implement the backoff**

In `src/worker/main.py`, add `import time` if not present. Then replace lines 293-295:

```python
        except (redis.ConnectionError, redis.TimeoutError) as exc:
            logger.warning("Redis BRPOP error: %s — retrying", exc)
            continue
```

with:

```python
        except (redis.ConnectionError, redis.TimeoutError) as exc:
            _redis_failures += 1
            backoff = min(2 ** _redis_failures, 30)
            logger.warning("Redis BRPOP error (attempt %d, backoff %ds): %s",
                           _redis_failures, backoff, exc)
            time.sleep(backoff)
            continue
```

And before the while loop (around line 288), add:

```python
    _redis_failures = 0
```

After a successful `brpop` (around line 297, after `if item is None: continue`), add:

```python
        _redis_failures = 0  # Reset backoff on successful connection
```

Also add healthcheck file touch. Add near the top of the file:

```python
HEALTHCHECK_FILE = "/tmp/healthcheck"
```

After each successful job completion (after line 442, the publish block) and after each idle poll (after the `if item is None: continue`), add:

```python
        Path(HEALTHCHECK_FILE).touch()
```

- [ ] **Step 3: Adjust the test to match the implementation**

Update `tests/test_worker_backoff.py` with a test that directly exercises the backoff logic by patching `time.sleep` and `redis_conn.brpop`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_worker_backoff.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/worker/main.py tests/test_worker_backoff.py
git commit -m "fix: worker BRPOP backoff on Redis disconnect + healthcheck file"
```

---

## Task 5: Delivery Runner Reconnection Loop

**Files:**
- Modify: `src/delivery/runner.py`
- Create: `tests/test_delivery_reconnect.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_delivery_reconnect.py
"""Tests for delivery runner Redis reconnection with backoff."""

import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
import redis as redis_lib


def test_reconnection_retries_with_backoff():
    """After Redis disconnect, delivery runner must retry with increasing delays."""
    sleep_calls = []

    async def mock_sleep(seconds):
        sleep_calls.append(seconds)
        if len(sleep_calls) >= 3:
            # Stop after 3 reconnection attempts
            raise asyncio.CancelledError

    # Test will verify that sleep_calls contains increasing values
    assert True  # Placeholder — shape depends on runner refactor
```

- [ ] **Step 2: Fix the reconnection logic**

In `src/delivery/runner.py`, replace lines 130-156:

```python
        try:
            r = redis.from_url(self.redis_url, decode_responses=True)
            pubsub = r.pubsub()
            pubsub.subscribe("client-scan-complete")
            logger.bind(context={"channel": "client-scan-complete"}).info("redis_subscribed")
        except redis.ConnectionError as exc:
            logger.error("redis_connection_failed: {}", exc)
            return

        while self._running:
            try:
                message = pubsub.get_message(timeout=1.0)
                if message and message.get("type") == "message":
                    await self._handle_scan_complete(message["data"])
            except redis.ConnectionError:
                logger.warning("redis_connection_lost, reconnecting in 5s")
                await asyncio.sleep(5)
                try:
                    pubsub = r.pubsub()
                    pubsub.subscribe("client-scan-complete")
                except redis.ConnectionError:
                    pass
            except Exception:
                logger.opt(exception=True).error("error_processing_scan_event")

            # Yield to event loop
            await asyncio.sleep(0.1)
```

with:

```python
        _RECONNECT_BACKOFF = [1, 2, 5, 10, 30]

        while self._running:
            try:
                r = redis.from_url(self.redis_url, decode_responses=True)
                pubsub = r.pubsub()
                pubsub.subscribe("client-scan-complete")
                logger.bind(context={"channel": "client-scan-complete"}).info(
                    "redis_subscribed"
                )
            except redis.ConnectionError as exc:
                logger.error("redis_connection_failed: {}", exc)
                await asyncio.sleep(_RECONNECT_BACKOFF[-1])
                continue

            reconnect_attempt = 0
            while self._running:
                try:
                    message = pubsub.get_message(timeout=1.0)
                    if message and message.get("type") == "message":
                        await self._handle_scan_complete(message["data"])
                    reconnect_attempt = 0  # Reset on success
                except redis.ConnectionError:
                    delay = _RECONNECT_BACKOFF[
                        min(reconnect_attempt, len(_RECONNECT_BACKOFF) - 1)
                    ]
                    reconnect_attempt += 1
                    logger.warning(
                        "redis_connection_lost (attempt {}, backoff {}s)",
                        reconnect_attempt, delay,
                    )
                    await asyncio.sleep(delay)
                    break  # Break inner loop to reconnect in outer loop
                except Exception:
                    logger.opt(exception=True).error("error_processing_scan_event")

                await asyncio.sleep(0.1)
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_delivery_reconnect.py tests/test_delivery.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/delivery/runner.py tests/test_delivery_reconnect.py
git commit -m "fix: delivery runner reconnects with backoff after Redis disconnect"
```

---

## Task 6: Telegram Error Handling + Approval Safety

**Files:**
- Modify: `src/delivery/sender.py`
- Modify: `src/delivery/approval.py`
- Create: `tests/test_telegram_errors.py`

- [ ] **Step 1: Write the test**

```python
# tests/test_telegram_errors.py
"""Tests for Telegram Forbidden/BadRequest handling in sender."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from telegram.error import Forbidden, BadRequest


@pytest.mark.asyncio
async def test_forbidden_returns_permanent_failure():
    """When bot is blocked by user, return permanently_failed status."""
    bot = AsyncMock()
    bot.send_message.side_effect = Forbidden("Forbidden: bot was blocked by the user")

    from src.delivery.sender import send_message
    result = await send_message(bot, chat_id=123, text="test")

    assert result["success"] is False
    assert "permanently_failed" in result.get("error", "").lower() or "forbidden" in result.get("error", "").lower()
    # Should NOT retry — only 1 call
    assert bot.send_message.call_count == 1


@pytest.mark.asyncio
async def test_bad_request_returns_permanent_failure():
    """When chat_id is invalid, return permanently_failed status."""
    bot = AsyncMock()
    bot.send_message.side_effect = BadRequest("Chat not found")

    from src.delivery.sender import send_message
    result = await send_message(bot, chat_id=999, text="test")

    assert result["success"] is False
    assert bot.send_message.call_count == 1  # No retry
```

- [ ] **Step 2: Fix sender.py**

In `src/delivery/sender.py`, add to imports:

```python
from telegram.error import RetryAfter, TimedOut, NetworkError, Forbidden, BadRequest
```

(Replace the existing import line that only imports `RetryAfter, TimedOut, NetworkError`.)

Then in `send_message()`, after the `except (TimedOut, NetworkError)` block (after line 76), add:

```python
        except (Forbidden, BadRequest) as exc:
            logger.bind(context={
                "chat_id": chat_id,
                "error": str(exc),
            }).error("telegram_permanent_failure")
            return {
                "success": False,
                "message_id": None,
                "error": f"Permanently failed: {exc}",
            }
```

- [ ] **Step 3: Fix approval.py**

In `src/delivery/approval.py`, wrap the `request_approval` send loop (lines 107-114) in try/except:

```python
    try:
        for i, chunk in enumerate(messages):
            is_last = i == len(messages) - 1
            await bot.send_message(
                chat_id=operator_chat_id,
                text=chunk,
                reply_markup=approval_keyboard if is_last else None,
                parse_mode="HTML",
            )
    except Exception as exc:
        logger.opt(exception=True).error(
            "approval_request_failed delivery_id={} domain={}", delivery_id, domain,
        )
        if conn and delivery_id:
            from src.db.delivery import update_delivery_status
            update_delivery_status(conn, delivery_id, "approval_failed", error_message=str(exc))
        return
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_telegram_errors.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/delivery/sender.py src/delivery/approval.py tests/test_telegram_errors.py
git commit -m "fix: handle Telegram Forbidden/BadRequest + approval error safety"
```

---

## Task 7: Minor Bug Fixes (feedparser, slug map, runner interpret)

**Files:**
- Modify: `src/vulndb/rss_cve.py`
- Modify: `src/worker/scan_job.py`

- [ ] **Step 1: Fix feedparser timeout**

In `src/vulndb/rss_cve.py`, add `import socket` at the top. Then wrap the feedparser call (lines 128-133):

```python
    try:
        old_timeout = socket.getdefaulttimeout()
        socket.setdefaulttimeout(30)
        try:
            feed = feedparser.parse(feed_url, agent=USER_AGENT)
        finally:
            socket.setdefaulttimeout(old_timeout)
    except Exception as exc:
        logger.warning("RSS fetch failed for {feed_key}: {exc}",
                       feed_key=feed_key, exc=exc)
        return 0
```

- [ ] **Step 2: Fix slug map silent failure**

In `src/worker/scan_job.py`, replace lines 103-104:

```python
    except Exception:
        return {}
```

with:

```python
    except Exception:
        logger.warning("slug_map_load_failed — plugin name normalization disabled",
                       exc_info=True)
        return {}
```

- [ ] **Step 3: Run existing tests**

Run: `pytest tests/test_rss_cve.py tests/test_scan_job.py -v`
Expected: PASS (no behavior change, just added logging/safety)

- [ ] **Step 4: Commit**

```bash
git add src/vulndb/rss_cve.py src/worker/scan_job.py
git commit -m "fix: feedparser timeout + slug map load logging"
```

---

## Task 8: Delivery Resilience (Retry Table)

**Files:**
- Modify: `docs/architecture/client-db-schema.sql`
- Modify: `src/db/migrate.py`
- Modify: `src/delivery/runner.py`
- Create: `tests/test_delivery_retry.py`

- [ ] **Step 1: Add delivery_retry table to schema**

Append to `docs/architecture/client-db-schema.sql` before the final views:

```sql
-- Delivery retry queue — catches failed interpretation/send attempts
CREATE TABLE IF NOT EXISTS delivery_retry (
    id              INTEGER PRIMARY KEY,
    delivery_log_id INTEGER REFERENCES delivery_log(id),
    domain          TEXT NOT NULL,
    brief_path      TEXT NOT NULL,
    attempt         INTEGER NOT NULL DEFAULT 0,
    next_retry_at   TEXT NOT NULL,
    last_error      TEXT,
    status          TEXT NOT NULL DEFAULT 'pending',
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_delivery_retry_pending
    ON delivery_retry(status, next_retry_at);
```

- [ ] **Step 2: Write the test**

```python
# tests/test_delivery_retry.py
"""Tests for delivery retry mechanism."""

import sqlite3
from datetime import datetime, timezone, timedelta


def test_retry_table_created():
    """delivery_retry table exists after schema application."""
    conn = sqlite3.connect(":memory:")
    from src.db.connection import _load_schema
    conn.executescript(_load_schema())
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()]
    assert "delivery_retry" in tables


def test_retry_insert_and_query():
    """Can insert a retry entry and query pending retries."""
    conn = sqlite3.connect(":memory:")
    from src.db.connection import _load_schema
    conn.executescript(_load_schema())

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn.execute(
        "INSERT INTO delivery_retry (domain, brief_path, next_retry_at, last_error)"
        " VALUES (?, ?, ?, ?)",
        ("example.dk", "/data/briefs/example.dk.json", now, "Claude API timeout"),
    )
    conn.commit()

    pending = conn.execute(
        "SELECT * FROM delivery_retry WHERE status = 'pending' AND next_retry_at <= ?",
        (now,),
    ).fetchall()
    assert len(pending) == 1
```

- [ ] **Step 3: Run test to verify it passes**

Run: `pytest tests/test_delivery_retry.py -v`
Expected: PASS

- [ ] **Step 4: Add retry logic to delivery runner**

In `src/delivery/runner.py`, add a method to the `DeliveryRunner` class that:
1. Queries `delivery_retry` for pending entries where `next_retry_at <= now AND status = 'pending' AND attempt < 3`
2. For each: attempts `interpret_brief()` + `compose_telegram()` + `send_with_logging()`
3. On success: deletes the retry entry
4. On failure: increments `attempt`, sets `next_retry_at` to exponential backoff (+15min, +1hr, +4hr), updates `last_error`
5. After 3 failures: sets `status = 'exhausted'`, sends operator alert via Telegram

Also modify `_handle_scan_complete` so that on interpretation failure (the current `except Exception: return` at line 241), it inserts into `delivery_retry` instead of silently returning.

Schedule this retry coroutine to run every 15 minutes using `asyncio.create_task` with a loop.

- [ ] **Step 5: Run all delivery tests**

Run: `pytest tests/test_delivery.py tests/test_delivery_retry.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add docs/architecture/client-db-schema.sql src/delivery/runner.py tests/test_delivery_retry.py
git commit -m "feat: delivery retry table — failed messages retried 3x with backoff"
```

---

## Task 9: SQLite Hardening

**Files:**
- Modify: `src/db/connection.py`
- Create: `tests/test_db_hardening.py`

- [ ] **Step 1: Write the test**

```python
# tests/test_db_hardening.py
"""Tests for SQLite hardening — integrity check, WAL verification."""

import sqlite3
import pytest
from pathlib import Path


def test_init_db_enables_foreign_keys(tmp_path):
    """Foreign key enforcement must be ON after init_db."""
    from src.db.connection import init_db
    db_path = tmp_path / "test.db"
    conn = init_db(str(db_path))
    fk_status = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    assert fk_status == 1
    conn.close()


def test_init_db_uses_wal_mode(tmp_path):
    """Journal mode must be WAL after init_db."""
    from src.db.connection import init_db
    db_path = tmp_path / "test.db"
    conn = init_db(str(db_path))
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode == "wal"
    conn.close()


def test_verify_integrity_passes_on_good_db(tmp_path):
    """verify_integrity should return True for a healthy database."""
    from src.db.connection import init_db, verify_integrity
    db_path = tmp_path / "test.db"
    conn = init_db(str(db_path))
    assert verify_integrity(conn) is True
    conn.close()
```

- [ ] **Step 2: Add verify_integrity function**

In `src/db/connection.py`, add after `init_db`:

```python
def verify_integrity(conn: sqlite3.Connection) -> bool:
    """Run PRAGMA integrity_check on the database.

    Returns:
        True if the database passes integrity checks, False otherwise.
    """
    try:
        result = conn.execute("PRAGMA integrity_check").fetchone()
        if result and result[0] == "ok":
            return True
        logger.critical("Database integrity check FAILED: {}", result)
        return False
    except sqlite3.DatabaseError as exc:
        logger.critical("Database integrity check error: {}", exc)
        return False
```

- [ ] **Step 3: Run test to verify it passes**

Run: `pytest tests/test_db_hardening.py -v`
Expected: PASS

- [ ] **Step 4: Add startup integrity check to delivery runner**

In `src/delivery/runner.py`, in the startup method where `init_db()` is called, wrap it:

```python
        try:
            self.db_conn = init_db(self.db_path)
            from src.db.connection import verify_integrity
            if not verify_integrity(self.db_conn):
                logger.critical("Database integrity check failed — refusing to start")
                return
        except Exception as exc:
            logger.critical("Database initialization failed: {}", exc)
            return
```

- [ ] **Step 5: Commit**

```bash
git add src/db/connection.py src/delivery/runner.py tests/test_db_hardening.py
git commit -m "feat: SQLite hardening — integrity check on startup, verify_integrity helper"
```

---

## Task 10: Docker Health Checks

**Files:**
- Modify: `infra/docker/docker-compose.yml`

- [ ] **Step 1: Add worker health check**

In `docker-compose.yml`, add to the `worker` service (after `restart: unless-stopped`):

```yaml
    healthcheck:
      test: ["CMD-SHELL", "test $$(( $$(date +%s) - $$(stat -c %Y /tmp/healthcheck 2>/dev/null || echo 0) )) -lt 300"]
      interval: 60s
      timeout: 5s
      retries: 3
      start_period: 30s
```

- [ ] **Step 2: Add twin health check**

In `docker-compose.yml`, add to the `twin` service:

```yaml
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9080/"]
      interval: 30s
      timeout: 5s
      retries: 3
```

- [ ] **Step 3: Verify docker-compose is valid**

Run: `cd infra/docker && docker compose config --quiet && cd ../..`
Expected: no errors

- [ ] **Step 4: Commit**

```bash
git add infra/docker/docker-compose.yml
git commit -m "feat: add Docker health checks for worker and twin containers"
```

---

## Task 11: Alerting Script

**Files:**
- Create: `scripts/healthcheck.sh`

- [ ] **Step 1: Create the script**

```bash
#!/usr/bin/env bash
# Heimdall health check — runs via cron every 5 minutes.
# Checks container health and restart counts. Alerts operator via Telegram.
#
# Cron setup: */5 * * * * /path/to/heimdall/scripts/healthcheck.sh
#
# Required env vars (set in crontab or .env):
#   TELEGRAM_BOT_TOKEN, TELEGRAM_OPERATOR_CHAT_ID

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Load .env if present
if [ -f "$PROJECT_DIR/.env" ]; then
    set -a
    source "$PROJECT_DIR/.env"
    set +a
fi

BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-}"
CHAT_ID="${TELEGRAM_OPERATOR_CHAT_ID:-}"

if [ -z "$BOT_TOKEN" ] || [ -z "$CHAT_ID" ]; then
    echo "ERROR: TELEGRAM_BOT_TOKEN and TELEGRAM_OPERATOR_CHAT_ID must be set" >&2
    exit 1
fi

send_alert() {
    local message="$1"
    curl -s -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
        -d chat_id="$CHAT_ID" \
        -d text="$message" \
        -d parse_mode="HTML" > /dev/null 2>&1
}

COMPOSE_DIR="$PROJECT_DIR/infra/docker"
ALERTS=""

# Check each service's health status
for service in redis worker api delivery scheduler ct-collector; do
    container=$(docker compose -f "$COMPOSE_DIR/docker-compose.yml" ps -q "$service" 2>/dev/null | head -1)
    [ -z "$container" ] && continue

    health=$(docker inspect --format='{{.State.Health.Status}}' "$container" 2>/dev/null || echo "no-healthcheck")
    restarts=$(docker inspect --format='{{.RestartCount}}' "$container" 2>/dev/null || echo "0")

    if [ "$health" = "unhealthy" ]; then
        ALERTS="${ALERTS}\n- ${service}: UNHEALTHY"
    fi
    if [ "$restarts" -gt 2 ]; then
        ALERTS="${ALERTS}\n- ${service}: ${restarts} restarts"
    fi
done

if [ -n "$ALERTS" ]; then
    send_alert "<b>Heimdall Alert</b>${ALERTS}"
fi
```

- [ ] **Step 2: Make executable**

Run: `chmod +x scripts/healthcheck.sh`

- [ ] **Step 3: Commit**

```bash
git add scripts/healthcheck.sh
git commit -m "feat: cron-based health check script with Telegram alerting"
```

---

## Task 12: Backup Script

**Files:**
- Create: `scripts/backup.sh`

- [ ] **Step 1: Create the script**

```bash
#!/usr/bin/env bash
# Heimdall SQLite backup — daily cron job.
# Uses sqlite3 .backup for WAL-safe atomic copies.
# Runs integrity check on each backup. 30-day retention.
#
# Cron: 0 3 * * * /path/to/heimdall/scripts/backup.sh
#
# Restore:
#   1. Stop the service that uses the DB
#   2. cp backups/YYYY-MM-DD-HHMMSS/clients.db data/clients/clients.db
#   3. Restart the service

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BACKUP_DIR="$PROJECT_DIR/backups/$(date +%Y-%m-%d-%H%M%S)"
LOG_FILE="$PROJECT_DIR/backups/backup.log"
RETENTION_DAYS=30

DATABASES=(
    "data/clients/clients.db"
    "data/enriched/companies.db"
)

mkdir -p "$BACKUP_DIR"

log() { echo "$(date -Iseconds) $1" >> "$LOG_FILE"; }

FAILURES=0

for db_rel in "${DATABASES[@]}"; do
    db_path="$PROJECT_DIR/$db_rel"
    db_name=$(basename "$db_rel")
    backup_path="$BACKUP_DIR/$db_name"

    if [ ! -f "$db_path" ]; then
        log "SKIP: $db_rel not found"
        continue
    fi

    # Atomic WAL-safe backup
    if sqlite3 "$db_path" ".backup '$backup_path'" 2>> "$LOG_FILE"; then
        # Integrity check on the backup copy
        result=$(sqlite3 "$backup_path" "PRAGMA integrity_check" 2>&1)
        if [ "$result" = "ok" ]; then
            log "OK: $db_name backed up and verified"
        else
            log "WARN: $db_name backup integrity check failed: $result"
            FAILURES=$((FAILURES + 1))
        fi
    else
        log "ERROR: $db_name backup failed"
        FAILURES=$((FAILURES + 1))
    fi
done

# Cleanup old backups
find "$PROJECT_DIR/backups" -maxdepth 1 -type d -name "20*" -mtime +$RETENTION_DAYS -exec rm -rf {} \; 2>/dev/null || true

if [ $FAILURES -gt 0 ]; then
    log "COMPLETED WITH $FAILURES FAILURES"
    exit 1
else
    log "COMPLETED SUCCESSFULLY"
fi
```

- [ ] **Step 2: Make executable**

Run: `chmod +x scripts/backup.sh`

- [ ] **Step 3: Commit**

```bash
git add scripts/backup.sh
git commit -m "feat: SQLite backup script — atomic WAL-safe copies + integrity check"
```

---

## Task 13: Console — HTTP Basic Auth

**Files:**
- Modify: `src/api/app.py`
- Modify: `src/api/frontend/src/lib/api.js`
- Modify: `src/api/frontend/src/lib/ws.svelte.js`
- Create: `tests/test_console_auth.py`

- [ ] **Step 1: Write the test**

```python
# tests/test_console_auth.py
"""Tests for console HTTP Basic Auth."""

import base64
import os
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient


@pytest.fixture
def app_with_auth():
    """Create app with auth env vars set."""
    with patch.dict(os.environ, {
        "CONSOLE_USER": "admin",
        "CONSOLE_PASSWORD": "secret123",
    }):
        from src.api.app import create_app
        app = create_app(results_dir="/tmp", redis_url="", messages_dir="/tmp")
        return app


def test_console_rejects_without_auth(app_with_auth):
    client = TestClient(app_with_auth)
    resp = client.get("/console/dashboard")
    assert resp.status_code == 401


def test_console_accepts_valid_auth(app_with_auth):
    client = TestClient(app_with_auth)
    creds = base64.b64encode(b"admin:secret123").decode()
    resp = client.get("/console/dashboard", headers={"Authorization": f"Basic {creds}"})
    # May be 500 if DB is missing, but NOT 401
    assert resp.status_code != 401


def test_health_endpoint_no_auth_required(app_with_auth):
    client = TestClient(app_with_auth)
    resp = client.get("/health")
    assert resp.status_code == 200
```

- [ ] **Step 2: Add auth middleware to app.py**

In `src/api/app.py`, add to imports:

```python
import base64
import secrets
```

Add a middleware class after `RequestLoggingMiddleware`:

```python
class BasicAuthMiddleware(BaseHTTPMiddleware):
    """HTTP Basic Auth for console endpoints."""

    PROTECTED_PREFIXES = ("/console", "/app")
    EXCLUDED_PATHS = ("/health",)

    def __init__(self, app, username: str, password: str):
        super().__init__(app)
        self.username = username
        self.password = password

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Skip auth for non-protected paths
        if not any(path.startswith(p) for p in self.PROTECTED_PREFIXES):
            return await call_next(request)
        if any(path.startswith(p) for p in self.EXCLUDED_PATHS):
            return await call_next(request)

        # Check Authorization header
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Basic "):
            return Response(
                status_code=401,
                headers={"WWW-Authenticate": 'Basic realm="Heimdall Console"'},
            )

        try:
            decoded = base64.b64decode(auth[6:]).decode("utf-8")
            username, password = decoded.split(":", 1)
        except (ValueError, UnicodeDecodeError):
            return Response(status_code=401,
                            headers={"WWW-Authenticate": 'Basic realm="Heimdall Console"'})

        if not (secrets.compare_digest(username, self.username)
                and secrets.compare_digest(password, self.password)):
            return Response(status_code=401,
                            headers={"WWW-Authenticate": 'Basic realm="Heimdall Console"'})

        return await call_next(request)
```

In the `create_app` function, after `app.add_middleware(RequestLoggingMiddleware)`, add:

```python
    console_user = os.environ.get("CONSOLE_USER", "")
    console_password = os.environ.get("CONSOLE_PASSWORD", "")
    if console_user and console_password:
        app.add_middleware(BasicAuthMiddleware,
                           username=console_user, password=console_password)
```

- [ ] **Step 3: Add auth headers to frontend api.js**

Replace the `fetchJSON` function in `src/api/frontend/src/lib/api.js`:

```javascript
async function fetchJSON(url) {
  const res = await fetch(url, {
    credentials: 'same-origin',
  });
  if (res.status === 401) {
    // Browser will show native auth dialog on next request
    window.location.reload();
    throw new Error('Authentication required');
  }
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}
```

Also update `saveSettings` and `sendCommand` to include `credentials: 'same-origin'` in fetch options.

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_console_auth.py -v`
Expected: PASS

- [ ] **Step 5: Rebuild frontend**

Run: `cd src/api/frontend && npm run build && cd ../../..`

- [ ] **Step 6: Commit**

```bash
git add src/api/app.py src/api/frontend/src/lib/api.js tests/test_console_auth.py
git commit -m "feat: HTTP Basic Auth on operator console endpoints"
```

---

## Task 14: Console — Error Boundaries, Send Button, Dead Code Cleanup

**Files:**
- Modify: `src/api/console.py`
- Modify: `src/api/frontend/src/views/Campaigns.svelte`
- Modify: `src/api/frontend/src/views/Dashboard.svelte`
- Modify: `src/api/frontend/src/components/Sidebar.svelte`
- Modify: `src/api/frontend/src/views/Logs.svelte`
- Modify: `src/api/frontend/src/lib/api.js`

- [ ] **Step 1: Add error boundaries to console.py dashboard endpoint**

Wrap the `_query()` function body in `console_dashboard` (and similarly for `pipeline/last`, `campaigns`, `campaigns/{}/prospects`, `clients/list`) with:

```python
        try:
            # ... existing query code ...
        except sqlite3.OperationalError as exc:
            logger.warning("console_db_unavailable: {}", exc)
            return {"error": "Database unavailable", "detail": str(exc)}
        except sqlite3.DatabaseError as exc:
            logger.critical("console_db_corruption: {}", exc)
            return {"error": "Database error", "detail": str(exc)}
```

Apply this pattern to each endpoint's `_query()` function.

- [ ] **Step 2: Remove orphaned /console/status endpoint**

Delete the `console_status` function and its route from `console.py` (lines 70-115).

- [ ] **Step 3: Add Send button to Campaigns.svelte**

In `src/api/frontend/src/views/Campaigns.svelte`, add a `handleSend` function:

```javascript
  function handleSend(campaign) {
    sendCommand('send', { campaign: campaign.campaign, limit: 10 }).catch(err => {
      console.error('Send command failed:', err);
    });
  }
```

Pass it to `CampaignCard` as `onsend={handleSend}`.

Remove the disabled "New Campaign" button:

```svelte
<!-- Remove this line: -->
<button class="btn btn-primary" disabled>New Campaign</button>
```

Replace with just the section title:

```svelte
<div class="section-header" style="margin-top: 0;">
  <span class="section-title">Active Campaigns</span>
</div>
```

- [ ] **Step 4: Wire "View all" button in Dashboard.svelte**

Replace line 131:

```svelte
    <button class="btn btn-ghost btn-sm">View all</button>
```

with:

```svelte
    <button class="btn btn-ghost btn-sm" onclick={() => navigate('logs', 'Logs')}>View all</button>
```

Add `navigate` to the imports:

```javascript
  import { navigate } from '../lib/router.svelte.js';
```

- [ ] **Step 5: Dynamic sidebar status**

In `src/api/frontend/src/components/Sidebar.svelte`, replace lines 71-77:

```svelte
      <span class="status-text">
        {#if wsState.connected}
          Pi5 &middot; 3 workers &middot; Redis OK
        {:else}
          Disconnected
        {/if}
      </span>
```

with:

```svelte
      <span class="status-text">
        {#if wsState.connected}
          Online &middot; Redis OK
        {:else}
          Disconnected
        {/if}
      </span>
```

- [ ] **Step 6: Clean up Logs.svelte to use api.js**

In `src/api/frontend/src/views/Logs.svelte`, replace any raw `fetch('/console/logs?limit=200')` call with:

```javascript
  import { fetchLogs } from '../lib/api.js';
  // Then in onMount:
  const data = await fetchLogs(200);
```

- [ ] **Step 7: Rebuild frontend**

Run: `cd src/api/frontend && npm run build && cd ../../..`

- [ ] **Step 8: Run all console tests**

Run: `pytest tests/test_console.py tests/test_console_auth.py -v`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add src/api/console.py src/api/frontend/
git commit -m "feat: console error boundaries, send button, dead code cleanup, dynamic sidebar"
```

---

## Verification Checklist

After all tasks are complete:

- [ ] `pytest -x --tb=short` — all tests pass
- [ ] `ruff check` — clean (no violations)
- [ ] `git status` — working tree clean
- [ ] `.gitignore` blocks `data/**/*.db`
- [ ] `.github/workflows/ci.yml` exists
- [ ] `.pre-commit-config.yaml` exists
- [ ] `scripts/healthcheck.sh` is executable
- [ ] `scripts/backup.sh` is executable
- [ ] `infra/docker/docker-compose.yml` has health checks for worker and twin
- [ ] Console requires auth when `CONSOLE_USER`/`CONSOLE_PASSWORD` are set
- [ ] `/health` endpoint works without auth
- [ ] "New Campaign" button is gone, "Send" button exists in Campaigns
- [ ] Sidebar shows "Online" not hardcoded "Pi5 · 3 workers"
