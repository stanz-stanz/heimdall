# SvelteKit Signup Site — Slice 1 Design

**Date:** 2026-04-25
**Branch:** `feat/sentinel-onboarding`
**Status:** ready for writing-plans
**Owners:** architect (project structure + endpoint shape), python-expert (FastAPI handler), frontend work has no dedicated agent (no WebSockets ⇒ not fullstack-guy)
**Related decisions:** D17 SvelteKit, D19 Hetzner FSN, D15 magic-link signup; cloud-hosting plan D4/S1 (`adapter-static` + MitID redirect_uri → backend FastAPI), D10 (Postmark EU), D9 (Hetzner :443 webhooks); plus 14 sub-decisions answered in the 2026-04-25 brainstorming session.

---

## Context

Heimdall has a complete backend pipeline (scan → consent → interpret → compose → deliver) and a backend data layer for Sentinel onboarding (signup tokens, subscriptions, retention, conversion events). It does not yet have a public website. The next critical-path slice is the SvelteKit signup site, which lands the Watchman-enrollment vertical (magic-link landing page) and the public marketing surface (landing, pricing, legal stubs).

**Locked context** from prior sessions:
- D17 (2026-04-23): SvelteKit chosen for the public site.
- D19 (2026-04-23): Hetzner Cloud, Falkenstein.
- 2026-04-25 cloud-hosting plan: `adapter-static` + Caddy serves bundle directly; MitID OIDC redirect_uri lands on backend FastAPI; Postmark EU API for transactional email; Caddy reverse-proxies `signup.digitalvagt.dk/api/*` to backend over Tailscale.
- Backend already shipped: `src/db/signup.py` (token issue + consume), `/start <token>` Telegram handler. The magic-link consumer has a server but no UI.

---

## Scope

**This slice ships:**
- Standalone SvelteKit project at `apps/signup/`, `adapter-static`.
- Design tokens copied once from `src/api/frontend/src/styles/tokens.css`.
- 6 routes: `/`, `/pricing`, `/signup/start`, `/legal/{privacy,terms,dpa}` + SvelteKit defaults (404, 500).
- Magic-link landing end-to-end (validate-only): SvelteKit page calls a read-only backend endpoint, renders Telegram deep-link + QR code on success, error UI on failure. Token consumption happens later in the existing Telegram `/start` handler — not here.
- New FastAPI endpoint `POST /signup/validate` wrapping `src/db/signup.get_signup_token()` (read-only).
- i18n machinery: simple JSON dict + `t()` helper, EN as source of truth, DA placeholder file.
- Light/dark theme support via the same no-FOUC bootstrap pattern as the operator console.
- Vitest unit tests (i18n + api wrapper), pytest tests for the new endpoint.
- Three Makefile targets: `signup-dev`, `signup-build`, `signup-test`.

**Explicitly deferred to later slices:**
- Hetzner box provisioning, Caddyfile, Simply DNS records, TLS, Tailscale wiring → slice 2.
- Postmark integration + Message 0 send → slice 2 or 3 (needs Postmark account + `mail.digitalvagt.dk` DNS).
- Danish translations of all stub copy → slice 3 (after EN copy is approved).
- Operator console "issue magic link" UI → slice 3 (separate backend endpoint to *issue* tokens; verify exists).
- MitID Erhverv OIDC flow, scope picker, PDF generation, Betalingsservice mandate → separate Sentinel-onboarding slice (broker selection still pending).
- Final marketing copy → follow-up slice (Federico writes; this slice ships stubs).

---

## Architecture

`apps/signup/` is a standalone SvelteKit project, independent of `src/api/frontend/` (the operator console). Vite dev server runs on host `:5173` with a proxy `/api/*` → `http://localhost:8001` (the FastAPI dev container, exposed on host via `make dev-up`). Production build (slice 2) emits to `apps/signup/build/`, which Caddy on the signup box serves directly. No Node runtime in production.

The bundle uses **relative** `/api/*` fetches so the same code works in dev (Vite proxy) and prod (Caddy reverse-proxy to backend Tailscale IP). No `PUBLIC_API_BASE` env-baking.

