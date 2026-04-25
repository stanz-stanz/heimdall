# SvelteKit Signup Site — Slice 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land a standalone SvelteKit site at `apps/signup/` (adapter-static) that renders 6 routes — landing, pricing, three legal stubs, and a magic-link `/signup/start` page that drives the Watchman activation flow — backed by a new read-only `POST /signup/validate` FastAPI endpoint. Slice-1 acceptance is dev-ready (Mac), not prod-ready (Hetzner = slice 2).

**Architecture:** SvelteKit project independent of `src/api/frontend/` (operator console). Vite dev server on `:5173` proxies `/api/*` → host `:8001` (the dev FastAPI container's host port; container internal is `:8000`). Bundle stays generic with relative `/api/*` fetches. Backend adds `src/api/signup.py` (`prefix="/signup"`, mirrors `console.py`); the new `POST /signup/validate` calls `src.db.signup.get_signup_token` (read-only) and returns a UX-shaped JSON payload. Token consumption stays in `src/db/onboarding.activate_watchman_trial`, called from the existing Telegram `/start <token>` handler — the SvelteKit landing never mutates DB state.

> **Spec divergence (corrected here, not silently):** the spec at line 48 says the Vite proxy targets `http://localhost:8000`. That's the FastAPI container's *internal* port. The dev compose overlay (`infra/compose/docker-compose.dev.yml:47`) maps it to host `:8001` to avoid colliding with other local services. This plan uses `:8001` because that is what `make dev-up` actually exposes; using `:8000` would 502 in dev. Surface to Federico as a one-line spec amendment after slice-1 ships.

**Tech Stack:** Svelte 5 + SvelteKit 2 + `@sveltejs/adapter-static` + Vite 6 + Vitest + jsdom + `qrcode` npm package. Backend: FastAPI + Pydantic + sqlite3 + loguru. Tests: pytest (`fakeredis`, `TestClient`) for the endpoint + round-trip; Vitest for the two library modules (`i18n`, `api`). Browser verification mandatory before final commit.

**Working tree assumption:** branch `feat/sentinel-onboarding`, working tree clean (verified: last commit `720db87`). All Python commits in this plan must be prefixed with `HEIMDALL_CODEX_REVIEWED=1` after a real Codex pass (per `.claude/hooks/precommit_codex_review_guard.py`).

---

## File structure

This plan creates these files:

**Backend** (slice-1 backend additions, all new):
- `src/api/signup.py` — FastAPI router (`prefix="/signup"`); single endpoint `POST /signup/validate`.
- `tests/_signup_test_helpers.py` — shared seed/issue/client helpers reused by the two test files (DRY; underscore prefix keeps pytest from collecting it).
- `tests/test_api_signup_validate.py` — pytest coverage of the endpoint (11 cases incl. true-concurrent validate, missing-`db_path` 503).
- `tests/test_signup_round_trip.py` — pytest coverage of validate → Telegram-activate → re-validate, plus the activation race.

**Backend modifications** (3 existing files):
- `src/api/app.py` — wire `signup.router`; one new line in the imports + one new `include_router` call.
- `infra/compose/docker-compose.yml` — add `TELEGRAM_BOT_USERNAME` env to the `api` service block.
- `infra/compose/.env.dev.example` — add the dev value (`HeimdallSecurityDEVbot`).

**SvelteKit project** at `apps/signup/`:
- `apps/signup/package.json` — Svelte 5, SvelteKit 2, adapter-static, Vite 6, Vitest, jsdom, qrcode.
- `apps/signup/svelte.config.js` — adapter-static config.
- `apps/signup/vite.config.js` — `/api/*` dev proxy → `http://localhost:8001` with `rewrite` to strip the prefix.
- `apps/signup/.gitignore` — local ignores (`node_modules/`, `build/`, `.svelte-kit/`).
- `apps/signup/src/app.html` — no-FOUC theme bootstrap (mirrors operator console index.html).
- `apps/signup/src/app.css` — base typography, layout primitives, `:focus-visible` rings.
- `apps/signup/src/styles/tokens.css` — copied verbatim from `src/api/frontend/src/styles/tokens.css`.
- `apps/signup/src/lib/i18n.js` — `t(key)` helper + locale store, EN-default with EN fallback.
- `apps/signup/src/lib/api.js` — fetch wrapper with normalised error shape.
- `apps/signup/src/lib/theme.js` — exposes `setTheme`/`currentTheme` stores; mirrors operator-console pattern (no toggle UI in slice 1).
- `apps/signup/src/lib/pricing.json` — Watchman + Sentinel cards.
- `apps/signup/src/messages/en.json` — source-of-truth strings.
- `apps/signup/src/messages/da.json` — `{}` (placeholder; slice 3).
- `apps/signup/src/routes/+layout.svelte` — nav + footer chrome.
- `apps/signup/src/routes/+page.svelte` — landing `/`.
- `apps/signup/src/routes/pricing/+page.svelte` — `/pricing`.
- `apps/signup/src/routes/legal/privacy/+page.svelte` — `/legal/privacy` stub.
- `apps/signup/src/routes/legal/terms/+page.svelte` — `/legal/terms` stub.
- `apps/signup/src/routes/legal/dpa/+page.svelte` — `/legal/dpa` stub.
- `apps/signup/src/routes/signup/start/+page.svelte` — magic-link landing.
- `apps/signup/static/favicon.svg` — self-hosted (no CDN).
- `apps/signup/static/robots.txt` — `User-agent: * / Disallow: /` (slice-1 dev-only).
- `apps/signup/tests/i18n.test.js` — Vitest unit tests.
- `apps/signup/tests/api.test.js` — Vitest unit tests.
- `apps/signup/vitest.config.js` — jsdom env config.

**Project root**:
- `Makefile` — three new phony targets: `signup-dev`, `signup-build`, `signup-test`.

---

## Task ordering and commit boundaries

Tasks group into seven logical commits:

1. **Backend** (Tasks 1–6): env var plumbing, `tests/test_api_signup_validate.py`, `tests/test_signup_round_trip.py`, `src/api/signup.py`, `src/api/app.py` wiring. Codex-reviewed before commit.
2. **SvelteKit scaffold** (Tasks 7–9): `apps/signup/` directory with package.json, vite/svelte configs, app.html, app.css, tokens copy, .gitignore.
3. **Library modules** (Tasks 10–12): i18n + api + theme with Vitest tests.
4. **Static content** (Task 13): messages, pricing.json, favicon, robots.
5. **Layout + simple pages** (Tasks 14–17): layout, landing, pricing, three legal stubs.
6. **Magic-link landing page** (Task 18): the `/signup/start` page wiring api.js + qrcode.
7. **Makefile + browser verification** (Tasks 19–20).

---

## Task 1: Add `TELEGRAM_BOT_USERNAME` env var to compose + dev example

**Files:**
- Modify: `infra/compose/docker-compose.yml:115-122` (api service `environment:` block)
- Modify: `infra/compose/.env.dev.example` (append at end)

The validate endpoint reads `TELEGRAM_BOT_USERNAME` at handler invocation. The variable must propagate into the `api` container in dev. Existing convention from `TELEGRAM_BOT_TOKEN` and `TELEGRAM_OPERATOR_CHAT_ID`: declare in compose with `${VAR:-}` placeholder, supply value via `.env.dev`.

This step touches `docker-compose.yml`, which is in the infra danger zone — the `infra_danger_zone.py` hook will inject the decision-log context (non-blocking). Expected.

- [ ] **Step 1: Add the env var declaration to the api service**

Edit `infra/compose/docker-compose.yml`. After the existing `BRIEFS_DIR` line (line 122), insert:

```yaml
      - TELEGRAM_BOT_USERNAME=${TELEGRAM_BOT_USERNAME:-}
```

Resulting block (verify):

```yaml
    environment:
      - REDIS_URL=redis://redis:6379/0
      - HEIMDALL_SOURCE=api
      - RESULTS_DIR=/data/results
      - MESSAGES_DIR=/data/messages
      - CONSOLE_USER=${CONSOLE_USER:-}
      - CLIENT_DATA_DIR=/data/clients
      - BRIEFS_DIR=/data/briefs
      - TELEGRAM_BOT_USERNAME=${TELEGRAM_BOT_USERNAME:-}
```

- [ ] **Step 2: Add the dev value to the example env file**

Edit `infra/compose/.env.dev.example`. After the existing `TELEGRAM_OPERATOR_CHAT_ID=` line, append:

```
TELEGRAM_BOT_USERNAME=HeimdallSecurityDEVbot
```

- [ ] **Step 3: Mirror the value into the operator's actual `.env.dev`** (manual, gitignored)

Run on the host:

```bash
test -f infra/compose/.env.dev || { echo "ERROR: infra/compose/.env.dev not present — copy .env.dev.example first" >&2; exit 1; }
grep -q '^TELEGRAM_BOT_USERNAME=' infra/compose/.env.dev || echo 'TELEGRAM_BOT_USERNAME=HeimdallSecurityDEVbot' >> infra/compose/.env.dev
```

Expected: silent success; subsequent `grep TELEGRAM_BOT_USERNAME infra/compose/.env.dev` returns the value. If `.env.dev` is missing, the operator must run `cp infra/compose/.env.dev.example infra/compose/.env.dev` and fill secrets first (per `make check-env`).

- [ ] **Step 4: Validate the dev compose still parses**

Run: `make compose-lint`
Expected: `==> both renders parse clean`.

(No commit yet — this lands in commit 1 with the rest of the backend changes in Task 6.)

---

## Task 2: Skeleton signup router + wire into app.py

**Files:**
- Create: `src/api/signup.py` (empty router only — no endpoints yet)
- Modify: `src/api/app.py:34` (imports), `src/api/app.py:416` (router registration)

This task lays the import surface so Task 3 can write a failing test. Without the empty router and the wiring, the test file would not even collect (the `from src.api.app import create_app` import would explode if app.py imported a missing `signup_router`). Implementation of the endpoint comes in Task 4 — strictly after the failing test runs.

- [ ] **Step 1: Create the skeleton router**

Write `src/api/signup.py`:

```python
"""Signup API router — magic-link token validation (read-only).

Endpoint bodies land in Task 4 (TDD).
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/signup", tags=["signup"])
```

- [ ] **Step 2: Add the import in app.py**

Edit `src/api/app.py`. Replace:

```python
from .console import router as console_router
from .result_store import ResultStore
```

with:

```python
from .console import router as console_router
from .result_store import ResultStore
from .signup import router as signup_router
```

- [ ] **Step 3: Register the router next to the console router**

Edit `src/api/app.py:416`. Replace:

```python
    # Console router + static PWA files
    app.include_router(console_router)
```

with:

```python
    # Console router + static PWA files
    app.include_router(console_router)
    app.include_router(signup_router)
```

- [ ] **Step 4: Verify the import surface**

Run: `python -c "from src.api.signup import router; print(router.prefix)"`
Expected: `/signup` printed. No import error.

(No commit yet — this lands in commit 1 with the rest of the backend changes in Task 6.)

---

## Task 3: TDD red — fixtures + first failing test

**Files:**
- Create: `tests/test_api_signup_validate.py`

The fixture pattern mirrors `tests/test_console_endpoints.py:104-124`: fakeredis monkeypatch + `TestClient(create_app(...))` + `app.state.db_path = test_db`. The `signup_tokens` table is created by `init_db` (the schema lives in `docs/architecture/client-db-schema.sql`).

The dev allowlist includes both `localhost:5173` AND `127.0.0.1:5173` because Vite logs the latter and a browser navigated to either form sends the corresponding `Origin`. Mismatching the host literal would 403 every browser call.

- [ ] **Step 1: Create the file with imports, fixtures, and ONE failing test**

Write `tests/test_api_signup_validate.py`:

```python
"""Tests for src.api.signup.validate — read-only magic-link token check."""

from __future__ import annotations

import sqlite3
import threading
from datetime import UTC, datetime, timedelta

import fakeredis
import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.db.connection import init_db
from src.db.signup import consume_signup_token, create_signup_token

ORIGIN_DEV_LOCALHOST = "http://localhost:5173"
ORIGIN_DEV_LOOPBACK = "http://127.0.0.1:5173"
ORIGIN_PROD = "https://signup.digitalvagt.dk"
BAD_ORIGIN = "https://attacker.example"

SEED_CVR = "12345678"
SEED_COMPANY = "Test Restaurant ApS"
SEED_NOW = "2026-04-25T10:00:00Z"


@pytest.fixture
def db_path(tmp_path):
    """Initialise a fresh clients.db with a known CVR row."""
    db_file = tmp_path / "clients.db"
    conn = init_db(str(db_file))
    conn.execute(
        "INSERT INTO clients (cvr, company_name, status, plan, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (SEED_CVR, SEED_COMPANY, "prospect", "watchman", SEED_NOW, SEED_NOW),
    )
    conn.commit()
    conn.close()
    return str(db_file)


@pytest.fixture
def client(db_path, tmp_path, monkeypatch):
    """FastAPI TestClient bound to a fresh DB and fakeredis."""
    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr("redis.Redis.from_url", lambda *a, **kw: fake)
    monkeypatch.setenv("TELEGRAM_BOT_USERNAME", "HeimdallSecurityDEVbot")
    monkeypatch.setenv(
        "SIGNUP_ALLOWED_ORIGINS",
        ",".join([ORIGIN_DEV_LOCALHOST, ORIGIN_DEV_LOOPBACK, ORIGIN_PROD]),
    )
    monkeypatch.chdir(tmp_path)
    app = create_app(
        redis_url="redis://fake:6379/0",
        results_dir=str(tmp_path / "results"),
        briefs_dir=str(tmp_path / "briefs"),
    )
    app.state.db_path = db_path
    with TestClient(app) as tc:
        yield tc


@pytest.fixture
def issued_token(db_path):
    """Issue a fresh signup token bound to the seeded CVR."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        result = create_signup_token(
            conn, cvr=SEED_CVR, email="owner@test-restaurant.dk"
        )
    finally:
        conn.close()
    return result["token"]


class TestValidateHappyPath:
    def test_valid_token_returns_ok_and_bot_username(self, client, issued_token):
        resp = client.post(
            "/signup/validate",
            json={"token": issued_token},
            headers={"Origin": ORIGIN_DEV_LOCALHOST},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["bot_username"] == "HeimdallSecurityDEVbot"
```

- [ ] **Step 2: Run the test — must FAIL because the endpoint isn't implemented**

Run: `python -m pytest tests/test_api_signup_validate.py::TestValidateHappyPath -v --no-cov`
Expected: 1 test runs and FAILs with `404 Not Found` (router exists, endpoint does not). Module collection succeeds (imports resolve to the empty router from Task 2).

This is the canonical TDD red. Move to Task 4 only after seeing this failure.

---

## Task 4: TDD green — implement the validate endpoint

**Files:**
- Modify: `src/api/signup.py` (replace skeleton with full implementation)

- [ ] **Step 1: Replace the skeleton with the full implementation**

Replace the entire contents of `src/api/signup.py` with:

```python
"""Signup API router — magic-link token validation (read-only)."""

from __future__ import annotations

import os
import sqlite3
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request
from loguru import logger
from pydantic import BaseModel

from src.db.signup import get_signup_token

router = APIRouter(prefix="/signup", tags=["signup"])


class ValidateBody(BaseModel):
    token: str


def _allowed_origins() -> set[str]:
    raw = os.environ.get(
        "SIGNUP_ALLOWED_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    )
    return {o.strip() for o in raw.split(",") if o.strip()}


def _open_clients_db(request: Request) -> sqlite3.Connection:
    db_path = getattr(request.app.state, "db_path", None)
    if not db_path:
        raise HTTPException(503, "clients_db_unavailable")
    conn = sqlite3.connect(db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


@router.post("/validate")
async def validate(request: Request, body: ValidateBody):
    """Read-only check on a magic-link token. Never mutates state.

    Token consumption happens later in
    src/db/onboarding.py:activate_watchman_trial via the Telegram
    /start <token> handler.
    """
    if request.headers.get("origin") not in _allowed_origins():
        raise HTTPException(403, "origin_not_allowed")

    bot_username = os.environ.get("TELEGRAM_BOT_USERNAME")
    if not bot_username:
        logger.error("signup_validate_missing_bot_username")
        raise HTTPException(503, "bot_username_unconfigured")

    conn = _open_clients_db(request)
    try:
        row = get_signup_token(conn, body.token)
    finally:
        conn.close()

    if row is None:
        return {"ok": False, "reason": "invalid"}
    if row["consumed_at"] is not None:
        return {"ok": False, "reason": "used"}
    expires_at = datetime.fromisoformat(row["expires_at"].replace("Z", "+00:00"))
    if expires_at <= datetime.now(UTC):
        return {"ok": False, "reason": "expired"}

    return {"ok": True, "bot_username": bot_username}
```

Two deliberate divergences from the spec, both more defensive:

1. **Bot-username failure mode.** Spec used `os.environ["TELEGRAM_BOT_USERNAME"]` (KeyError → 500). We use `.get()` and return a clean 503 with a logged error so misconfiguration surfaces as a typed error rather than an opaque 500.
2. **Default allowlist.** Spec listed only `http://localhost:5173`; we add `http://127.0.0.1:5173` because Vite binds to and logs the loopback literal (browsers navigated there send a corresponding `Origin`). Production deployments override the default via `SIGNUP_ALLOWED_ORIGINS` (the slice-2 Caddy-fronted box sets it to `https://signup.digitalvagt.dk`).

- [ ] **Step 2: Re-run the failing test — must now PASS**

Run: `python -m pytest tests/test_api_signup_validate.py::TestValidateHappyPath -v --no-cov`
Expected: 1/1 PASS. TDD green.

---

## Task 5: Add the remaining test cases

**Files:**
- Modify: `tests/test_api_signup_validate.py`

Cover: nonexistent → invalid; consumed → used; expired → expired; both dev origins accepted; bad origin → 403; missing Origin → 403; missing TELEGRAM_BOT_USERNAME → 503; **missing app.state.db_path → 503**; validate doesn't mutate token; truly-concurrent validate calls (two threads) both succeed and don't consume.

- [ ] **Step 1: Add the four reason-branch tests**

Append to `tests/test_api_signup_validate.py`:

```python
class TestValidateReasons:
    def test_unknown_token_returns_invalid(self, client):
        resp = client.post(
            "/signup/validate",
            json={"token": "nonexistent-token-abc123"},
            headers={"Origin": ORIGIN_DEV_LOCALHOST},
        )
        assert resp.status_code == 200
        assert resp.json() == {"ok": False, "reason": "invalid"}

    def test_consumed_token_returns_used(self, client, issued_token, db_path):
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            consume_signup_token(conn, issued_token)
        finally:
            conn.close()

        resp = client.post(
            "/signup/validate",
            json={"token": issued_token},
            headers={"Origin": ORIGIN_DEV_LOCALHOST},
        )
        assert resp.status_code == 200
        assert resp.json() == {"ok": False, "reason": "used"}

    def test_expired_token_returns_expired(self, client, db_path):
        past = (datetime.now(UTC) - timedelta(minutes=5)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        conn = sqlite3.connect(db_path)
        try:
            conn.execute(
                """
                INSERT INTO signup_tokens
                  (token, cvr, email, source, expires_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    "expired-token-xyz",
                    SEED_CVR,
                    None,
                    "email_reply",
                    past,
                    "2026-04-25T09:00:00Z",
                ),
            )
            conn.commit()
        finally:
            conn.close()

        resp = client.post(
            "/signup/validate",
            json={"token": "expired-token-xyz"},
            headers={"Origin": ORIGIN_DEV_LOCALHOST},
        )
        assert resp.status_code == 200
        assert resp.json() == {"ok": False, "reason": "expired"}

    def test_both_dev_origins_accepted(self, client, issued_token):
        for origin in (ORIGIN_DEV_LOCALHOST, ORIGIN_DEV_LOOPBACK, ORIGIN_PROD):
            resp = client.post(
                "/signup/validate",
                json={"token": issued_token},
                headers={"Origin": origin},
            )
            assert resp.status_code == 200, f"Origin {origin} failed"
            assert resp.json()["ok"] is True
```

- [ ] **Step 2: Add the failure-mode tests (incl. the missing db_path guard Codex flagged)**

Append to `tests/test_api_signup_validate.py`:

```python
class TestValidateGuards:
    def test_bad_origin_is_403(self, client, issued_token):
        resp = client.post(
            "/signup/validate",
            json={"token": issued_token},
            headers={"Origin": BAD_ORIGIN},
        )
        assert resp.status_code == 403

    def test_missing_origin_is_403(self, client, issued_token):
        resp = client.post(
            "/signup/validate",
            json={"token": issued_token},
        )
        assert resp.status_code == 403

    def test_missing_bot_username_is_503(
        self, client, issued_token, monkeypatch
    ):
        monkeypatch.delenv("TELEGRAM_BOT_USERNAME", raising=False)
        resp = client.post(
            "/signup/validate",
            json={"token": issued_token},
            headers={"Origin": ORIGIN_DEV_LOCALHOST},
        )
        assert resp.status_code == 503

    def test_missing_db_path_is_503(self, client, issued_token):
        # Strip db_path from app.state so _open_clients_db hits its
        # 503 guard. We restore it after the assertion so the fixture
        # teardown doesn't see a half-broken app.
        app = client.app
        original = getattr(app.state, "db_path", None)
        try:
            app.state.db_path = None
            resp = client.post(
                "/signup/validate",
                json={"token": issued_token},
                headers={"Origin": ORIGIN_DEV_LOCALHOST},
            )
            assert resp.status_code == 503
        finally:
            app.state.db_path = original

    def test_validate_does_not_mutate_token(
        self, client, issued_token, db_path
    ):
        client.post(
            "/signup/validate",
            json={"token": issued_token},
            headers={"Origin": ORIGIN_DEV_LOCALHOST},
        )
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT consumed_at, email FROM signup_tokens WHERE token = ?",
                (issued_token,),
            ).fetchone()
        finally:
            conn.close()
        assert row["consumed_at"] is None
        assert row["email"] == "owner@test-restaurant.dk"

    def test_concurrent_validates_both_succeed_and_dont_consume(
        self, client, issued_token, db_path
    ):
        """Per spec: two truly-concurrent validate calls must both
        succeed AND the DB token state must be unchanged after both.

        TestClient is thread-safe (httpx underneath); we use a
        threading.Barrier so the requests fire as close to
        simultaneously as the kernel allows.
        """
        results: list[dict] = []
        results_lock = threading.Lock()
        barrier = threading.Barrier(2, timeout=2)

        def worker():
            barrier.wait(timeout=2)
            r = client.post(
                "/signup/validate",
                json={"token": issued_token},
                headers={"Origin": ORIGIN_DEV_LOCALHOST},
            )
            with results_lock:
                results.append({"status": r.status_code, "body": r.json()})

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert len(results) == 2
        assert all(r["status"] == 200 for r in results)
        assert all(r["body"]["ok"] is True for r in results)

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT consumed_at, email FROM signup_tokens WHERE token = ?",
                (issued_token,),
            ).fetchone()
            count = conn.execute(
                "SELECT COUNT(*) AS n FROM signup_tokens WHERE token = ?",
                (issued_token,),
            ).fetchone()["n"]
        finally:
            conn.close()
        assert row["consumed_at"] is None
        assert row["email"] == "owner@test-restaurant.dk"
        assert count == 1
```

- [ ] **Step 3: Run the full validate suite — must PASS**

Run: `python -m pytest tests/test_api_signup_validate.py -v --no-cov`
Expected: 11/11 PASS (TestValidateHappyPath × 1 + TestValidateReasons × 4 + TestValidateGuards × 6).

If any test fails: read the failure output, fix the implementation in `src/api/signup.py`, re-run. Do **not** mark this step complete until 11/11 green.

---

## Task 6: Round-trip + race-condition test (validate ↔ activate)

**Files:**
- Create: `tests/_signup_test_helpers.py` — shared db/client/issue helpers (DRY for the two test files)
- Create: `tests/test_signup_round_trip.py`
- Modify: `tests/test_api_signup_validate.py` — replace inline fixtures with imports from the helper module

This proves the spec's central design claim: validate is read-only, the **only** state-mutation path is `activate_watchman_trial`, and concurrent activations cannot both win.

- [ ] **Step 0: Extract shared fixtures**

Both test files need the same `clients.db` seed (`12345678` / `Test Restaurant ApS`) and the same FastAPI test-client wiring. Drift on the seed values silently breaks the round-trip suite. Move the helpers into `tests/_signup_test_helpers.py`:

Write `tests/_signup_test_helpers.py`:

```python
"""Shared helpers for the signup-validate + round-trip test files.

Underscore-prefixed so pytest does not collect it as a test module.
"""

from __future__ import annotations

import sqlite3

import fakeredis
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.db.connection import init_db
from src.db.signup import create_signup_token

ORIGIN_DEV_LOCALHOST = "http://localhost:5173"
ORIGIN_DEV_LOOPBACK = "http://127.0.0.1:5173"
ORIGIN_PROD = "https://signup.digitalvagt.dk"
BAD_ORIGIN = "https://attacker.example"

SEED_CVR = "12345678"
SEED_COMPANY = "Test Restaurant ApS"
SEED_NOW = "2026-04-25T10:00:00Z"


def init_seeded_db(db_file_path: str) -> None:
    """Initialise a fresh clients.db with the canonical seed CVR row."""
    conn = init_db(db_file_path)
    conn.execute(
        "INSERT INTO clients (cvr, company_name, status, plan, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (SEED_CVR, SEED_COMPANY, "prospect", "watchman", SEED_NOW, SEED_NOW),
    )
    conn.commit()
    conn.close()


def issue_token(db_path: str, *, email: str | None = None) -> str:
    """Issue a fresh signup token bound to the seeded CVR. Returns the token string."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        result = create_signup_token(conn, cvr=SEED_CVR, email=email)
    finally:
        conn.close()
    return result["token"]


def make_client(db_path: str, tmp_path, monkeypatch) -> TestClient:
    """Build a FastAPI TestClient bound to a fresh DB and fakeredis."""
    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr("redis.Redis.from_url", lambda *a, **kw: fake)
    monkeypatch.setenv("TELEGRAM_BOT_USERNAME", "HeimdallSecurityDEVbot")
    monkeypatch.setenv(
        "SIGNUP_ALLOWED_ORIGINS",
        ",".join([ORIGIN_DEV_LOCALHOST, ORIGIN_DEV_LOOPBACK, ORIGIN_PROD]),
    )
    monkeypatch.chdir(tmp_path)
    app = create_app(
        redis_url="redis://fake:6379/0",
        results_dir=str(tmp_path / "results"),
        briefs_dir=str(tmp_path / "briefs"),
    )
    app.state.db_path = db_path
    return TestClient(app)
```

Then refactor `tests/test_api_signup_validate.py` — replace its top-of-file imports, constants, and the inline `db_path` / `client` / `issued_token` fixtures (defined in Task 3) with:

```python
"""Tests for src.api.signup.validate — read-only magic-link token check."""

from __future__ import annotations

import sqlite3
import threading
from datetime import UTC, datetime, timedelta

import pytest

from src.db.signup import consume_signup_token

from tests._signup_test_helpers import (
    BAD_ORIGIN,
    ORIGIN_DEV_LOCALHOST,
    ORIGIN_DEV_LOOPBACK,
    ORIGIN_PROD,
    SEED_CVR,
    init_seeded_db,
    issue_token,
    make_client,
)


@pytest.fixture
def db_path(tmp_path):
    db_file = tmp_path / "clients.db"
    init_seeded_db(str(db_file))
    return str(db_file)


@pytest.fixture
def client(db_path, tmp_path, monkeypatch):
    with make_client(db_path, tmp_path, monkeypatch) as tc:
        yield tc


@pytest.fixture
def issued_token(db_path):
    return issue_token(db_path, email="owner@test-restaurant.dk")
```

Leave the `class TestValidateHappyPath` / `class TestValidateReasons` / `class TestValidateGuards` blocks intact below the new imports — only the top of the file changes.

Run the validate suite to confirm nothing broke during the refactor:

```
python -m pytest tests/test_api_signup_validate.py -v --no-cov
```

Expected: still 11/11 PASS.

- [ ] **Step 1: Create the round-trip test file**

Write `tests/test_signup_round_trip.py`:

```python
"""End-to-end round trip: SvelteKit validate → Telegram /start activation."""

from __future__ import annotations

import sqlite3
import threading

import pytest

from src.db.onboarding import InvalidSignupToken, activate_watchman_trial

from tests._signup_test_helpers import (
    ORIGIN_DEV_LOCALHOST,
    SEED_CVR,
    init_seeded_db,
    issue_token,
    make_client,
)


@pytest.fixture
def db_path(tmp_path):
    db_file = tmp_path / "clients.db"
    init_seeded_db(str(db_file))
    return str(db_file)


@pytest.fixture
def client(db_path, tmp_path, monkeypatch):
    with make_client(db_path, tmp_path, monkeypatch) as tc:
        yield tc


class TestRoundTrip:
    def test_validate_does_not_consume_then_activate_does(
        self, client, db_path
    ):
        token = issue_token(db_path)

        # Step 1: validate succeeds, token unchanged
        resp = client.post(
            "/signup/validate",
            json={"token": token},
            headers={"Origin": ORIGIN_DEV_LOCALHOST},
        )
        assert resp.json() == {
            "ok": True,
            "bot_username": "HeimdallSecurityDEVbot",
        }

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT consumed_at FROM signup_tokens WHERE token = ?",
                (token,),
            ).fetchone()
            assert row["consumed_at"] is None
        finally:
            conn.close()

        # Step 2: Telegram /start handler activates
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            client_row = activate_watchman_trial(
                conn, token, "tg_chat_id_123"
            )
        finally:
            conn.close()
        assert client_row["status"] == "watchman_active"
        assert client_row["plan"] == "watchman"
        assert client_row["telegram_chat_id"] == "tg_chat_id_123"

        # Step 3: validate now reports used
        resp = client.post(
            "/signup/validate",
            json={"token": token},
            headers={"Origin": ORIGIN_DEV_LOCALHOST},
        )
        assert resp.json() == {"ok": False, "reason": "used"}

        # Step 4: signup_tokens.email is nulled per Art 5(1)(e)
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT email, consumed_at FROM signup_tokens WHERE token = ?",
                (token,),
            ).fetchone()
            assert row["email"] is None
            assert row["consumed_at"] is not None
        finally:
            conn.close()

        # Step 5: exactly one conversion event
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            count = conn.execute(
                "SELECT COUNT(*) AS n FROM conversion_events "
                "WHERE cvr = ? AND event_type = 'signup'",
                (SEED_CVR,),
            ).fetchone()["n"]
            assert count == 1
        finally:
            conn.close()


class TestActivationRace:
    def test_two_concurrent_activations_one_wins(self, db_path):
        token = issue_token(db_path)
        outcomes: list[str] = []
        barrier = threading.Barrier(2)

        def worker(chat_id: str) -> None:
            conn = sqlite3.connect(db_path, timeout=10)
            conn.row_factory = sqlite3.Row
            try:
                barrier.wait(timeout=2)
                activate_watchman_trial(conn, token, chat_id)
                outcomes.append(f"ok:{chat_id}")
            except InvalidSignupToken:
                outcomes.append(f"raised:{chat_id}")
            finally:
                conn.close()

        t1 = threading.Thread(target=worker, args=("chat_1",))
        t2 = threading.Thread(target=worker, args=("chat_2",))
        t1.start()
        t2.start()
        t1.join(timeout=5)
        t2.join(timeout=5)

        assert sorted(outcomes)[:1][0].startswith("ok:")
        wins = [o for o in outcomes if o.startswith("ok:")]
        losses = [o for o in outcomes if o.startswith("raised:")]
        assert len(wins) == 1
        assert len(losses) == 1
```

- [ ] **Step 2: Run the round-trip suite**

Run: `python -m pytest tests/test_signup_round_trip.py -v --no-cov`
Expected: 2/2 PASS (TestRoundTrip + TestActivationRace).

- [ ] **Step 3: Run the full slice-1 backend test set together**

Run: `python -m pytest tests/test_api_signup_validate.py tests/test_signup_round_trip.py tests/test_db_signup.py tests/test_db_onboarding.py -v --no-cov`
Expected: all green.

- [ ] **Step 4: Codex-review the backend changes**

Run: `node ~/.claude/plugins/cache/openai-codex/codex/1.0.4/scripts/codex-companion.mjs review ""`
Read the output. Address any must-fix items in `src/api/signup.py`, `tests/test_api_signup_validate.py`, `tests/test_signup_round_trip.py`. Re-run Codex until clean.

- [ ] **Step 5: Commit the backend slice**

```bash
git add infra/compose/docker-compose.yml infra/compose/.env.dev.example \
        src/api/signup.py src/api/app.py \
        tests/_signup_test_helpers.py \
        tests/test_api_signup_validate.py tests/test_signup_round_trip.py
HEIMDALL_CODEX_REVIEWED=1 git commit -m "$(cat <<'EOF'
feat(api): POST /signup/validate — read-only magic-link check

Adds src/api/signup.py with a single read-only endpoint that the
SvelteKit /signup/start landing calls to decide which UI to render.
Token consumption stays in src/db/onboarding.activate_watchman_trial,
called from the existing Telegram /start handler — the validate
endpoint never mutates DB state.

- Origin allowlist via SIGNUP_ALLOWED_ORIGINS (defaults to dev only).
- TELEGRAM_BOT_USERNAME wired into api compose env (dev value
  HeimdallSecurityDEVbot in .env.dev.example).
- Round-trip + activation-race tests assert the read-only contract.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

Run `git status` to confirm.

---

## Task 7: Scaffold `apps/signup/` SvelteKit project

**Files:**
- Create: `apps/signup/package.json`
- Create: `apps/signup/svelte.config.js`
- Create: `apps/signup/vite.config.js`
- Create: `apps/signup/vitest.config.js`
- Create: `apps/signup/.gitignore`
- Create: `apps/signup/jsconfig.json`

The project lives at `apps/signup/` (new `apps/` top-level directory). Independent `node_modules`, independent `package.json`. Builds to `apps/signup/build/` (gitignored).

- [ ] **Step 1: Create the directory and package.json**

```bash
mkdir -p apps/signup/src/routes/signup/start \
         apps/signup/src/routes/legal/privacy \
         apps/signup/src/routes/legal/terms \
         apps/signup/src/routes/legal/dpa \
         apps/signup/src/routes/pricing \
         apps/signup/src/lib \
         apps/signup/src/styles \
         apps/signup/src/messages \
         apps/signup/static \
         apps/signup/tests
```

Write `apps/signup/package.json`:

```json
{
  "name": "heimdall-signup",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite dev --port 5173 --host 127.0.0.1",
    "build": "vite build",
    "preview": "vite preview",
    "test": "vitest run"
  },
  "devDependencies": {
    "@sveltejs/adapter-static": "^3.0.0",
    "@sveltejs/kit": "^2.0.0",
    "@sveltejs/vite-plugin-svelte": "^5.0.0",
    "@testing-library/svelte": "^5.2.4",
    "jsdom": "^25.0.0",
    "svelte": "^5.0.0",
    "vite": "^6.0.0",
    "vitest": "^2.1.0"
  },
  "dependencies": {
    "qrcode": "^1.5.4"
  }
}
```

- [ ] **Step 2: Create svelte.config.js (adapter-static)**

Write `apps/signup/svelte.config.js`:

```javascript
import adapter from '@sveltejs/adapter-static';

