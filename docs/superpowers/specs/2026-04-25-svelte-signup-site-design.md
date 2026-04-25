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
- 2026-04-25 cloud-hosting plan: `adapter-static` + Caddy serves bundle directly; MitID OIDC redirect_uri lands on backend FastAPI; Postmark EU API for transactional email; Caddy reverse-proxies `signup.<domain>/api/*` to backend over Tailscale.
- Backend already shipped: `src/db/signup.py` (token issue + consume), `/start <token>` Telegram handler. The magic-link consumer has a server but no UI.

---

## Scope

**This slice ships:**
- Standalone SvelteKit project at `apps/signup/`, `adapter-static`.
- Design tokens copied once from `src/api/frontend/src/styles/tokens.css`.
- 6 routes: `/`, `/pricing`, `/signup/consume`, `/legal/{privacy,terms,dpa}` + SvelteKit defaults (404, 500).
- Magic-link consumer end-to-end: SvelteKit page calls a new backend endpoint, renders Telegram deep-link + QR code on success, error UI on failure.
- New FastAPI endpoint `POST /signup/consume` wrapping `src/db/signup.consume_token()`.
- i18n machinery: simple JSON dict + `t()` helper, EN as source of truth, DA placeholder file.
- Light/dark theme support via the same no-FOUC bootstrap pattern as the operator console.
- Vitest unit tests (i18n + api wrapper), pytest tests for the new endpoint.
- Three Makefile targets: `signup-dev`, `signup-build`, `signup-test`.

**Explicitly deferred to later slices:**
- Hetzner box provisioning, Caddyfile, Simply DNS records, TLS, Tailscale wiring → slice 2.
- Postmark integration + Message 0 send → slice 2 or 3 (needs Postmark account + `mail.<domain>` DNS).
- Danish translations of all stub copy → slice 3 (after EN copy is approved).
- Operator console "issue magic link" UI → slice 3 (separate backend endpoint to *issue* tokens; verify exists).
- MitID Erhverv OIDC flow, scope picker, PDF generation, Betalingsservice mandate → separate Sentinel-onboarding slice (broker selection still pending).
- Final marketing copy → follow-up slice (Federico writes; this slice ships stubs).

---

## Architecture

`apps/signup/` is a standalone SvelteKit project, independent of `src/api/frontend/` (the operator console). Vite dev server runs on host `:5173` with a proxy `/api/*` → `http://localhost:8000` (the FastAPI dev container, exposed on host via `make dev-up`). Production build (slice 2) emits to `apps/signup/build/`, which Caddy on the signup box serves directly. No Node runtime in production.

The bundle uses **relative** `/api/*` fetches so the same code works in dev (Vite proxy) and prod (Caddy reverse-proxy to backend Tailscale IP). No `PUBLIC_API_BASE` env-baking.

Both the Vite dev proxy and the prod Caddy reverse-proxy **strip the leading `/api` path segment** before forwarding. The backend FastAPI router prefix is therefore `/signup` (no `/api`), which aligns with the existing `/console` and `/health` convention. The `/api/*` namespace exists only on the bundle side as a stable proxy hook.

```
                                Public internet
                                       │
                                       ▼
                              signup.<domain>:443
                          ┌────────────────────────┐
                          │ Caddy (signup box)     │
                          │ • serves /build/*      │
                          │ • proxies /api/*       │──── Tailscale ───►  Backend FastAPI
                          └────────────────────────┘                     /signup/consume
                                                                         (calls src/db/signup.consume_token)
```

Slice 1 stops at the dashed line above — only the SvelteKit + backend endpoint pair lands. Caddy + Hetzner are slice 2.

---

## File layout