Both the Vite dev proxy and the prod Caddy reverse-proxy **strip the leading `/api` path segment** before forwarding. The backend FastAPI router prefix is therefore `/signup` (no `/api`), which aligns with the existing `/console` and `/health` convention. The `/api/*` namespace exists only on the bundle side as a stable proxy hook.

```
                                Public internet
                                       │
                                       ▼
                              signup.digitalvagt.dk:443
                          ┌────────────────────────┐
                          │ Caddy (signup box)     │
                          │ • serves /build/*      │
                          │ • proxies /api/*       │──── Tailscale ───►  Backend FastAPI
                          └────────────────────────┘                     /signup/validate
                                                                         (calls src/db/signup.get_signup_token — READ-ONLY)
                                                                         /start <token> in Telegram → activate_watchman_trial
```

Slice 1 stops at the dashed line above — only the SvelteKit + backend endpoint pair lands. Caddy + Hetzner are slice 2.

---

## File layout

```
apps/signup/
  package.json
  svelte.config.js              # adapter-static
  vite.config.js                # /api/* dev-proxy → localhost:8001
  src/
    app.html                    # no-FOUC theme bootstrap (mirrors src/api/frontend/index.html)
    routes/
      +layout.svelte            # nav, footer
      +page.svelte              # /
      pricing/+page.svelte      # /pricing (reads lib/pricing.json)
      signup/start/+page.svelte      # /signup/start — magic-link landing (validate-only)
      legal/
        privacy/+page.svelte    # /legal/privacy (Aumento Law disclaimer)
        terms/+page.svelte      # /legal/terms (Aumento Law disclaimer)
        dpa/+page.svelte        # /legal/dpa (Aumento Law disclaimer)
    lib/
      i18n.js                   # t(key) helper, locale store, EN-default
      api.js                    # fetch wrapper, error normalization
      theme.js                  # data-theme bootstrap mirror of console
      pricing.json              # source-of-truth pricing data (mirrors docs/briefing.md)
    styles/
      tokens.css                # copied from src/api/frontend/src/styles/tokens.css
      app.css                   # base typography, layout primitives
    messages/
      en.json                   # source of truth
      da.json                   # {} until slice 3
  static/
    favicon.svg                 # self-hosted (no CDN — see "Security")
    robots.txt                  # User-agent: * / Disallow: / (slice 1 = dev-only)
  tests/
    i18n.test.js
    api.test.js
```

---

## Routes

| Path | Purpose | Slice 1 content |
|------|---------|-----------------|
| `/` | Landing page | H1 + 4 section stubs ("How it works", "What we monitor", "Pricing", "FAQ"); CTA button → `mailto:` until email-issue flow lands |
| `/pricing` | Pricing | Single Sentinel card reading from `lib/pricing.json`; the 30-day Watchman trial is listed as a feature, not a peer tier (per project_tier_restructure memory). CTA → `mailto:` |
| `/signup/start?t=<token>` | Magic-link landing (validate-only) | **Functional.** See "Magic-link flow" below. Page name mirrors Telegram `/start`. |
| `/legal/privacy` | Privacy stub | H1 + disclaimer block: *"This is a placeholder. Final terms pending review by Anders Wernblad, Aumento Law. Do not rely on this text."* |
| `/legal/terms` | Terms stub | Same disclaimer pattern |
| `/legal/dpa` | DPA stub | Same disclaimer pattern |
| `/404`, `/500` | SvelteKit defaults | Themed via `app.css` |

---

## Magic-link flow — token consumption ownership

**Critical constraint (Codex finding 1):** The existing Telegram `/start <token>` handler already consumes the token atomically via `activate_watchman_trial(conn, token, telegram_chat_id)` in `src/db/onboarding.py`. That function is the **sole** state-mutation point in the production Watchman-activation flow: token consumption + client upsert + `conversion_events` row + email-nulling all happen in one `BEGIN IMMEDIATE` transaction. If the SvelteKit landing also consumed the token, the subsequent Telegram `/start` would fail with `InvalidSignupToken` and the user would see a broken activation.

The SvelteKit landing is therefore **validate-only** — it inspects the token's state without mutating it.

### End-to-end flow