/** @type {import('@sveltejs/kit').Config} */
const config = {
  kit: {
    adapter: adapter({
      pages: 'build',
      assets: 'build',
      fallback: '404.html',
      precompress: false,
      strict: true,
    }),
    alias: {
      $lib: 'src/lib',
    },
  },
};

export default config;
```

`fallback: '404.html'` is required: adapter-static prerenders all routes; the `/signup/start` page reads `?t=<token>` at runtime so SvelteKit's client-side router needs a fallback when the prerender misses dynamic searches. (Routes themselves are static — only the query param is runtime.)

- [ ] **Step 3: Create vite.config.js with the dev proxy**

Write `apps/signup/vite.config.js`:

```javascript
import { defineConfig } from 'vite';
import { sveltekit } from '@sveltejs/kit/vite';

export default defineConfig({
  plugins: [sveltekit()],
  server: {
    port: 5173,
    host: '127.0.0.1',
    proxy: {
      '/api': {
        target: 'http://localhost:8001',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
});
```

`localhost:8001` is the dev FastAPI host port (verified: `infra/compose/docker-compose.dev.yml:47` maps `8001:8000`). The `rewrite` strips `/api` so `/api/signup/validate` reaches backend `/signup/validate` (matching the production Caddy strip-prefix behaviour from the cloud-hosting plan).

`changeOrigin: true` rewrites the upstream `Host` header to `localhost:8001` so the backend sees the request as locally-bound. **Failure-mode note:** some `http-proxy` versions also strip the browser-supplied `Origin` header when `changeOrigin` is set, which would 403 every valid validate call. The browser-verification step (Task 20 Step 4) is the canary for this. If a 403 surfaces in dev with a valid Origin header in DevTools, switch to `xfwd: true` and inspect the upstream request via `docker logs heimdall_dev-api-1` — do **not** mis-diagnose as a backend bug.

- [ ] **Step 4: Create vitest.config.js (jsdom env)**

Write `apps/signup/vitest.config.js`:

```javascript
import { defineConfig } from 'vitest/config';
import { svelte } from '@sveltejs/vite-plugin-svelte';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = fileURLToPath(new URL('.', import.meta.url));

export default defineConfig({
  plugins: [svelte({ hot: false })],
  test: {
    environment: 'jsdom',
    include: ['tests/**/*.test.js'],
    globals: false,
  },
  resolve: {
    alias: {
      $lib: resolve(__dirname, 'src/lib'),
    },
  },
});
```

A leading `'/src/lib'` would resolve to filesystem root and break test imports. The `resolve(__dirname, 'src/lib')` pattern anchors to the apps/signup/ directory regardless of the cwd Vitest is invoked from.

- [ ] **Step 5: Create .gitignore for the SvelteKit project**

Write `apps/signup/.gitignore`:

```
node_modules/
.svelte-kit/
.env
.env.local
.env.development
.env.production
.DS_Store
```

`build/` is already covered by the repo-root `.gitignore:52`. SvelteKit's standard `.env` filenames are listed explicitly so a `.env.example` (if added in slice 2 for Postmark) is committable without negation gymnastics.

- [ ] **Step 6: Create jsconfig.json (editor support)**

Write `apps/signup/jsconfig.json`:

```json
{
  "extends": "./.svelte-kit/tsconfig.json",
  "compilerOptions": {
    "allowJs": true,
    "checkJs": false,
    "esModuleInterop": true,
    "forceConsistentCasingInFileNames": true,
    "resolveJsonModule": true,
    "skipLibCheck": true,
    "strict": true
  }
}
```

- [ ] **Step 7: Install dependencies**

Run from project root:

```bash
cd apps/signup && npm install --prefer-offline && cd -
```

Expected: `node_modules/` populated, no errors. Network calls allowed for the first install.

(No commit yet — landing in commit 2 with the rest of the scaffold.)

---

## Task 8: app.html, app.css, tokens copy

**Files:**
- Create: `apps/signup/src/app.html`
- Create: `apps/signup/src/app.css`
- Create: `apps/signup/src/styles/tokens.css` (verbatim copy)

- [ ] **Step 1: Copy tokens.css verbatim**

Run from project root:

```bash
cp src/api/frontend/src/styles/tokens.css apps/signup/src/styles/tokens.css
```

Verify size:

```bash
diff -q src/api/frontend/src/styles/tokens.css apps/signup/src/styles/tokens.css
```

Expected: silent (files match).

- [ ] **Step 2: Create app.html with no-FOUC theme bootstrap**

Write `apps/signup/src/app.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <meta name="description" content="Digital Vagt — Heimdall security monitoring for Danish small businesses." />
  <link rel="icon" href="%sveltekit.assets%/favicon.svg" type="image/svg+xml" />
  <title>Digital Vagt</title>
  <script>
    // No-FOUC theme bootstrap — runs before the SvelteKit bundle mounts.
    // Mirrors src/api/frontend/index.html.
    (function () {
      try {
        var stored = localStorage.getItem('heimdall.theme');
        var mode =
          stored === 'dark' || stored === 'light'
            ? stored
            : window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches
            ? 'light'
            : 'dark';
        document.documentElement.setAttribute('data-theme', mode);
      } catch (e) {
        document.documentElement.setAttribute('data-theme', 'dark');
      }
    })();
  </script>
  %sveltekit.head%
</head>
<body data-sveltekit-preload-data="hover">
  <div id="svelte" style="display: contents">%sveltekit.body%</div>
</body>
</html>
```

`<html lang="en">` is hard-coded for slice 1 (EN-only). Slice 3 will swap to a runtime locale attribute when DA translations land — but adapter-static prerenders against a single locale, so a per-route lang flip needs a SvelteKit hook (`handle` in `src/hooks.server.js`) or a build-time multi-locale prerender. Both are slice-3 work.

- [ ] **Step 3: Create app.css with base typography + focus rings**

Write `apps/signup/src/app.css`:

```css
@import './styles/tokens.css';

:root {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto,
    'Helvetica Neue', Arial, sans-serif;
  font-size: 16px;
  line-height: 1.5;
  color: var(--text);
  background: var(--bg-base);
  -webkit-font-smoothing: antialiased;
  text-rendering: optimizeLegibility;
}

*,
*::before,
*::after {
  box-sizing: border-box;
}

body {
  margin: 0;
  min-height: 100vh;
  background: var(--bg-base);
  color: var(--text);
}

a {
  color: var(--gold);
  text-decoration: none;
}

a:hover {
  text-decoration: underline;
}

a:focus-visible,
button:focus-visible {
  outline: 2px solid var(--gold);
  outline-offset: 2px;
}

h1, h2, h3 {
  margin: 0 0 0.5em;
  line-height: 1.25;
}

h1 {
  font-size: 2.25rem;
  letter-spacing: -0.02em;
}

h2 {
  font-size: 1.5rem;
  letter-spacing: -0.01em;
}

p {
  margin: 0 0 1em;
  max-width: 65ch;
}

.container {
  max-width: 960px;
  margin: 0 auto;
  padding: 2rem 1.5rem;
}

.btn {
  display: inline-block;
  padding: 0.75rem 1.25rem;
  background: var(--gold);
  color: var(--bg-deep);
  border-radius: 6px;
  font-weight: 600;
  border: none;
  cursor: pointer;
  font-size: 1rem;
}

.btn:hover {
  background: var(--gold-dim);
  text-decoration: none;
}

.btn-outline {
  background: transparent;
  color: var(--gold);
  border: 1px solid var(--gold);
}

.btn-outline:hover {
  background: var(--gold-glow);
}

.muted {
  color: var(--text-dim);
}

.disclaimer {
  padding: 1rem 1.25rem;
  border-left: 3px solid var(--orange);
  background: var(--orange-dim);
  border-radius: 0 6px 6px 0;
  margin: 1.5rem 0;
}
```

Don't create files for unused tokens — the import pulls everything from tokens.css. Slice 1 uses a strict subset (`--gold`, `--text`, `--bg-*`, `--orange-dim`); leaving the rest available for slice 3.

(No commit yet.)

---

## Task 9: Library: theme.js + first commit (scaffold)

**Files:**
- Create: `apps/signup/src/lib/theme.js`

- [ ] **Step 1: Create theme.js**

Write `apps/signup/src/lib/theme.js`:

```javascript
import { writable } from 'svelte/store';
import { browser } from '$app/environment';

const STORAGE_KEY = 'heimdall.theme';

function readInitial() {
  if (!browser) return 'dark';
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === 'dark' || stored === 'light') return stored;
    if (window.matchMedia('(prefers-color-scheme: light)').matches) return 'light';
  } catch (e) {
    // ignore
  }
  return 'dark';
}

export const theme = writable(readInitial());

export function setTheme(next) {
  if (next !== 'dark' && next !== 'light') return;
  theme.set(next);
  if (browser) {
    try {
      localStorage.setItem(STORAGE_KEY, next);
      document.documentElement.setAttribute('data-theme', next);
    } catch (e) {
      // ignore
    }
  }
}
```

This mirrors the operator-console pattern at `src/api/frontend/src/lib/theme.svelte.js` (Svelte 5 runes there; we use plain stores here since we don't need fine-grained reactivity in slice 1).

- [ ] **Step 2: Commit the SvelteKit scaffold**

Pure JS/CSS/JSON; no Codex requirement (hook checks for `src/**/*.py` and `tests/**/*.py`).

```bash
git add apps/signup/
git commit -m "$(cat <<'EOF'
feat(signup): scaffold SvelteKit project at apps/signup/

apps/signup/ is independent of src/api/frontend/ (operator console).
Adapter-static, Vite dev server on :5173 with /api proxy to the dev
FastAPI host port :8001. No-FOUC theme bootstrap mirrors the operator
console. Tokens copied verbatim from src/api/frontend/src/styles/.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: i18n.js — TDD with Vitest

**Files:**
- Create: `apps/signup/tests/i18n.test.js`
- Create: `apps/signup/src/lib/i18n.js`
- Create: `apps/signup/src/messages/en.json` (minimal seed for tests)
- Create: `apps/signup/src/messages/da.json` (empty `{}`)

- [ ] **Step 1: Create empty messages first so the import works**

Write `apps/signup/src/messages/en.json`:

```json
{
  "nav.brand": "Digital Vagt",
  "nav.pricing": "Pricing",
  "nav.signin": "Sign in",
  "footer.copyright": "© 2026 Digital Vagt ApS"
}
```

Write `apps/signup/src/messages/da.json`:

```json
{}
```

(Slice 3 will populate `da.json` with the full Danish translations.)

- [ ] **Step 2: Write the failing tests**

Write `apps/signup/tests/i18n.test.js`:

```javascript
import { describe, it, expect, beforeEach } from 'vitest';
import { get } from 'svelte/store';
import { t, locale, setLocale } from '$lib/i18n';

describe('i18n', () => {
  beforeEach(() => {
    setLocale('en');
  });

  it('returns the EN string for a known key', () => {
    expect(t('nav.brand')).toBe('Digital Vagt');
  });

  it('falls back to EN when the DA dict is missing the key', () => {
    setLocale('da');
    expect(t('nav.brand')).toBe('Digital Vagt');
  });

  it('returns the key itself when neither locale has it', () => {
    expect(t('nonexistent.key')).toBe('nonexistent.key');
  });

  it('updates locale via setLocale', () => {
    setLocale('da');
    expect(get(locale)).toBe('da');
    setLocale('en');
    expect(get(locale)).toBe('en');
  });

  it('ignores unknown locale codes', () => {
    setLocale('en');
    setLocale('zz'); // not registered
    expect(get(locale)).toBe('en');
  });
});
```

- [ ] **Step 3: Run vitest — must FAIL because i18n.js does not exist yet**

```bash
cd apps/signup && npm run test
```

Expected: 5 failures, all "Cannot resolve $lib/i18n".

- [ ] **Step 4: Implement i18n.js**

Write `apps/signup/src/lib/i18n.js`:

```javascript
import { writable, get } from 'svelte/store';
import en from '../messages/en.json';
import da from '../messages/da.json';

const dicts = { en, da };

export const locale = writable('en');

export function setLocale(next) {
  if (!Object.prototype.hasOwnProperty.call(dicts, next)) return;
  locale.set(next);
}

export function t(key) {
  const active = get(locale);
  const dict = dicts[active] || {};
  if (Object.prototype.hasOwnProperty.call(dict, key)) {
    return dict[key];
  }
  if (Object.prototype.hasOwnProperty.call(dicts.en, key)) {
    return dicts.en[key];
  }
  return key;
}
```

- [ ] **Step 5: Run vitest — must PASS**

```bash
cd apps/signup && npm run test
```

Expected: 5/5 PASS.

(No commit yet — bundles with api.js into commit 3.)

---

## Task 11: api.js — TDD with Vitest

**Files:**
- Create: `apps/signup/tests/api.test.js`
- Create: `apps/signup/src/lib/api.js`

The api wrapper is a thin `fetch` helper that returns `{ ok, data, error }` instead of throwing. The validate endpoint always returns 200 on the happy path; non-2xx responses (4xx Origin failures, 5xx server errors) and network failures collapse to a normalised error.

- [ ] **Step 1: Write the failing tests**

Write `apps/signup/tests/api.test.js`:

```javascript
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { post } from '$lib/api';

describe('api.post', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('returns ok=true with parsed JSON on a 2xx response', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        ok: true,
        status: 200,
        json: async () => ({ ok: true, bot_username: 'TestBot' }),
      })),
    );

    const result = await post('/api/signup/validate', { token: 'abc' });

    expect(result.ok).toBe(true);
    expect(result.data).toEqual({ ok: true, bot_username: 'TestBot' });
    expect(result.status).toBe(200);
  });

  it('returns ok=false with a normalised error on a 4xx response', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        ok: false,
        status: 403,
        json: async () => ({ detail: 'origin_not_allowed' }),
      })),
    );

    const result = await post('/api/signup/validate', { token: 'abc' });

    expect(result.ok).toBe(false);
    expect(result.status).toBe(403);
    expect(result.error).toBe('origin_not_allowed');
  });

  it('returns ok=false with a network error reason on fetch failure', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new TypeError('Failed to fetch');
      }),
    );

    const result = await post('/api/signup/validate', { token: 'abc' });

    expect(result.ok).toBe(false);
    expect(result.status).toBe(0);
    expect(result.error).toBe('network_error');
  });

  it('handles JSON parse failures on a 5xx response', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        ok: false,
        status: 503,
        json: async () => {
          throw new SyntaxError('Unexpected token');
        },
      })),
    );

    const result = await post('/api/signup/validate', { token: 'abc' });

    expect(result.ok).toBe(false);
    expect(result.status).toBe(503);
    expect(result.error).toBe('server_error');
  });
});
```

- [ ] **Step 2: Run vitest — must FAIL because api.js doesn't exist**

```bash
cd apps/signup && npm run test
```

Expected: 4 failures, all "Cannot resolve $lib/api".

- [ ] **Step 3: Implement api.js**

Write `apps/signup/src/lib/api.js`:

```javascript
/**
 * Thin fetch wrapper for the signup site. Returns
 *   { ok, data, error, status }
 * instead of throwing, so callers can handle every branch
 * with a single conditional.
 */
export async function post(path, body) {
  let response;
  try {
    response = await fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
  } catch (e) {
    return { ok: false, status: 0, error: 'network_error' };
  }

  if (response.ok) {
    try {
      const data = await response.json();
      return { ok: true, status: response.status, data };
    } catch (e) {
      return {
        ok: false,
        status: response.status,
        error: 'invalid_response',
      };
    }
  }

  let detail = 'server_error';
  try {
    const errBody = await response.json();
    if (errBody && typeof errBody.detail === 'string') {
      detail = errBody.detail;
    }
  } catch (e) {
    // leave detail as 'server_error'
  }
  return { ok: false, status: response.status, error: detail };
}
```

- [ ] **Step 4: Run vitest — must PASS for both test files**

```bash
cd apps/signup && npm run test
```

Expected: 9/9 PASS (5 i18n + 4 api).

---

## Task 12: Commit library modules

- [ ] **Step 1: Stage and commit**

```bash
git add apps/signup/src/lib/i18n.js apps/signup/src/lib/api.js \
        apps/signup/src/messages/en.json apps/signup/src/messages/da.json \
        apps/signup/tests/i18n.test.js apps/signup/tests/api.test.js
git commit -m "$(cat <<'EOF'
feat(signup): i18n + api library modules with Vitest

i18n: t(key) helper with EN-default + EN-fallback when DA dict
misses a key. setLocale ignores unknown codes.

api: post() returns { ok, status, data, error } instead of
throwing; network/parse failures collapse to a normalised
error reason.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 13: Static content — pricing, favicon, robots, message expansion

**Files:**
- Create: `apps/signup/src/lib/pricing.json`
- Create: `apps/signup/static/favicon.svg`
- Create: `apps/signup/static/robots.txt`
- Modify: `apps/signup/src/messages/en.json` (expand for all routes)

- [ ] **Step 1: Expand the EN message dictionary**

Replace `apps/signup/src/messages/en.json` with:

```json
{
  "nav.brand": "Digital Vagt",
  "nav.pricing": "Pricing",
  "nav.signin": "Sign in",
  "footer.copyright": "© 2026 Digital Vagt ApS",
  "footer.legal.privacy": "Privacy",
  "footer.legal.terms": "Terms",
  "footer.legal.dpa": "Data Processing Agreement",
  "home.h1": "Heimdall watches your digital front door.",
  "home.subtitle": "Continuous external attack-surface monitoring for Danish small businesses. Built by Digital Vagt.",
  "home.cta.primary": "See pricing",
  "home.cta.secondary": "Email us",
  "home.section.howitworks.title": "How it works",
  "home.section.howitworks.body": "We scan what's reachable on the public internet — your website, mail records, exposed files. When something changes that puts you at risk, you get a plain-language Telegram alert.",
  "home.section.whatwemonitor.title": "What we monitor",
  "home.section.whatwemonitor.body": "Web servers, TLS certificates, DNS, exposed admin panels, leaked storage buckets, and unpatched software versions known to attackers.",
  "home.section.pricing.title": "Pricing",
  "home.section.pricing.body": "Two plans. Both include monthly scans, plain-language alerts, and a 30-day Watchman trial.",
  "home.section.faq.title": "Questions",
  "home.section.faq.body": "Ask anything: hello@digitalvagt.dk.",
  "pricing.h1": "Pricing",
  "pricing.subtitle": "Two plans. No surprise charges.",
  "pricing.cta.email": "Email us to get started",
  "legal.privacy.h1": "Privacy",
  "legal.terms.h1": "Terms of Service",
  "legal.dpa.h1": "Data Processing Agreement",
  "legal.disclaimer": "This is a placeholder. Final terms pending review by Anders Wernblad, Aumento Law. Do not rely on this text.",
  "signup.start.checking": "Checking your link…",
  "signup.start.ok.title": "Almost there — open Telegram to finish.",
  "signup.start.ok.body": "Tap the button on your phone, or scan the code.",
  "signup.start.ok.cta": "Open Telegram",
  "signup.start.ok.qr.alt": "Open Telegram on your phone — scan this code",
  "signup.start.ok.fallback": "No Telegram? Reply to the email and Federico will help.",
  "signup.start.invalid.title": "We can't find that link.",
  "signup.start.invalid.body": "It may have been mistyped. Reply to the email you received and we'll send a fresh one.",
  "signup.start.used.title": "That link has already been used.",
  "signup.start.used.body": "If you didn't activate your trial, reply to the email and we'll help.",
  "signup.start.expired.title": "That link expired.",
  "signup.start.expired.body": "Magic links last 30 minutes. Reply to the email and we'll send a fresh one.",
  "signup.start.error.title": "Something went wrong.",
  "signup.start.error.body": "Try refreshing. If that doesn't work, reply to the email."
}
```

`da.json` stays `{}` until slice 3 — i18n.js falls back to EN.

- [ ] **Step 2: Create pricing.json**

Write `apps/signup/src/lib/pricing.json`:

```json
{
  "currency": "kr.",
  "currency_label": "DKK",
  "plans": [
    {
      "id": "watchman",
      "name": "Watchman",
      "price_monthly": 199,
      "tagline": "Free 30-day trial, then 199 kr./month.",
      "features": [
        "Layer 1 monthly scans",
        "Plain-language Telegram alerts",
        "Critical-severity alerts within 24 h",
        "Cancel anytime"
      ]
    },
    {
      "id": "sentinel",
      "name": "Sentinel",
      "price_monthly": 399,
      "tagline": "Active monitoring with consent-gated probing.",
      "features": [
        "Everything in Watchman",
        "Layer 2 active probes (with written consent)",
        "Same-day alerts for actively-exploited CVEs",
        "Quarterly Danish-language summary"
      ]
    }
  ]
}
```

- [ ] **Step 3: Create favicon.svg (placeholder shield)**

Write `apps/signup/static/favicon.svg`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" width="32" height="32" role="img" aria-label="Digital Vagt">
  <rect width="32" height="32" rx="6" fill="#0b1120"/>
  <path d="M16 5l9 3v8c0 6-4 10-9 12-5-2-9-6-9-12V8l9-3z" fill="none" stroke="#f59e0b" stroke-width="2" stroke-linejoin="round"/>
  <path d="M11 16l4 4 7-8" fill="none" stroke="#f59e0b" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
```

- [ ] **Step 4: Create robots.txt blocking everything (slice-1 dev-only)**

Write `apps/signup/static/robots.txt`:

```
User-agent: *
Disallow: /
```

Slice 2 will replace this with a public-allowing robots.txt at the same time as the Hetzner deploy.

(Static-content commit lands together with the layout + pages in Task 17.)

---

## Task 14: Layout + landing page

**Files:**
- Create: `apps/signup/src/routes/+layout.svelte`
- Create: `apps/signup/src/routes/+page.svelte`

- [ ] **Step 1: Create +layout.svelte (nav + footer chrome)**

Write `apps/signup/src/routes/+layout.svelte`:

```svelte
<script>
  import '../app.css';
  import { t } from '$lib/i18n';
</script>

<nav class="nav">
  <a class="brand" href="/">{t('nav.brand')}</a>
  <ul class="nav-links">
    <li><a href="/pricing">{t('nav.pricing')}</a></li>
  </ul>
</nav>

<main>
  <slot />
</main>

<footer class="footer">
  <p class="muted">{t('footer.copyright')}</p>
  <ul class="legal-links">
    <li><a href="/legal/privacy">{t('footer.legal.privacy')}</a></li>
    <li><a href="/legal/terms">{t('footer.legal.terms')}</a></li>
    <li><a href="/legal/dpa">{t('footer.legal.dpa')}</a></li>
  </ul>
</footer>

<style>
  .nav {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 1rem 1.5rem;
    border-bottom: 1px solid var(--border);
    max-width: 960px;
    margin: 0 auto;
  }
  .brand {
    font-weight: 700;
    color: var(--gold);
    font-size: 1.1rem;
  }
  .nav-links,
  .legal-links {
    display: flex;
    gap: 1.25rem;
    margin: 0;
    padding: 0;
    list-style: none;
  }
  .footer {
    max-width: 960px;
    margin: 4rem auto 2rem;
    padding: 1.5rem;
    border-top: 1px solid var(--border-subtle);
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    flex-wrap: wrap;
  }
</style>
```

- [ ] **Step 2: Create +page.svelte (landing /)**

Write `apps/signup/src/routes/+page.svelte`:

```svelte
<script>
  import { t } from '$lib/i18n';
</script>

<svelte:head>
  <title>{t('nav.brand')} — {t('home.h1')}</title>
</svelte:head>

<section class="hero container">
  <h1>{t('home.h1')}</h1>
  <p class="lede">{t('home.subtitle')}</p>
  <div class="cta-row">
    <a class="btn" href="/pricing">{t('home.cta.primary')}</a>
    <a class="btn btn-outline" href="mailto:hello@digitalvagt.dk">
      {t('home.cta.secondary')}
    </a>
  </div>
</section>

<section class="container sections">
  <article>
    <h2>{t('home.section.howitworks.title')}</h2>
    <p>{t('home.section.howitworks.body')}</p>
  </article>
  <article>
    <h2>{t('home.section.whatwemonitor.title')}</h2>
    <p>{t('home.section.whatwemonitor.body')}</p>
  </article>
  <article>
    <h2>{t('home.section.pricing.title')}</h2>
    <p>{t('home.section.pricing.body')}</p>
    <a class="btn btn-outline" href="/pricing">{t('home.cta.primary')}</a>
  </article>
  <article>
    <h2>{t('home.section.faq.title')}</h2>
    <p>{t('home.section.faq.body')}</p>
  </article>
</section>

<style>
  .hero {
    padding-top: 4rem;
    padding-bottom: 2rem;
  }
  .lede {
    font-size: 1.15rem;
    color: var(--text-dim);
    max-width: 60ch;
  }
  .cta-row {
    display: flex;
    gap: 0.75rem;
    margin-top: 1.5rem;
    flex-wrap: wrap;
  }
  .sections {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
    gap: 2rem;
    padding-bottom: 3rem;
  }
</style>
```

(No commit yet — bundles with the rest of pages in Task 17.)

---

## Task 15: Pricing page

**Files:**
- Create: `apps/signup/src/routes/pricing/+page.svelte`

- [ ] **Step 1: Create the pricing page**

Write `apps/signup/src/routes/pricing/+page.svelte`:

```svelte
<script>
  import { t } from '$lib/i18n';
  import pricing from '$lib/pricing.json';
</script>

<svelte:head>
  <title>{t('pricing.h1')} — {t('nav.brand')}</title>
</svelte:head>

<section class="container">
  <h1>{t('pricing.h1')}</h1>
  <p class="lede">{t('pricing.subtitle')}</p>

  <div class="cards">
    {#each pricing.plans as plan}
      <article class="card">
        <h2>{plan.name}</h2>
        <p class="price">
          <span class="amount">{plan.price_monthly}</span>
          <span class="unit">{pricing.currency} / month</span>
        </p>
        <p class="muted">{plan.tagline}</p>
        <ul class="features">
          {#each plan.features as feature}
            <li>{feature}</li>
          {/each}
        </ul>
        <a class="btn" href="mailto:hello@digitalvagt.dk?subject=Interested in {plan.name}">
          {t('pricing.cta.email')}
        </a>
      </article>
    {/each}
  </div>
</section>

<style>
  .cards {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    gap: 1.5rem;
    margin-top: 2rem;
    padding-bottom: 3rem;
  }
  .card {
    padding: 1.5rem;
    background: var(--bg-raised);
    border: 1px solid var(--border);
    border-radius: 8px;
  }
  .price {
    display: flex;
    align-items: baseline;
    gap: 0.5rem;
    margin: 0.5rem 0 1rem;
  }
  .amount {
    font-size: 2.25rem;
    font-weight: 700;
    color: var(--gold);
  }
  .unit {
    color: var(--text-dim);
  }
  .features {
    list-style: none;
    padding: 0;
    margin: 0 0 1.5rem;
  }
  .features li {
    padding: 0.4rem 0;
    border-top: 1px solid var(--border-subtle);
  }
  .features li:first-child {
    border-top: 0;
  }
</style>
```

(No commit yet.)

---

## Task 16: Three legal stub pages

**Files:**
- Create: `apps/signup/src/routes/legal/privacy/+page.svelte`
- Create: `apps/signup/src/routes/legal/terms/+page.svelte`
- Create: `apps/signup/src/routes/legal/dpa/+page.svelte`

The three stubs share an identical skeleton. Each has a unique heading-key and a shared disclaimer.

- [ ] **Step 1: Create privacy stub**

Write `apps/signup/src/routes/legal/privacy/+page.svelte`:

```svelte
<script>
  import { t } from '$lib/i18n';
</script>

<svelte:head>
  <title>{t('legal.privacy.h1')} — {t('nav.brand')}</title>
</svelte:head>

<section class="container">
  <h1>{t('legal.privacy.h1')}</h1>
  <div class="disclaimer">
    <strong>{t('legal.disclaimer')}</strong>
  </div>
</section>
```

- [ ] **Step 2: Create terms stub**

Write `apps/signup/src/routes/legal/terms/+page.svelte`:

```svelte
<script>
  import { t } from '$lib/i18n';
</script>

<svelte:head>
  <title>{t('legal.terms.h1')} — {t('nav.brand')}</title>
</svelte:head>

<section class="container">
  <h1>{t('legal.terms.h1')}</h1>
  <div class="disclaimer">
    <strong>{t('legal.disclaimer')}</strong>
  </div>
</section>
```

- [ ] **Step 3: Create dpa stub**

Write `apps/signup/src/routes/legal/dpa/+page.svelte`:

```svelte
<script>
  import { t } from '$lib/i18n';
</script>

<svelte:head>
  <title>{t('legal.dpa.h1')} — {t('nav.brand')}</title>
</svelte:head>

<section class="container">
  <h1>{t('legal.dpa.h1')}</h1>
  <div class="disclaimer">
    <strong>{t('legal.disclaimer')}</strong>
  </div>
</section>
```

(No commit yet.)

---

## Task 17: Commit pages + static content

- [ ] **Step 1: Verify build still parses**

```bash
cd apps/signup && npm run build
```

Expected: `build/` directory created, no errors. The `/signup/start` route may warn about prerender + dynamic search; that's expected and handled by `fallback: '404.html'` in svelte.config.js.

- [ ] **Step 2: Stage and commit**

```bash
git add apps/signup/static/ apps/signup/src/lib/pricing.json \
        apps/signup/src/messages/en.json \
        apps/signup/src/routes/+layout.svelte apps/signup/src/routes/+page.svelte \
        apps/signup/src/routes/pricing/ apps/signup/src/routes/legal/
git commit -m "$(cat <<'EOF'
feat(signup): layout, landing, pricing, legal stubs

Adds the layout chrome (nav + footer), landing page with 4 stub
sections, pricing page reading lib/pricing.json, and three legal
stubs each carrying the Aumento Law placeholder disclaimer.

Self-hosted favicon, robots.txt blocks indexing (slice 1 = dev-only).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 18: Magic-link landing page (`/signup/start`)

**Files:**
- Create: `apps/signup/src/routes/signup/start/+page.svelte`
- Create: `apps/signup/src/routes/signup/start/+page.js` (disable prerender for the dynamic-token route)

This is the slice's most complex page. Lifecycle:

1. On mount: read `?t=<token>` from `$page.url.searchParams`.
2. Call `api.post('/api/signup/validate', { token })`.
3. Render one of three states based on response.
4. On success: also generate a QR code client-side via `qrcode.toDataURL` for the Telegram deep link.
5. Replace the URL via `history.replaceState({}, '', '/signup/start')` so the token isn't visible in the address bar after the call.

- [ ] **Step 1: Create the prerender opt-out file**

Write `apps/signup/src/routes/signup/start/+page.js`:

```javascript
// The /signup/start page reads ?t=<token> at runtime; prerendering it
// would bake an empty-token state into the static bundle. Disable
// prerender — adapter-static still serves the route from the SPA
// fallback at build/404.html.
export const prerender = false;
export const ssr = false;
```

- [ ] **Step 2: Create the page**

Write `apps/signup/src/routes/signup/start/+page.svelte`:

```svelte
<script>
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import QRCode from 'qrcode';
  import { post } from '$lib/api';
  import { t } from '$lib/i18n';

  let state = $state('checking'); // 'checking' | 'ok' | 'invalid' | 'used' | 'expired' | 'error'
  let botUsername = $state('');
  let token = $state('');
  let qrDataUrl = $state('');

  onMount(async () => {
    const url = new URL(window.location.href);
    token = url.searchParams.get('t') || '';

    if (!token) {
      state = 'invalid';
      replaceUrlWithoutToken();
      return;
    }

    const result = await post('/api/signup/validate', { token });

    if (!result.ok) {
      // network or 4xx/5xx — show generic error, don't leak which
      state = 'error';
      replaceUrlWithoutToken();
      return;
    }

    const data = result.data;
    if (data.ok === true) {
      botUsername = data.bot_username;
      state = 'ok';
      try {
        qrDataUrl = await QRCode.toDataURL(telegramDeepLink(), {
          width: 240,
          margin: 1,
          color: { dark: '#0b1120', light: '#f8fafc' },
        });
      } catch (e) {
        // QR is a nice-to-have — fall back silently
        qrDataUrl = '';
      }
    } else if (data.reason === 'used') {
      state = 'used';
    } else if (data.reason === 'expired') {
      state = 'expired';
    } else {
      state = 'invalid';
    }

    replaceUrlWithoutToken();
  });

  function replaceUrlWithoutToken() {
    try {
      history.replaceState({}, '', '/signup/start');
    } catch (e) {
      // ignore
    }
  }

  function telegramDeepLink() {
    return `https://t.me/${encodeURIComponent(botUsername)}?start=${encodeURIComponent(token)}`;
  }
</script>

<svelte:head>
  <title>{t('signup.start.ok.title')} — {t('nav.brand')}</title>
</svelte:head>

<section class="container start-page">
  {#if state === 'checking'}
    <p class="muted">{t('signup.start.checking')}</p>
  {:else if state === 'ok'}
    <h1>{t('signup.start.ok.title')}</h1>
    <p>{t('signup.start.ok.body')}</p>
    <a class="btn" href={telegramDeepLink()} rel="noopener noreferrer">
      {t('signup.start.ok.cta')}
    </a>
    {#if qrDataUrl}
      <div class="qr">
        <img src={qrDataUrl} alt={t('signup.start.ok.qr.alt')} width="240" height="240" />
      </div>
    {/if}
    <p class="muted fallback">{t('signup.start.ok.fallback')}</p>
  {:else if state === 'used'}
    <h1>{t('signup.start.used.title')}</h1>
    <p>{t('signup.start.used.body')}</p>
    <a class="btn btn-outline" href="mailto:hello@digitalvagt.dk">
      {t('home.cta.secondary')}
    </a>
  {:else if state === 'expired'}
    <h1>{t('signup.start.expired.title')}</h1>
    <p>{t('signup.start.expired.body')}</p>
    <a class="btn btn-outline" href="mailto:hello@digitalvagt.dk">
      {t('home.cta.secondary')}
    </a>
  {:else if state === 'invalid'}
    <h1>{t('signup.start.invalid.title')}</h1>
    <p>{t('signup.start.invalid.body')}</p>
    <a class="btn btn-outline" href="mailto:hello@digitalvagt.dk">
      {t('home.cta.secondary')}
    </a>
  {:else}
    <h1>{t('signup.start.error.title')}</h1>
    <p>{t('signup.start.error.body')}</p>
    <a class="btn btn-outline" href="mailto:hello@digitalvagt.dk">
      {t('home.cta.secondary')}
    </a>
  {/if}
</section>

<style>
  .start-page {
    padding-top: 4rem;
    padding-bottom: 4rem;
    text-align: center;
  }
  .start-page p {
    margin-left: auto;
    margin-right: auto;
  }
  .qr {
    margin: 1.5rem auto 0;
    display: inline-block;
    padding: 0.5rem;
    background: var(--bg-raised);
    border: 1px solid var(--border);
    border-radius: 8px;
  }
  .fallback {
    margin-top: 2rem;
  }
</style>
```

Notes on the implementation:
- Uses Svelte 5 runes (`$state`) — the operator console at `src/api/frontend/` is on Svelte 5 already, so the version is consistent.
- `encodeURIComponent` on both bot username and token: defense-in-depth, even though `secrets.token_urlsafe` produces URL-safe characters.
- QR colours: dark token on light token background, hard-coded to `#0b1120` (--bg-base) / `#f8fafc` (light-theme bg) so the QR remains scannable in both themes — phone cameras don't read CSS variables.
- `state` ordering matches the validate-endpoint reason values: invalid/used/expired plus a generic error catch-all for network failures.

- [ ] **Step 3: Build to verify the dynamic route compiles**

```bash
cd apps/signup && npm run build
```

Expected: build succeeds. May log: `404.html written as fallback`.

- [ ] **Step 4: Codex review of the magic-link page**

`precommit_codex_review_guard.py` only fires on `src/**/*.py` and `tests/**/*.py` diffs, so this commit is *not* hook-gated. The magic-link page contains the slice's most non-trivial logic (state machine, QR generation, history mutation, deep-link construction). Run Codex anyway:

```bash
node ~/.claude/plugins/cache/openai-codex/codex/1.0.4/scripts/codex-companion.mjs review "apps/signup/src/routes/signup/start/+page.svelte apps/signup/src/routes/signup/start/+page.js"
```

Read the output. Address any must-fix items in-place. Re-run Codex until clean.

- [ ] **Step 5: Commit the magic-link page**

```bash
git add apps/signup/src/routes/signup/
git commit -m "$(cat <<'EOF'
feat(signup): /signup/start magic-link landing

Calls POST /api/signup/validate (read-only), renders one of five
states: checking, ok (with QR + Telegram CTA), used, expired,
invalid (also covers network errors generically).

The token is stripped from the URL via history.replaceState after
the validate call to avoid persisting it in browser history.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 19: Makefile targets

**Files:**
- Modify: `Makefile` (append three targets at the end of the test section, before `compose-lint`)

Touching `Makefile` triggers the `infra_danger_zone.py` hook (context-injection, non-blocking). Expected.

- [ ] **Step 1: Add the three targets**

Edit `Makefile`. After the `dev-ops-smoke:` block (around line 209), and before the `# --- Compose lint / diff ---` comment block (around line 211), insert:

```make
# --- Signup site (apps/signup/) -----------------------------------------

.PHONY: signup-dev
signup-dev: ## Run the SvelteKit signup site dev server (host :5173, /api → :8001).
	cd apps/signup && npm install --prefer-offline && npm run dev

.PHONY: signup-build
signup-build: ## Build the SvelteKit signup site to apps/signup/build/.
	cd apps/signup && npm install --prefer-offline && npm run build

.PHONY: signup-test
signup-test: ## Run the signup-site Vitest suite.
	cd apps/signup && npm install --prefer-offline && npm run test

```

- [ ] **Step 2: Verify the targets parse**

Run: `make help | grep signup`
Expected: three lines (`signup-dev`, `signup-build`, `signup-test`) with their descriptions.

- [ ] **Step 3: Commit the Makefile change**

```bash
git add Makefile
git commit -m "$(cat <<'EOF'
chore(make): signup-{dev,build,test} targets for apps/signup/

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 20: Browser verification

This is the slice-1 acceptance gate. Per `feedback_test_frontend_in_browser.md`: verify in a real browser before reporting complete. No new files.

- [ ] **Step 1: Bring up the dev backend stack**

```bash
make dev-up
```

Expected: containers up, healthchecks pass.

- [ ] **Step 2: Issue a known-good test token from the dev DB**

```bash
docker exec heimdall_dev-api-1 python -c "
import sqlite3
from src.db.signup import create_signup_token
conn = sqlite3.connect('/data/clients/clients.db')
conn.row_factory = sqlite3.Row
result = create_signup_token(conn, cvr='12345678', email='browser-test@example.dk')
print('VALID_TOKEN=' + result['token'])
conn.close()
"
```

Capture the printed `VALID_TOKEN=...` value. Use it in Step 6.

If the seed CVR `12345678` doesn't exist in the dev DB, run `make dev-seed` first (it loads `config/dev_dataset.json` into `data/dev/clients.db`, then re-issue from the seeded DB; you may need to insert the CVR into `clients` first if seeded data uses different CVRs — check the dev fixture).

- [ ] **Step 3: Start the SvelteKit dev server**

In a second terminal:

```bash
make signup-dev
```

Expected: Vite logs `Local: http://127.0.0.1:5173/`.

- [ ] **Step 4: Walk all six routes**

In a browser, visit each in order. For each, check that the page renders, no console errors, no network calls to non-localhost domains:

1. `http://127.0.0.1:5173/` — landing
2. `http://127.0.0.1:5173/pricing` — two cards visible, prices in kr.
3. `http://127.0.0.1:5173/legal/privacy` — disclaimer visible
4. `http://127.0.0.1:5173/legal/terms` — disclaimer visible
5. `http://127.0.0.1:5173/legal/dpa` — disclaimer visible
6. `http://127.0.0.1:5173/signup/start?t=invalid_xxx` — "We can't find that link"
7. `http://127.0.0.1:5173/signup/start?t=<VALID_TOKEN>` — Telegram CTA + QR code visible
8. After Step 7, refresh the page (URL is now `/signup/start` with no `?t=`) — it should show the invalid state because `?t=` is missing
9. Re-paste the URL with `?t=<VALID_TOKEN>` again — still shows ok (token unconsumed)

- [ ] **Step 5: Verify the no-mutation contract from the browser session**

In a third terminal:

```bash
docker exec heimdall_dev-api-1 python -c "
import sqlite3
conn = sqlite3.connect('/data/clients/clients.db')
conn.row_factory = sqlite3.Row
row = conn.execute('SELECT consumed_at, email FROM signup_tokens WHERE token = ?', ('<VALID_TOKEN>',)).fetchone()
print(dict(row))
conn.close()
"
```

Expected: `consumed_at` is `None`, `email` is `'browser-test@example.dk'` (not nulled — only `activate_watchman_trial` nulls it).

- [ ] **Step 6: DevTools spot-checks**

In Chrome/Firefox DevTools:
- Network tab: filter for `domain != localhost`. Result must be empty for the entire session.
- Console tab: no errors, no warnings.
- Application → Local Storage: only `heimdall.theme` should be present (and only if user toggled — slice 1 has no UI toggle, so likely empty).
- Accessibility (Tab key): from the landing page, press Tab repeatedly and verify a visible focus ring appears on every interactive element (nav links, hero CTAs, footer legal links). Repeat on `/signup/start?t=<valid>` — focus rings must appear on the Telegram CTA, the QR fallback link if rendered, and the mailto fallback.

- [ ] **Step 7: Theme-switch smoke test**

In DevTools console:

```javascript
localStorage.setItem('heimdall.theme', 'light');
location.reload();
```

Expected: page reloads with light tokens, no flash of dark colours during reload (FOUC check — the inline bootstrap in app.html runs before the bundle).

Toggle back:

```javascript
localStorage.setItem('heimdall.theme', 'dark');
location.reload();
```

- [ ] **Step 8: Production-build smoke**

Stop the dev server. From project root:

```bash
make signup-build
```

Expected: `apps/signup/build/` populated. Spot-check `apps/signup/build/index.html` exists and contains the expected meta description.

- [ ] **Step 9: Verification log entry**

Append to `docs/decisions/log.md` a single dated entry summarising the verification result. Example:

```markdown
### 2026-04-25 — SvelteKit signup site slice 1 verified

Six routes render in dev, /signup/start magic-link flow exercises the
read-only validate contract end-to-end (token state unchanged after
the browser session). Theme bootstrap shows no FOUC. Production
build emits to apps/signup/build/.

Slice 2 follow-up (tracked in cloud-hosting plan + spec): Hetzner
provisioning, Caddy + TLS, robots.txt for public crawl, signup-site
/health responder, rate limiter on POST /signup/validate, Postmark
Message-0 sender.
```

- [ ] **Step 10: Final commit (if anything was edited during verification)**

If the verification surfaced a fix:

```bash
git add <fix-files> docs/decisions/log.md
git commit -m "docs(decisions): slice-1 signup site verification entry"
```

If nothing needed fixing, only the decision-log entry needs committing:

```bash
git add docs/decisions/log.md
git commit -m "docs(decisions): slice-1 signup site verification entry"
```

---

## Verification checklist (slice-1 acceptance — must all pass)

1. `python -m pytest tests/test_api_signup_validate.py tests/test_signup_round_trip.py -v --no-cov` — green.
2. `python -m pytest -m "not integration" --no-cov` — full suite green (no regressions).
3. `make signup-test` — Vitest 9/9 green.
4. `make signup-build` — `apps/signup/build/` populated.
5. `make signup-dev` opens at `http://127.0.0.1:5173/`, all 6 routes render.
6. `/signup/start?t=<valid>` shows Telegram deep-link + QR with the correct payload `https://t.me/<bot>?start=<token>`.
7. `/signup/start?t=invalid` shows the invalid-state UI.
8. After validate succeeds, the DB row is unchanged (`consumed_at IS NULL`, `email` not nulled).
9. DevTools Network tab during a full session shows zero requests to external domains.
10. DevTools Console: zero errors, zero warnings.
11. `localStorage.setItem('heimdall.theme', 'light')` → reload → no FOUC.
12. `make compose-lint` green.
13. Backend commit message contained `HEIMDALL_CODEX_REVIEWED=1` after a real Codex pass.

---

## Out-of-scope (do not pull in)

- Hetzner provisioning, Caddyfile, Simply DNS, TLS — slice 2 (per `docs/plans/cloud-hosting-plan.md`).
- Postmark account + Message 0 sender — slice 2 or 3.
- Full Danish translations — slice 3 (after EN copy is approved by Federico).
- Rate limiter on `/signup/validate` (`slowapi` dep) — slice 2 alongside public exposure.
- Operator console "issue magic link" UI — slice 3.
- MitID OIDC, Betalingsservice, scope picker, PDF generation — separate Sentinel-onboarding slice.
- Cookie banner — never, unless tracking is introduced (none in slice 1).
- Theme toggle UI on signup — never (signup users don't need it).
- Playwright E2E — slice 2 (paired with Hetzner deploy).

---

## Open items carried into implementation

1. **Ports 5173 collision**: if the operator already runs another Vite instance on `:5173`, `make signup-dev` will fail to bind. Workaround: `cd apps/signup && npm run dev -- --port 5174` and update the `SIGNUP_ALLOWED_ORIGINS` env on the dev backend accordingly.
2. **Dev DB CVR mismatch**: Task 20 Step 2 assumes CVR `12345678` exists in the dev `clients.db`. If `make dev-seed` populates with different CVRs (check `config/dev_dataset.json`), insert the CVR via SQL before issuing a token, or use the first seeded CVR.
3. **`apps/` top-level directory**: this is the first occupant. If a future second app (e.g. `apps/operator/` if operator console moves out of `src/api/frontend/`) is planned, the current scaffold establishes the convention: each app self-contained, independent `package.json`, independent `node_modules`. No shared library at slice 1.
4. **Two SvelteKit homes** (`apps/signup/` vs `src/api/frontend/`): the long-term convention has not been decided. Slice 1 doesn't force a resolution, but a future ADR should pick one — either the operator console relocates to `apps/operator/`, or the signup site moves under `src/`. Surfacing here so the next architect-touching change addresses it deliberately rather than by accretion.
5. **Slice-3 i18n lang-attribute flip**: `apps/signup/src/app.html` hard-codes `<html lang="en">`. Slice 3's runtime locale flip needs either a SvelteKit `handle` hook (SSR) or a build-time multi-locale prerender. With `adapter-static` + `prerender = false; ssr = false` on `/signup/start`, neither is free — surface to Federico in slice-3 brainstorming so the cost is visible.
6. **`+page.js` prerender opt-out**: the current implementation disables prerender on the dynamic-token route. If slice 2 adds a `/health` Caddy responder + a SvelteKit catch-all 404, validate that the SPA fallback at `build/404.html` still resolves the dynamic search params correctly under Caddy's `try_files` behaviour.
7. **Vite proxy `Origin` header preservation**: see the failure-mode note in Task 7 Step 3. The slice-1 acceptance test (Task 20 Step 4) is the canary; if 403 surfaces with a valid Origin in DevTools, switch to `xfwd: true` and re-verify.