```
apps/signup/
  package.json
  svelte.config.js              # adapter-static
  vite.config.js                # /api/* dev-proxy → localhost:8000
  src/
    app.html                    # no-FOUC theme bootstrap (mirrors src/api/frontend/index.html)
    routes/
      +layout.svelte            # nav, footer
      +page.svelte              # /
      pricing/+page.svelte      # /pricing (reads lib/pricing.json)
      signup/consume/+page.svelte    # /signup/consume — the only functional route
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
| `/pricing` | Pricing | Watchman + Sentinel cards reading from `lib/pricing.json`; CTA → `mailto:` |
| `/signup/consume?t=<token>` | Magic-link consumer | **Functional.** See "Magic-link flow" below. |
| `/legal/privacy` | Privacy stub | H1 + disclaimer block: *"This is a placeholder. Final terms pending review by Anders Wernblad, Aumento Law. Do not rely on this text."* |
| `/legal/terms` | Terms stub | Same disclaimer pattern |
| `/legal/dpa` | DPA stub | Same disclaimer pattern |
| `/404`, `/500` | SvelteKit defaults | Themed via `app.css` |

---

## Magic-link flow

1. User clicks the link in Message 0 email: `https://signup.<domain>/signup/consume?t=<32-char-token>`.
2. SvelteKit page `signup/consume/+page.svelte` reads `?t=<token>` from `$page.url.searchParams`.
3. Page calls `POST /api/signup/consume` with `{token}` (Vite proxy → backend `/signup/consume` in dev; Caddy proxy in prod).
4. Backend handler:
   - Validates Origin header (rejects requests not from `signup.<domain>` in prod or `http://localhost:5173` in dev — dev allowlist from env var).
   - Calls `src/db/signup.consume_token(token)`.
   - Returns `{ok: true, bot_username: "<from env TELEGRAM_BOT_USERNAME>"}` on success.
   - Returns `{ok: false, reason: "expired"|"used"|"invalid"}` on failure (HTTP 200 either way — payload carries the outcome; this is a UX-driven endpoint, not a REST-purist one).
5. **On success**, page renders:
   - Heading: *"Almost there — open Telegram to finish."*
   - Primary CTA: `<a href="https://t.me/<bot_username>?start=<token>">Open Telegram</a>` styled as a button.
   - QR code below the button: `<img alt="Open Telegram on your phone — scan this code" src="<data-url>">`. QR generated client-side by the `qrcode` npm package (~5KB).
   - Fallback text: *"No Telegram? Reply to the email and Federico will help."*
   - Calls `history.replaceState({}, '', '/signup/consume')` to strip the token from the visible URL.
6. **On failure**, page renders the reason-specific copy + the same fallback CTA.

**Why the bot username comes from the backend response** rather than a build-time env var: dev and prod use different bots (`@HeimdallSecurityDEVbot` in dev, prod TBD post-naming-session). Backend reads `TELEGRAM_BOT_USERNAME` env var; bundle stays generic.

**Why `consume_token` semantics need verification before binding the response shape**: open question (see Open items below) — does `consume_token` write to `consent_records`? If yes, Valdí is on the path and Gate-2 must run.

---

## Backend additions