1. User clicks the link in Message 0 email: `https://signup.digitalvagt.dk/signup/start?t=<32-char-urlsafe-token>`.
2. SvelteKit page `signup/start/+page.svelte` reads `?t=<token>` from `$page.url.searchParams`.
3. Page calls `POST /api/signup/validate` with `{"token": "<token>"}` (Vite proxy strips `/api` → backend `POST /signup/validate` in dev; Caddy proxy strips `/api` in prod).
4. Backend handler (read-only, no DB writes):
   - Validates `Origin` header (rejects requests not from `https://signup.digitalvagt.dk` in prod, `http://localhost:5173` in dev — allowlist from `SIGNUP_ALLOWED_ORIGINS` env var).
   - Calls `src.db.signup.get_signup_token(conn, token)` — returns the row dict or `None`.
   - Computes status:
     - `None` → `{"ok": false, "reason": "invalid"}`
     - row with `consumed_at IS NOT NULL` → `{"ok": false, "reason": "used"}`
     - row with `expires_at <= now()` → `{"ok": false, "reason": "expired"}`
     - otherwise → `{"ok": true, "bot_username": "<TELEGRAM_BOT_USERNAME env>"}`
   - All responses are HTTP 200 (UX-driven payload, not REST-purist). HTTP 4xx is reserved for Origin/rate-limit failures.
5. **On success**, page renders:
   - Heading: *"Almost there — open Telegram to finish."*
   - Primary CTA: `<a href="https://t.me/<bot_username>?start=<token>">Open Telegram</a>` styled as a button. The token in the deep-link is what Telegram passes to the `/start` handler, which calls `activate_watchman_trial` and binds the `chat_id`.
   - QR code below the button: `<img alt="Open Telegram on your phone — scan this code" src="<data-url>">`. QR generated client-side by the `qrcode` npm package (~5 KB).
   - Fallback text: *"No Telegram? Reply to the email and Federico will help."*
   - Calls `history.replaceState({}, '', '/signup/start')` to strip the token from the visible URL.
6. **On failure**, page renders reason-specific copy + the same fallback CTA. The token is replaceState-stripped on failure too.

### Why this design closes the Codex token-race finding

- The validate endpoint is **read-only** — concurrent calls from two browsers or a refresh loop cannot leave the DB in an inconsistent state.
- The atomic write happens **once**, in `activate_watchman_trial`, which uses `BEGIN IMMEDIATE` + a conditional `UPDATE` on `signup_tokens.consumed_at` to enforce single-use. The `cursor.rowcount == 0` branch raises `InvalidSignupToken` and rolls back.
- If a user clicks the magic link twice (browser back-forward, accidental refresh) the validate endpoint returns `ok=true` both times until Telegram `/start` runs, after which validate returns `reason=used`. The flow is idempotent at the SvelteKit layer.

### Bot username delivery

`TELEGRAM_BOT_USERNAME` env var on the backend container. Dev value: `HeimdallSecurityDEVbot`. Prod value: TBD post-Digital-Vagt-naming. Backend reads it at handler invocation; bundle stays generic. **Open item:** verify the env-var convention against `src/core/config.py` patterns before commit (next section).

---

## Backend additions

New file: `src/api/signup.py` (separate module — keeps `src/api/console.py` focused on operator endpoints; matches the `prefix="/console"` / `prefix="/signup"` separation by audience).

### Router pattern (mirrors `src/api/console.py`)

```python
# Verified shape — aligned with src/api/console.py:23 and src/db/signup.py
from __future__ import annotations

import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

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
        "http://localhost:5173",
    )
    return {o.strip() for o in raw.split(",") if o.strip()}


def _open_clients_db(request: Request) -> sqlite3.Connection:
    """Resolve the clients.db connection from app state.

    Mirrors the existing pattern: src/api/app.py:405 wires
    `app.state.db_path` at startup; handlers open per-request
    connections so each handler sees a clean transactional view.
    """
    db_path = getattr(request.app.state, "db_path", None)
    if not db_path:
        raise HTTPException(503, "clients_db_unavailable")
    conn = sqlite3.connect(db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


@router.post("/validate")
async def validate(request: Request, body: ValidateBody):
    """Read-only check on a magic-link token. Never mutates state.

    Returns 200 with a payload that the SvelteKit landing reads to
    decide which UI to render. Token consumption happens later in
    `src/db/onboarding.py:activate_watchman_trial` via the Telegram
    `/start <token>` handler.
    """
    if request.headers.get("origin") not in _allowed_origins():
        raise HTTPException(403, "origin_not_allowed")

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

    return {
        "ok": True,
        "bot_username": os.environ["TELEGRAM_BOT_USERNAME"],
    }
```

### Wiring

`src/api/app.py` adds `app.include_router(signup.router)` next to the existing `app.include_router(console.router)`. The router mounts under `/signup/*` (no `/api` prefix — matches existing FastAPI convention from `/console/*`, `/health`).

### Rate limiting

Slice 1 ships **without** a rate limiter. Reasons: (a) `slowapi` is not currently in `requirements.txt` (verified via grep); adding it is a separate dep decision; (b) the validate endpoint is read-only and idempotent — abuse impact is bounded to DB reads, not state writes. **Slice 2 must add a rate limiter** before the signup site goes public on Hetzner. Tracked in "Open items" + slice-2 scope. The Origin allowlist is the slice-1 abuse control.

### Pytest coverage

`tests/test_api_signup_validate.py` covers:
- valid unconsumed token → 200 + `{ok: true, bot_username}`
- nonexistent token → 200 + `{ok: false, reason: "invalid"}`
- consumed token (call `consume_signup_token` first to mutate, then validate) → 200 + `{ok: false, reason: "used"}`
- expired token (insert with `expires_at` in the past) → 200 + `{ok: false, reason: "expired"}`
- bad Origin header → 403
- two concurrent validate calls on the same valid token both succeed AND the DB token state is unchanged after both (no consumption)
- token state asserted unchanged via `PRAGMA table_info(signup_tokens)` row count + `consumed_at IS NULL` check

### End-to-end activation round-trip (per Codex finding 6)

`tests/test_signup_round_trip.py` (new): exercises the full state transition, asserting validate-then-Telegram is the only path that mutates:

1. Create a fresh signup token via `create_signup_token`.
2. Call `POST /signup/validate` → assert `ok=true`. Re-query `signup_tokens` → assert `consumed_at IS NULL` (still unconsumed).
3. Call `activate_watchman_trial(conn, token, "tg_chat_id_123")` directly (simulates Telegram `/start`).
4. Assert: `clients` row has `status='watchman_active'`, `plan='watchman'`, `telegram_chat_id='tg_chat_id_123'`; `signup_tokens.consumed_at IS NOT NULL` and `email IS NULL`; `conversion_events` has one `signup` row for the CVR.
5. Call `POST /signup/validate` again → assert `ok=false, reason="used"`.
6. Race case: spawn two threads that simultaneously call `activate_watchman_trial`; assert exactly one succeeds and one raises `InvalidSignupToken`.

---

## Tokens, theme, i18n

**Tokens.** Copy `src/api/frontend/src/styles/tokens.css` to `apps/signup/src/styles/tokens.css` once, including both `:root[data-theme="dark"]` and `:root[data-theme="light"]` blocks. The signup site uses a strict subset (no severity colors, no operator-spacing tokens) — copying the whole file is fine; unused tokens add ~2KB to the gzipped bundle, acceptable.

**Theme.** `app.html` carries an inline `<script>` that sets `data-theme` on `<html>` before the SvelteKit bundle mounts (no FOUC). Resolution order: `localStorage["heimdall.theme"]` → `prefers-color-scheme` → `dark` (default). No theme toggle UI in slice 1 — signup users don't need it.

**i18n.** `lib/i18n.js` exports a `t(key)` helper backed by a Svelte store. Locale resolution: `?lang=da` query param → `Accept-Language` header on first SSR (n/a here — adapter-static serves pre-rendered EN) → default `en`. Slice 1 `da.json` is `{}`; the helper falls back to the `en.json` value if the key is missing in the active locale.

```js
// Sketch
import en from '../messages/en.json';
import da from '../messages/da.json';
const dicts = { en, da };
export const locale = writable('en');
export function t(key) {
  return dicts[get(locale)]?.[key] ?? dicts.en[key] ?? key;
}
```

---

## Dev workflow

Three new Makefile targets (root `Makefile`):

```make
signup-dev:
	cd apps/signup && npm install --prefer-offline && npm run dev

signup-build:
	cd apps/signup && npm install --prefer-offline && npm run build

signup-test:
	cd apps/signup && npm install --prefer-offline && npm run test
```