New file: `src/api/signup.py` (or extension to existing `src/api/console.py` — implementer's call, prefer new module to avoid bloating console.py beyond its 9 endpoints).

```python
# Sketch — actual implementation per python-expert + Codex review
from fastapi import APIRouter, Request, HTTPException
from src.db.signup import consume_token

router = APIRouter(prefix="/signup")

ALLOWED_ORIGINS = os.environ.get("SIGNUP_ALLOWED_ORIGINS", "http://localhost:5173").split(",")

@router.post("/consume")
async def consume(request: Request, body: ConsumeBody):
    if request.headers.get("origin") not in ALLOWED_ORIGINS:
        raise HTTPException(403, "origin_not_allowed")
    # Rate limit: 10 req/min per client IP — slowapi or equivalent.
    result = consume_token(body.token)
    return {
        "ok": result.ok,
        "reason": result.reason,
        "bot_username": os.environ["TELEGRAM_BOT_USERNAME"] if result.ok else None,
    }
```

**Wired into the FastAPI app** at `src/api/app.py` via `app.include_router(signup.router)`.

**Pytest coverage** in `tests/test_api_signup_consume.py` mirrors the patterns in `tests/test_db_signup.py`: valid token → 200 + ok=true; expired → 200 + ok=false + reason="expired"; bad origin → 403; rate-limited → 429.

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

`make dev-up` is unchanged — backend stack still comes up via `infra/compose/docker-compose.dev.yml`. `make signup-dev` runs SvelteKit on the host (port 5173) and proxies to the backend at `localhost:8000`.

**Editing `Makefile` will trigger the `infra_danger_zone.py` hook** (context-injection, non-blocking). Expected.

---

## Testing

**Vitest** (in-app):
- `tests/i18n.test.js`: key lookup, locale switching, EN fallback when key missing in DA.
- `tests/api.test.js`: fetch wrapper success path, error normalization for 4xx/5xx/network failure.

**Pytest** (existing test suite):
- `tests/test_api_signup_consume.py`: valid token, expired token, used token, invalid token, bad Origin (403), rate-limit hit (429). Mirrors the contract pattern from `tests/test_db_signup.py`.

**Browser verification** (mandatory per `feedback_test_frontend_in_browser`):
- `make signup-dev`, open `http://localhost:5173/`, walk all 6 routes manually.
- `/signup/consume?t=<test-token-from-fixture>` shows Telegram CTA + QR.
- `/signup/consume?t=invalid` shows error UI.
- DevTools Network tab: zero requests to external domains.
- DevTools Console: no errors, no warnings.
- Switch theme via DevTools `localStorage.setItem('heimdall.theme', 'light')` → reload → no FOUC.

**Playwright** deferred to slice 2 (real browser tests pair with the Hetzner deploy).

**Codex review of the FastAPI endpoint** is **mandatory before commit** per `precommit_codex_review_guard.py`. Bypass prefix `HEIMDALL_CODEX_REVIEWED=1` only after a real review.

---

## Security

- **Origin validation** on `POST /signup/consume`. Allowlist from `SIGNUP_ALLOWED_ORIGINS` env var.
- **Rate limit** 10 req/min per client IP (slowapi or equivalent — verify dep before adding).
- **Token format**: `src/db/signup.py` must issue URL-safe base64 (no `+/=` padding) so `?t=<token>` doesn't need encoding. Verify during implementation; if format is unsafe, fix in `src/db/signup.py` (open-issue ticket).
- **No third-party scripts in the bundle.** No analytics, no error tracking, no fonts from CDN, no embedded social widgets. Tokens in `?t=...` would leak via Referer header to any external load. Self-hosted favicon. **System font stack** (`font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif`) — no font files to ship, no CDN load. Zero outbound network calls except to `/api/*`.
- **`history.replaceState` strips the token** from the visible URL after consume call (whether success or failure) so the token doesn't sit in browser history past the page lifetime.
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
2. `/signup/consume?t=<valid-test-token>` shows the Telegram deep-link button + QR code with the correct `?start=<token>` payload.
3. `/signup/consume?t=invalid` shows the error UI with the fallback CTA.
4. `make signup-build` produces a non-empty `apps/signup/build/` directory.
5. `make signup-test` is green.
6. `pytest tests/test_api_signup_consume.py` is green.
7. The new FastAPI endpoint passed Codex review before its commit (`HEIMDALL_CODEX_REVIEWED=1` only after actual review).
8. Theme bootstrap: light/dark switches via `localStorage` override, no FOUC on reload.
9. DevTools Network tab during a full session shows zero requests to external domains.
10. DevTools Console: zero errors, zero warnings.

---

## Open items (require resolution during implementation)

1. **`consume_token` semantics**: does it write to `consent_records`, or only update `signup_tokens.consumed_at`? If consent_records is touched, Valdí is on the path and a Gate-2 check is required. **Action:** read `src/db/signup.py` first thing during implementation; loop in valdi if consent_records is touched.
2. **Token URL-safety**: confirm tokens issued by `src/db/signup.py` are URL-safe base64. If not, fix in `src/db/signup.py` before binding the URL shape.
3. **Rate-limit dependency**: confirm `slowapi` (or equivalent) is in `requirements.txt`. If not, python-expert decides between adding it and rolling a minimal limiter against Redis (already in the stack).
4. **Bot username env var name**: settle on `TELEGRAM_BOT_USERNAME` (proposed) vs whatever convention exists in `src/core/config.py`. Use existing convention if there is one.
5. **API path alignment with operator console**: console uses `/console/...`. Spec uses `/signup/...` for public signup paths. Confirm with python-expert during implementation that this matches the existing FastAPI router-prefix pattern.

---

## Out of scope — explicit slice boundary

Anything below is **not** in slice 1; do not let scope creep pull it in:

- Hetzner box provisioning, Caddyfile, Simply DNS records, TLS cert, Tailscale wiring (slice 2).
- Postmark account setup, API key management, `mail.<domain>` SPF/DKIM/DMARC (slice 2 or 3).
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
- `src/db/signup.py` — magic-link token table + `consume_token`.
- `src/api/frontend/` — operator console, source of design tokens to copy.
- `.claude/agents/architect/SKILL.md`, `.claude/agents/python-expert/SKILL.md` — agent ownership.

---

**Next step after approval:** invoke `superpowers:writing-plans` to produce the implementation plan that delivers this spec.