`make dev-up` is unchanged — backend stack still comes up via `infra/compose/docker-compose.dev.yml`. `make signup-dev` runs SvelteKit on the host (port 5173) and proxies to the backend at `localhost:8001`.

**Editing `Makefile` will trigger the `infra_danger_zone.py` hook** (context-injection, non-blocking). Expected.

---

## Testing

**Vitest** (in-app):
- `tests/i18n.test.js`: key lookup, locale switching, EN fallback when key missing in DA.
- `tests/api.test.js`: fetch wrapper success path, error normalization for 4xx/5xx/network failure.

**Pytest** (existing test suite):
- `tests/test_api_signup_validate.py` — see "Pytest coverage" in Backend additions for the full case list.
- `tests/test_signup_round_trip.py` — full validate → Telegram-activate → re-validate round-trip; race test on `activate_watchman_trial`.

**Browser verification** (mandatory per `feedback_test_frontend_in_browser`):
- `make signup-dev`, open `http://localhost:5173/`, walk all 6 routes manually.
- `/signup/start?t=<test-token-from-fixture>` shows Telegram CTA + QR.
- `/signup/start?t=invalid` shows error UI.
- After clicking the Telegram CTA in browser dev (no real Telegram redirect — just check the href), `/signup/start?t=<same-token>` still shows valid (token only consumed by Telegram bot).
- DevTools Network tab: zero requests to external domains.
- DevTools Console: no errors, no warnings.
- Switch theme via DevTools `localStorage.setItem('heimdall.theme', 'light')` → reload → no FOUC.

**Playwright** deferred to slice 2 (real browser tests pair with the Hetzner deploy).

**Codex review of the FastAPI endpoint** is **mandatory before commit** per `precommit_codex_review_guard.py`. Bypass prefix `HEIMDALL_CODEX_REVIEWED=1` only after a real review.

---

## Security

- **Origin validation** on `POST /signup/validate`. Allowlist from `SIGNUP_ALLOWED_ORIGINS` env var. Slice 1 single abuse control (read-only endpoint, no state mutation, idempotent).
- **Rate limiter deferred to slice 2.** `slowapi` is not in `requirements.txt`; the dep + limiter wiring is a slice-2 concern alongside the Hetzner public exposure. Until then, the endpoint is read-only and the Origin allowlist limits cross-site abuse.
- **Token format verified:** `src/db/signup.py` issues `secrets.token_urlsafe(24)` = 32 URL-safe characters (no `+/=` padding). No URL-encoding needed for the `?t=<token>` parameter.
- **No third-party scripts in the bundle.** No analytics, no error tracking, no fonts from CDN, no embedded social widgets. Tokens in `?t=...` would leak via Referer header to any external load. Self-hosted favicon. **System font stack** (`font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif`) — no font files to ship, no CDN load. Zero outbound network calls except to `/api/*`.
- **`history.replaceState` strips the token** from the visible URL after the validate call (whether success or failure) so the token doesn't sit in browser history past the page lifetime.
- **No tracking cookies set.** Only `localStorage["heimdall.theme"]` is written, which is strictly necessary (not subject to ePrivacy consent). Therefore: **no cookie consent banner.** Adding one later "to be safe" is a regression unless tracking is actually introduced.

## Accessibility (a11y)

- QR `<img>` carries `alt="Open Telegram on your phone — scan this code"`.
- Telegram CTA is `<a href="https://t.me/...">` styled as a button (semantic link, not `<button onclick>`).
- `<html lang="en">` (or `lang="da"` when locale switches).
- Color contrast: tokens.css already meets AA in both themes (verified for the operator console). Spot-check the signup-specific layouts.
- Keyboard navigation: focus rings on all interactive elements (CSS `:focus-visible` baseline in `app.css`).

---

## Verification checklist for slice 1 (writing-plans success criteria)

1. `make signup-dev` opens at `http://localhost:5173`, all 6 routes render without error.
2. `/signup/start?t=<valid-test-token>` shows the Telegram deep-link button + QR code with the correct `https://t.me/<bot>?start=<token>` payload.
3. `/signup/start?t=invalid` shows the error UI with the fallback CTA.
4. `/signup/start?t=<expired-token>` and `/signup/start?t=<consumed-token>` each show their reason-specific UI.
5. After validate succeeds, the DB token row is **unchanged** (`consumed_at IS NULL`, `email` not nulled). Verifies the no-mutation contract.
6. `make signup-build` produces a non-empty `apps/signup/build/` directory.
7. `make signup-test` is green (Vitest).
8. `pytest tests/test_api_signup_validate.py tests/test_signup_round_trip.py` is green, including the round-trip and race tests.
9. The new FastAPI endpoint + the `payment_events` migration both passed Codex review before their commits (`HEIMDALL_CODEX_REVIEWED=1` only after actual review).
10. Theme bootstrap: light/dark switches via `localStorage` override, no FOUC on reload.
11. DevTools Network tab during a full session shows zero requests to external domains.
12. DevTools Console: zero errors, zero warnings.

**Slice 1 acceptance is `dev-ready`, not `prod-ready`.** Hetzner deploy, Postmark Message-0 sender, public DNS, the `/health` Caddy responder, and the rate limiter are slice-2 work. A green slice-1 means: the SvelteKit project builds, the validate endpoint serves correct responses against the dev DB, the Telegram round-trip works against the dev bot, and the design tokens render in both themes. It does **not** mean a public user can sign up — that's slice 2.

---

## Open items (require resolution during implementation)

1. **Bot username env var name**: spec uses `TELEGRAM_BOT_USERNAME`. Verify against `src/core/config.py` conventions before commit; rename to match if a convention exists.
2. **Signup-site `/health` route**: cloud-hosting plan verification step requires `curl https://signup.digitalvagt.dk/health → 200`. Slice-1 (dev-only) does not need this; slice 2 must add a Caddy `/health` static responder when the box is provisioned. Tracked here so the Hetzner runbook doesn't get caught off-guard.
3. **`activate_watchman_trial` `company_name` parameter**: the function requires `company_name` if no client row exists for the CVR. Slice 1 uses test fixtures where the row pre-exists, so this is not exercised. Slice 3 (operator UI to issue magic links) needs to decide whether to enforce a clients-row precondition before token issuance, or pass `company_name` through. Not blocking slice 1.

---

## Out of scope — explicit slice boundary

Anything below is **not** in slice 1; do not let scope creep pull it in:

- Hetzner box provisioning, Caddyfile, Simply DNS records, TLS cert, Tailscale wiring (slice 2).
- Postmark account setup, API key management, `mail.digitalvagt.dk` SPF/DKIM/DMARC (slice 2 or 3).
- Postmark integration + Message 0 sender code (slice 2 or 3).
- Danish translations of stub copy (slice 3).
- Final marketing copy (Federico writes; follow-up slice).
- Operator console "issue magic link" UI (slice 3 — needs `src/db/signup.issue_token` to exist; verify during implementation).
- MitID Erhverv OIDC flow, scope picker, PDF generation, Betalingsservice mandate (separate Sentinel-onboarding slice; MitID broker selection still pending — Idura / Criipto / Signicat).
- Cookie consent banner (will only be added if tracking is introduced — see Security).
- Theme toggle UI on the signup site (signup users don't need it).
- Service worker / PWA shell (not justified at this stage).

---

## Related documents

- `~/.claude/plans/i-need-you-to-logical-pebble.md` — locked Sentinel onboarding plan (D1–D22).
- `docs/plans/cloud-hosting-plan.md` — hosting + DevSecOps plan (committed 2026-04-25, includes the cloud-devsec critique resolutions).
- `docs/business/onboarding-playbook.md` — onboarding flow + 12-message sequence.
- `src/db/signup.py` — magic-link token CRUD: `create_signup_token`, `consume_signup_token`, `get_signup_token`, `expire_stale_tokens`.
- `src/db/onboarding.py` — `activate_watchman_trial(conn, token, telegram_chat_id)` is the sole atomic state-mutation point in the Watchman activation flow. Called by the Telegram `/start <token>` handler.
- `src/api/frontend/` — operator console, source of design tokens to copy.
- `.claude/agents/architect/SKILL.md`, `.claude/agents/python-expert/SKILL.md` — agent ownership.

---

**Next step after approval:** invoke `superpowers:writing-plans` to produce the implementation plan that delivers this spec.
