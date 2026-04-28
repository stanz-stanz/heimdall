# Stage A Slice 3g.5 — SPA Vitest harness + auth-flow tests — Implementation Spec

**Status:** **LOCKED** — §7.1–§7.7 all decided 2026-04-29. §7.3 (the merge-blocking decision) resolved to Option A + 1: separate `frontend` CI job parallel to `test` + `package-lock.json` committed for both `src/api/frontend/` and `apps/signup/`. Slice 3g.5 implementation is unblocked.
**Sprint:** Stage A (production-deploy gate for the slice 3g bundle on `feat/stage-a-foundation`).
**Author:** Application Architect agent, 2026-04-28 (post-3g implementation wrap-up); locked 2026-04-29 by Federico.
**Master spec:** `docs/architecture/stage-a-implementation-spec.md` — cite by section number; never restate contracts here.
**Parent slice spec:** `docs/architecture/stage-a-slice-3g-spec.md` — slice 3g.5 is the §7.11 hard-gate companion to slice 3g; cite §-numbers there for all SPA-side contracts.
**Locks scope from:** `docs/architecture/stage-a-slice-3g-spec.md` §7.11 ("hard-gate production deploy on slice 3g.5") + §11 ("Vitest harness for SPA tests — Slice 3g.5") + slice 3g spec §5.3 ("New SPA tests — out of scope for the Python harness").

> Slice 3g.5 is **the production-deploy gate for the slice 3g bundle.** Slice 3g implementation has merged to `feat/stage-a-foundation` (commits `f3f95da`, `9f2f583`, `72d7386`). The bundle does NOT merge to `main` or push to `prod` until slice 3g.5 lands the SPA Vitest harness and auth-flow tests green. Rationale: a new auth-critical frontend state machine without automated coverage is too thin a test floor for a control-plane cutover, and `src/api/frontend/` has no Vitest setup today.
>
> **Browser-eyeball QA is required, not replaceable.** Per memory `feedback_test_frontend_in_browser`, every SPA change must be eyeballed in a real browser before merge. Vitest is the automated floor; browser QA is the ceiling. Slice 3g.5 ships both.

---

## Summary

Slice 3g (a)(b)(c) shipped the SPA login state machine, whoami bootstrap, CSRF helper, logout button, and four new component / module files in `src/api/frontend/`:

- `src/api/frontend/src/lib/auth.svelte.js` — 276 LOC. The `$state` runes + `bootstrap()` / `login()` / `logout()` / `getCsrfToken()` / `tickRateLimit()` / `handleSessionExpired()` exports; module-level `bootstrapInFlight` promise collapses concurrent callers; `getCsrfToken()` re-hydrates from `document.cookie['heimdall_csrf']` per slice 3g spec §7.2 Option C.
- `src/api/frontend/src/views/Login.svelte` — 216 LOC. Form with `submitting / rate-limited / 401 / 503 / network` branches; `$effect` drives the rate-limit countdown via `tickRateLimit()`.
- `src/api/frontend/src/views/BootstrapEmpty.svelte` (51 LOC) + `views/AllDisabled.svelte` (50 LOC) — splash components per slice 3g spec §7.4 / §7.5 (Option C / Option B).
- `src/api/frontend/src/lib/api.js` — `csrfHeaders()` threaded through `postJSON / saveSettings / sendCommand`; 401 path calls `handleSessionExpired()` (fire-and-forget) before throwing `SESSION_REQUIRED_MESSAGE`.
- `src/api/frontend/src/App.svelte` — outer `{#if}` chain on `auth.status`; single `$effect` is the WS startup site (per slice 3g spec §7.3 Option C); tears down WS + resets shell counters when `auth.status` leaves `'authenticated'`.

`src/api/frontend/package.json` has zero Vitest setup. Slice 3g.5 ships the harness and the auth-flow tests that close the §7.11 production-deploy gate. After 3g.5 lands green, the slice 3g bundle merges to `main` and pushes to `prod` per the standard deploy flow (`docs/runbook-prod-deploy.md`). After that, the next sprint is Stage A.5 (`Permission` enum, `require_permission`, `config_changes` triggers, `X-Request-ID` middleware, `/console/config/history`).

---

## Table of contents

1. [Locked scope (atomic)](#1-locked-scope-atomic)
2. [Vitest harness configuration](#2-vitest-harness-configuration)
3. [Auth state-machine unit tests (`auth.svelte.js`)](#3-auth-state-machine-unit-tests-authsvelteJs)
4. [Component tests (`Login.svelte` / `BootstrapEmpty.svelte` / `AllDisabled.svelte`)](#4-component-tests-loginsvelte--bootstrapemptysvelte--alldisabledsvelte)
5. [Integration tests (CSRF threading + mid-session 401 + bootstrap collapse)](#5-integration-tests-csrf-threading--mid-session-401--bootstrap-collapse)
6. [Test-runner integration (Makefile + CI)](#6-test-runner-integration-makefile--ci)
7. [Decisions (open)](#7-decisions-open)
8. [Out of scope](#8-out-of-scope)
9. [Rollback plan](#9-rollback-plan)
10. [Appendix A — file map](#10-appendix-a--file-map)
11. [Appendix B — affected master-spec sections](#11-appendix-b--affected-master-spec-sections)
12. [Revision history](#12-revision-history)

---

## 1. Locked scope (atomic)

The seven components below ship as one slice. Each refers to the parent slice 3g spec or the master spec by section number.

| ID | Component | Slice 3g / master ref | Lands in |
|---|---|---|---|
| (a) | Vitest harness configs in `src/api/frontend/`: dev-deps in `package.json`, `vitest.config.js`, `tests/` directory, `"test"` npm script. | Slice 3g spec §11 (out of scope row "Vitest harness for SPA tests — Slice 3g.5") | `src/api/frontend/package.json` (+ deps) + `src/api/frontend/vitest.config.js` (new) + `src/api/frontend/tests/` (new dir) |
| (b) | Auth state-machine unit tests for `lib/auth.svelte.js`: `bootstrap()` 200/204/409/401/503/network branches; `login()` 200/401/429/503/`http_500` (generic non-503 5xx)/`malformed_response` (200 with bad JSON)/network branches; `logout()` 204/401/503/network branches; `getCsrfToken()` cookie-fallback; `tickRateLimit()` countdown; `handleSessionExpired()` re-probe. Full assertion list in §3. | Slice 3g spec §2.2, §3.2, §7.2 Option C, §7.3 Option C, §7.6 Option B + master spec §3.5, §6.3 | `src/api/frontend/tests/auth.test.js` (new) |
| (c) | Component tests for `views/Login.svelte`: idle render, submitting state, invalid_credentials error region, rate-limited countdown derived from `auth.retryAfter`, service_unavailable / network error branches, form-disabled-while-submitting. | Slice 3g spec §2.3 | `src/api/frontend/tests/Login.test.js` (new) |
| (d) | Component tests for `views/BootstrapEmpty.svelte` + `views/AllDisabled.svelte`: each splash renders the spec-blessed copy block; no form fields; no fetch calls fired. | Slice 3g spec §2.4, §7.4 Option C, §7.5 Option B | `src/api/frontend/tests/splash.test.js` (new — both splashes covered in one file since each is ≤30 LOC of assertions) |
| (e) | Integration tests for CSRF threading on `lib/api.js`: `postJSON` / `saveSettings` / `sendCommand` send `X-CSRF-Token` when `getCsrfToken()` returns a value; `fetchJSON` does NOT send the header; mid-session 401 from any helper triggers `handleSessionExpired()` and throws the `SESSION_REQUIRED_MESSAGE`. | Slice 3g spec §3.3, §3.4, §3.5 + master spec §4.4 | `src/api/frontend/tests/api.test.js` (new) |
| (f) | Bootstrap state-machine integration test: two parallel `bootstrap()` calls share the same in-flight promise and produce one `fetch('/console/auth/whoami')` round trip with one final state mutation. Locks the spec §2.2 + §3.4 race-mitigation contract (`bootstrapInFlight` collapse). | Slice 3g spec §2.2, §3.4 | `src/api/frontend/tests/bootstrap.test.js` (new) |
| (g) | Makefile target `frontend-test` + a thin `make` wiring rule mirroring `make signup-test`'s shape. **[Necessary but not sufficient for the hard-gate — see footnote.]** | New | `Makefile` (+5 LOC) |

> **Footnote on (g) — the gate is not local.** The Makefile target makes the test suite runnable, but a runnable suite is not a hard-gate. Without a CI job that runs `make frontend-test` on every PR to `main` and blocks merge on red, "tests must be green before merge" is operator self-attestation, not a mechanical gate. The CI job lives in §7.3, and §7.3 must be locked (Option A or Option B — not Option C / deferred) before slice 3g.5 itself can lock. Component (g) is necessary; the §7.3 CI job is the missing sufficient condition.

**Why atomic.** Harness without tests is dead code. Tests without harness can't run. Auth-state-machine tests without component tests miss the form-submission paths. Component tests without integration tests miss the CSRF wire shape. Splitting any of these out delays the §7.11 hard-gate by exactly the duration of the omitted slice; combining them in one slice clears the gate in one merge.

**Gate scope (narrow, not "all SPA paths covered").** Slice 3g.5's automated coverage ends at the auth state machine + SPA login UI + lib/api.js wire shape. The `App.svelte` authenticated-flip `$effect` (the single WS startup/teardown trigger per slice 3g spec §7.3 Option C) is verified by browser-eyeball QA only — see §8 for the explicit out-of-scope row. App.svelte is a thin wiring layer; its state-machine inputs are unit-tested in §3, and adding an App.svelte integration test expands the slice into App-component territory without a proportional safety gain. The gate claim is therefore: "Vitest covers the auth state machine and SPA login UI; the App.svelte WS effect is verified by browser QA."

**Production-deploy contract.** Slice 3g.5 is green ⇒ slice 3g bundle is mergeable to `main` and pushable to `prod`. Slice 3g.5 is red or absent ⇒ the slice 3g bundle stays on `feat/stage-a-foundation` per slice 3g spec §7.11 Option B. Component (g) — Makefile target — is necessary but **not sufficient** for the gate to be mechanical; the CI job is what makes the gate enforceable, and that lives in §7.3. See the §7 prose intro for the load-bearing dependency. Browser-eyeball QA in DEV against `make dev-up` is also required before merge per the parent spec §5.3 + memory `feedback_test_frontend_in_browser`; Vitest is the floor, browser QA is the ceiling.

**Why this is its own slice, not folded into 3g.** Setting up a Vitest harness inside the existing Vite project (`src/api/frontend/`) plus writing the auth-state-machine + component + integration tests is itself a meaningful side-project (~400 LOC across 6 new files + 1 modified). Folding it into slice 3g would have ballooned slice 3g into a frontend-tooling slice with two distinct review surfaces (Python WS handler + frontend test infra). Decoupling preserves slice 3g's narrow scope.

---

## 2. Vitest harness configuration

### 2.1 `src/api/frontend/package.json` edits

Add three dev-deps + one script. Versions match `apps/signup/package.json` exactly (rationale: one Vitest version across the repo to avoid two npm caches and two upgrade tracks):

```json
{
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview",
    "test": "vitest run"
  },
  "devDependencies": {
    "svelte": "^5.0.0",
    "vite": "^6.0.0",
    "@sveltejs/vite-plugin-svelte": "^5.0.0",
    "@testing-library/svelte": "^5.2.4",
    "jsdom": "^25.0.0",
    "vitest": "^2.1.0"
  }
}
```

`@testing-library/svelte@^5.2.4` works against Svelte 5 (the SPA already runs Svelte 5 runes; same major as `apps/signup/`). `vitest@^2.1.0` + `jsdom@^25.0.0` mirror `apps/signup/` exactly. No new top-level deps are added — the harness is dev-only.

### 2.2 `src/api/frontend/vitest.config.js` (new — 20 LOC)

Mirrors `apps/signup/vitest.config.js` line-for-line, adjusted only for the alias path:

```js
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

The `$lib` alias points at `src/api/frontend/src/lib/` so tests can `import { auth, bootstrap } from '$lib/auth.svelte.js'` rather than relative paths. (Tests can also use relative imports; alias is the preferred shape because it survives test-file moves.)

### 2.3 `src/api/frontend/tests/` (new directory)

Test files live here per Decision §7.1 (Option A — co-located in `tests/`, mirrors `apps/signup/`). Five files land in 3g.5:

- `tests/auth.test.js` — auth state-machine unit tests (§3 below).
- `tests/Login.test.js` — Login.svelte component tests (§4 below).
- `tests/splash.test.js` — BootstrapEmpty + AllDisabled component tests (§4 below).
- `tests/api.test.js` — CSRF threading + mid-session 401 integration tests (§5 below).
- `tests/bootstrap.test.js` — bootstrap in-flight collapse integration test (§5 below).

### 2.4 jsdom shim — `localStorage` / `document.cookie`

`apps/signup/tests/i18n.test.js:17-33` documents that jsdom returns `{}` for `window.localStorage` instead of a real `Storage` instance — same shim transfers if any 3g.5 test needs `localStorage` (none do today, but the `getCsrfToken()` cookie-fallback test in `tests/auth.test.js` needs `document.cookie`). jsdom DOES implement `document.cookie` correctly, so the shim is not needed for the cookie-fallback path. If a future test needs `localStorage`, copy the `installMemStorage` helper from `apps/signup/tests/i18n.test.js`.

Centralisation note: if more than one 3g.5 test file ends up needing the same shim, lift it to `src/api/frontend/tests/_helpers.js`. For 3g.5's six test files this is not required — only the cookie-fallback path needs cookie state, and it can set `document.cookie = 'heimdall_csrf=fixture-token'` directly.

### 2.5 `vi.stubGlobal('fetch', ...)` pattern

Matches `apps/signup/tests/api.test.js:10-17` exactly. Each test that exercises a fetch helper stubs `fetch` to return the response shape under test, runs the helper, asserts the result. `vi.restoreAllMocks()` in `beforeEach`.

### 2.6 Svelte 5 runes inside Vitest — implementation assumption

**Assumption to verify in the first 3g.5 PR.** `auth.svelte.js` declares `export const auth = $state({...})` at module scope. The expectation is that Vitest's Vite-based runner with `@sveltejs/vite-plugin-svelte` honours the `$state` rune transform via the `.svelte.js` extension (the plugin treats `*.svelte.js` files as Svelte rune modules) without additional config beyond what `apps/signup/`'s harness already does.

**Why this is an assumption, not established fact.** `apps/signup/` is the only Vitest project in the repo today, and its tests do NOT exercise any `.svelte.js` rune modules — the signup site's `lib/i18n.js` and `lib/api.js` are plain ESM. The "rune modules work in Vitest" claim therefore can't be inferred from `apps/signup/` precedent alone; it has to be proved during the first slice 3g.5 PR. If `import { auth } from '$lib/auth.svelte.js'` in a Vitest test file fails to compile the `$state` runes (or compiles them but the reactive reads/writes don't settle in jsdom), the slice has to add a Svelte 5 plugin config — a non-trivial expansion that would need to be tracked as a follow-up decision before the slice can lock.

**Mitigation.** The first auth-test file in the slice 3g.5 PR includes a one-shot smoke test (`test_runes_settle_in_jsdom`) that reads `auth.status`, mutates it, and re-reads — if that test passes, the harness assumption holds. If it fails, slice 3g.5 stops at the harness step and Federico is paged; the test files that follow assume the smoke test is green.

Tests assert on `auth.status` / `auth.csrfToken` / etc. by importing `auth` directly: `import { auth, bootstrap } from '$lib/auth.svelte.js'`. The reactive reads/writes are expected to work in jsdom because jsdom provides a synchronous DOM and the `$state` runes don't need a microtask flush to settle — but again, this is the assumption-to-verify, not an established fact.

---

## 3. Auth state-machine unit tests (`auth.svelte.js`)

### 3.1 File: `src/api/frontend/tests/auth.test.js` (~250 LOC, 32 tests)

Pattern mirrors `apps/signup/tests/api.test.js` and `apps/signup/tests/i18n.test.js`. Per-test stubs `fetch` via `vi.stubGlobal` (installed BEFORE rendering / calling the helper), runs the exported helper, asserts on the `auth` rune state.

### 3.2 `bootstrap()` — ten branches

Spec citation: slice 3g spec §2.1 (whoami state machine) + §3.2 (bootstrap shape) + master spec §3.5 (whoami split states), §6.3 (auth router response shapes).

Intent: lock every status code branch + the loading-flicker suppression so a refactor can't quietly drop the cold-bootstrap signal handling or re-introduce flicker on re-probe.

| # | Test name | fetch stub returns | Assertion |
|---|---|---|---|
| 1 | `test_bootstrap_200_authenticated` | `200` + `{operator, csrf_token}` | `auth.status === 'authenticated'`; operator populated; `csrfToken === 'tok'`; `error === null`. |
| 2 | `test_bootstrap_204_bootstrap_empty` | `204` | `auth.status === 'bootstrap-empty'`; operator/csrfToken cleared. |
| 3 | `test_bootstrap_409_all_disabled` | `409` | `auth.status === 'all-disabled'`. |
| 4 | `test_bootstrap_401_unauthenticated` | `401` | `auth.status === 'unauthenticated'`; `error === null` (cold-bootstrap signal, not an error). |
| 5 | `test_bootstrap_503_service_unavailable` | `503` | `auth.status === 'unauthenticated'`; `error === 'service_unavailable'`. |
| 6 | `test_bootstrap_network_error` | `fetch` throws | `auth.status === 'unauthenticated'`; `error === 'network'`. |
| 7 | `test_bootstrap_5xx_other_falls_through` | `500` | `auth.status === 'unauthenticated'`; `error === 'http_500'`. |
| 8 | `test_bootstrap_malformed_200_body` | `200` but `json()` throws `SyntaxError` | `auth.status === 'unauthenticated'`; `error === 'malformed_response'`. |
| 9 | `test_bootstrap_loading_state_set_first_time` | `200` after baseline `'unauthenticated'` | Status transitions through `'loading'` mid-call (fetch-side-effect spy) ONLY when prior status was not `'authenticated'`. |
| 10 | `test_bootstrap_no_loading_flicker_when_authenticated` | `200` after baseline `'authenticated'` | Status stays `'authenticated'` throughout the re-probe; never flips to `'loading'`. |

### 3.3 `login()` — seven branches

Spec citation: slice 3g spec §2.1 (login wire contract) + §3.2 (auth.svelte.js login shape) + master spec §6.3 (auth router response shapes).

Intent: lock every status code branch in `auth.svelte.js` `login()` so future refactors can't quietly drop the rate-limit clamp/floor, the malformed-200 fallback, or the generic non-503 error code mapping.

| # | Test name | fetch stub returns | Assertion |
|---|---|---|---|
| 11 | `test_login_200_authenticated` | `200` + `{operator, csrf_token}` | `login()` returns `true`; `auth.status === 'authenticated'`; `auth.csrfToken === 'tok'`. |
| 12 | `test_login_401_invalid_credentials` | `401` | `login()` returns `false`; `auth.status === 'unauthenticated'`; `auth.error === 'invalid_credentials'`. |
| 13 | `test_login_429_rate_limited` | `429` + `Retry-After: 60` | `auth.status === 'rate-limited'`; `auth.retryAfter === 60`; `auth.error === 'rate_limited'`. |
| 14 | `test_login_429_retry_after_clamped_to_3600` | `429` + `Retry-After: 99999` | `auth.retryAfter === 3600` (clamp). |
| 15 | `test_login_429_retry_after_floor_one` | `429` + missing or zero `Retry-After` | `auth.retryAfter === 1` (floor). |
| 16 | `test_login_503_service_unavailable` | `503` | `auth.error === 'service_unavailable'`; `auth.status === 'unauthenticated'`. |
| 17 | `test_login_500_generic_http_error` | `500` | `auth.status === 'unauthenticated'`; `auth.error === 'http_500'`. Locks the generic non-503 `!res.ok` branch — keeps a future "narrow the error map" refactor from collapsing 500 into `service_unavailable`. |
| 18 | `test_login_malformed_200_body` | `200` but `json()` throws `SyntaxError` | `login()` returns `false`; `auth.status === 'unauthenticated'`; `auth.error === 'malformed_response'`. Locks the JSON-parse failure path on the success branch. |
| 19 | `test_login_network_error` | `fetch` throws | `login()` returns `false`; `auth.error === 'network'`. |

### 3.4 `logout()`, `getCsrfToken()`, `tickRateLimit()`, `handleSessionExpired()`

Spec citation: slice 3g spec §2.2 (logout always-reset-locally contract), §7.2 Option C (CSRF cookie re-hydration), §3.2 (rate-limit countdown), §3.4 (mid-session 401 re-probe).

Intent: lock the four auxiliary helpers' contracts. The logout block in particular asserts the §2.2 "reset locally regardless of server response" guarantee — server status should never block client-side state cleanup.

| # | Test name | Assertion |
|---|---|---|
| 20 | `test_logout_resets_state_on_204` | After `auth.status='authenticated'`, fetch returns 204; `logout()` clears `auth.operator` / `auth.csrfToken`; sets `auth.status='unauthenticated'`; mocked `disconnect` called. |
| 21 | `test_logout_resets_state_on_401` | Fetch returns 401; local state still reset. |
| 22 | `test_logout_resets_state_on_503` | Fetch returns 503; local state still reset. Locks the "always reset locally regardless of response" contract for non-204/non-401 statuses (slice 3g spec §2.2, source `auth.svelte.js:232-254`). |
| 23 | `test_logout_resets_state_on_network_error` | Fetch throws; local state still reset. |
| 24 | `test_logout_threads_csrf_header` | `auth.csrfToken='abc'`; captured init has `'X-CSRF-Token': 'abc'`. |
| 25 | `test_get_csrf_returns_in_memory_first` | `auth.csrfToken='cached'`; getter returns `'cached'` without reading `document.cookie`. |
| 26 | `test_get_csrf_falls_back_to_cookie` | `auth.csrfToken=null`; `document.cookie='heimdall_csrf=from-cookie'`; getter returns `'from-cookie'` AND re-hydrates `auth.csrfToken='from-cookie'`. |
| 27 | `test_get_csrf_returns_null_when_neither` | No memory token, no cookie; getter returns `null`. |
| 28 | `test_get_csrf_handles_url_encoded_cookie` | `document.cookie='heimdall_csrf=tok%2Bvalue'`; getter returns `'tok+value'`. |
| 29 | `test_tick_rate_limit_decrements` | `retryAfter=5`, status `'rate-limited'`; one tick → `retryAfter === 4`, status unchanged, returns `false`. |
| 30 | `test_tick_rate_limit_terminates` | `retryAfter=1`; one tick → `retryAfter === 0`, status `'unauthenticated'`, returns `true`. |
| 31 | `test_tick_rate_limit_noop_when_not_rate_limited` | Status `'authenticated'`; tick returns `false`, no state change. |
| 32 | `test_handle_session_expired_reprobes_whoami` | Status `'authenticated'`; fetch returns 401; after `handleSessionExpired()` resolves, status is `'unauthenticated'`. |

### 3.5 Test helper — `beforeEach` reset

Each test resets the rune to a known baseline so cross-test state can't leak:

```js
beforeEach(() => {
  vi.restoreAllMocks();
  auth.status = 'loading';
  auth.operator = null;
  auth.csrfToken = null;
  auth.retryAfter = 0;
  auth.error = null;
  // Clear cookies between tests so the cookie-fallback test isn't
  // polluted by a prior test's auth.csrfToken=... write.
  document.cookie = 'heimdall_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/';
});
```

The `disconnect` import from `ws.svelte.js` is mocked at the top of the file via `vi.mock('$lib/ws.svelte.js', () => ({ disconnect: vi.fn(), connect: vi.fn() }))` so logout-tests don't touch the real WebSocket module (which has its own state and is exercised only in browser QA — see §8).

---

## 4. Component tests (`Login.svelte` / `BootstrapEmpty.svelte` / `AllDisabled.svelte`)

### 4.1 File: `src/api/frontend/tests/Login.test.js` (~150 LOC, 10 tests)

Spec citation: slice 3g spec §2.3 (Login.svelte UI states).

Intent: lock every UI render branch (idle / submitting / each error code / rate-limited countdown render) and the form-submit wire to `login()`.

Uses `@testing-library/svelte`'s `render()` + `screen` + `fireEvent`. Pattern locked by Decision §7.2 (Option A).

| # | Test name | Setup | Assertion |
|---|---|---|---|
| 1 | `test_login_renders_idle_form` | `auth.status='unauthenticated'`, `auth.error=null` | Username + password inputs present; submit reads "Sign in"; no error region. |
| 2 | `test_login_disables_form_while_submitting` | Mock `login` to never resolve; submit | Button reads "Signing in…"; both inputs disabled. |
| 3 | `test_login_renders_invalid_credentials_error` | `auth.error='invalid_credentials'` | "Invalid username or password." with `role="alert"`. |
| 4 | `test_login_renders_service_unavailable_error` | `auth.error='service_unavailable'` | "Server unavailable. Please try again." |
| 5 | `test_login_renders_network_error` | `auth.error='network'` | "Network error. Check your connection and retry." |
| 6 | `test_login_renders_generic_error_for_unknown_code` | `auth.error='http_500'` | "Login failed. Please try again." (default branch). |
| 7 | `test_login_renders_rate_limited_countdown` | `auth.status='rate-limited'`, `auth.retryAfter=42` | Submit reads "Wait 42s"; error region reads "Too many failed attempts. Try again in 42s." |
| 8 | `test_login_calls_login_on_submit` | Mock `login` returning `true`; user fills + submits | `login(username, password)` called once with typed values. |
| 9 | `test_login_clears_password_on_success` | Mock `login` returning `true` | Password input resets to `''` after submit resolves. |
| 10 | `test_login_blocks_submit_with_empty_fields` | Empty inputs; click submit | `login` NOT called; `auth.error === 'invalid_credentials'`. |

The countdown-timer `$effect` is NOT exercised in unit tests (timers are flaky in jsdom + Vitest fake-timers + Svelte 5 runes have known interaction edges). The countdown is covered by the `tickRateLimit()` unit tests in §3.4 + browser QA — Decision §7.4.

### 4.2 File: `src/api/frontend/tests/splash.test.js` (~80 LOC, 6 tests)

Spec citation: slice 3g spec §2.4 (BootstrapEmpty + AllDisabled), §7.4 Option C, §7.5 Option B.

Intent: lock the two splash copy blocks + the no-fetch contract (these components must not trigger any network call from their render path).

**Test ordering note.** Each "no fetch" test must install the fetch spy via `vi.spyOn(globalThis, 'fetch')` BEFORE calling `render()`, not after. A spy installed after render misses any fetch fired during component initialisation, which would silently pass a regression. Reflect this in the `beforeEach` shape: spy install in `beforeEach`, render in the test body.

| # | Test name | Component | Assertion |
|---|---|---|---|
| 11 | `test_bootstrap_empty_renders_copy` | `BootstrapEmpty.svelte` | Splash text matches "No operators seeded. …"; no form fields; no submit button. |
| 12 | `test_bootstrap_empty_makes_no_fetch_during_render` | `BootstrapEmpty.svelte` | Fetch spy installed pre-render; after render, spy records zero calls. |
| 13 | `test_bootstrap_empty_role_alert_present` | `BootstrapEmpty.svelte` | Splash region has `role="alert"` or `role="status"` (a11y). |
| 14 | `test_all_disabled_renders_copy` | `AllDisabled.svelte` | Splash text matches "All operators are currently disabled. …"; no form fields. |
| 15 | `test_all_disabled_makes_no_fetch_during_render` | `AllDisabled.svelte` | Fetch spy installed pre-render; zero calls. |
| 16 | `test_all_disabled_distinct_from_bootstrap_empty` | Both | Text content differs (locks "distinct components per state"). |

### 4.3 `Topbar.svelte` logout button — covered by integration test, not a component test

`Topbar.svelte`'s logout button is small (one `<button onclick={logout}>` + a `<span>` for `display_name`). Component-testing it adds little vs. the one-shot click test inside `tests/auth.test.js` (test #20 already mocks `disconnect` and asserts the post-logout state). Decision §7.6 covers whether to add a Topbar component test; recommendation is NO for slice 3g.5.

---

## 5. Integration tests (CSRF threading + mid-session 401 + bootstrap collapse)

### 5.1 File: `src/api/frontend/tests/api.test.js` (~180 LOC, 12 tests)

Spec citation: slice 3g spec §3.3 (CSRF threading), §3.4 (mid-session 401 redirect), §3.5 (helper error shapes) + master spec §4.4 (CSRF defense).

Intent: lock the wire shape of `lib/api.js` — which helpers send `X-CSRF-Token`, which don't, and how 401 / 403 / 5xx are surfaced.

| # | Test name | Helper | Assertion |
|---|---|---|---|
| 1 | `test_post_threads_csrf_when_token_present` | `postJSON('/console/foo', {a:1})` | `auth.csrfToken='tok'`; init has `headers['X-CSRF-Token'] === 'tok'`. |
| 2 | `test_post_omits_csrf_when_token_null` | `postJSON('/console/foo')` | No memory token, no cookie; init has no `X-CSRF-Token`. |
| 3 | `test_post_uses_cookie_fallback_csrf` | `postJSON('/console/foo')` | `auth.csrfToken=null`; cookie `heimdall_csrf=cookie-tok`; init has `X-CSRF-Token === 'cookie-tok'`. |
| 4 | `test_save_settings_threads_csrf` | `saveSettings('foo', {a:1})` | PUT init has `X-CSRF-Token` + `Content-Type: application/json`. |
| 5 | `test_send_command_threads_csrf` | `sendCommand('reload')` | Same as #4 (POST). |
| 6 | `test_fetch_json_does_not_send_csrf` | `fetchDashboard()` | Init has no `X-CSRF-Token` (read methods bypass CSRF). |
| 7 | `test_post_401_calls_handle_session_expired` | `postJSON(...)` returns 401 | Mocked `handleSessionExpired` called once; thrown `error.message === 'Session required — log in to continue.'` |
| 8 | `test_save_settings_401_calls_handle_session_expired` | 401 | Same as #7. |
| 9 | `test_send_command_401_calls_handle_session_expired` | 401 | Same as #7. |
| 10 | `test_fetch_json_401_calls_handle_session_expired` | 401 | Same as #7. |
| 11 | `test_post_403_csrf_mismatch_does_not_logout` | 403 + `{error:'csrf_mismatch'}` | `handleSessionExpired` NOT called; thrown error includes `csrf_mismatch`; `auth.status` unchanged. |
| 12 | `test_post_500_throws_status_error` | 500 + `{detail:'oops'}` | Throws error containing `500` and `oops`; `handleSessionExpired` NOT called. |

### 5.2 File: `src/api/frontend/tests/bootstrap.test.js` (~80 LOC, 3 tests)

Spec citation: slice 3g spec §2.2 + §3.4 (bootstrapInFlight race-mitigation).

Intent: lock the in-flight promise collapse — concurrent callers share one promise, one fetch, one state mutation. This slice asserts the collapse to one fetch round trip per concurrent burst.

Per Decision §7.5 (Option A — required), three tests close this contract:

| # | Test name | Assertion |
|---|---|---|
| 1 | `test_bootstrap_collapses_to_one_fetch_round_trip` | Stub `fetch` with a deferred promise; call `bootstrap()` twice; capture both return values; resolve fetch with `200`; both await; assert (a) `fetch` called exactly once AND (b) both `bootstrap()` callers received the same promise object (`p1 === p2`). |
| 2 | `test_bootstrap_releases_in_flight_after_resolve` | Call `bootstrap()` → resolve → call `bootstrap()` → second call triggers a new fetch. |
| 3 | `test_bootstrap_releases_in_flight_after_throw` | Call `bootstrap()` → fetch rejects → call `bootstrap()` → second call triggers a new fetch (release on failure path too). |

Why required: slice 3g spec §3.4 wires `lib/api.js`'s 401 handler to call `handleSessionExpired()` (which calls `bootstrap()`); without the collapse, a 401 burst across `fetchDashboard` + `fetchCampaigns` (fired concurrently from `App.svelte.initialiseShell()`) would mean two whoami probes racing two state mutations. The pair-of-assertions in test #1 (single fetch + same promise object) prevents a future refactor from quietly recreating the promise per call while keeping the fetch dedupe.

### 5.3 What is NOT integration-tested in 3g.5

- **End-to-end browser flow against a live server.** Out of scope; Playwright / WebDriver territory; would require dev-stack provisioning in CI. Browser-eyeball QA per memory `feedback_test_frontend_in_browser` is the manual ceiling.
- **WebSocket auth from the SPA side.** Handler-level WS auth (slice 3g (d)(e)) is exercised by `tests/test_console_ws_auth.py` (already shipped). SPA's `lib/ws.svelte.js` connect/disconnect is exercised by browser QA only.
- **`App.svelte` `$effect` for WS auto-connect / auto-disconnect on `auth.status` flip.** Slice 3g spec §7.3 Option C wires this `$effect` as the single WS startup/teardown trigger. Browser QA is the floor — Vitest with `@testing-library/svelte` can render App.svelte but reactive-effect ordering against jsdom + the WS module mock is brittle, and adding an App.svelte integration test expands the slice into App-component territory (App is a thin wiring layer; the state-machine logic that drives the effect is unit-tested in §3). The §1 / §8 gate claim narrows accordingly: Vitest covers the auth state machine + SPA login UI; the App.svelte effect is verified by browser-eyeball QA only.

---

## 6. Test-runner integration (Makefile + CI)

### 6.0 Current CI surface (baseline before slice 3g.5)

`.github/workflows/ci.yml` today has exactly one job: `test` (Python). It runs the pytest suite directly as `pytest -m "not integration" --tb=short --timeout=30` against the project's Python `requirements*.txt`. There is **no Node setup, no Vitest step, no `apps/signup/` test invocation** — `apps/signup/`'s 21/21 Vitest tests pass locally on every dev's machine but never run in CI. This is the baseline slice 3g.5 inherits.

What this means for the §7.11 hard-gate: the gate cannot be mechanical against the current CI surface, because there is nothing in CI today that would fail when SPA tests fail. Slice 3g.5 has to land a CI job (§6.2) for the hard-gate to be enforceable — landing only the Makefile target (§6.1) and the test files (§§3–5) leaves "tests must be green before merge" as operator self-attestation. This is the load-bearing observation behind §7.3's escalation to headline blocker (see §7 prose intro).

### 6.1 `Makefile` target — `frontend-test`

New target alongside `signup-test`:

```makefile
.PHONY: frontend-test
frontend-test: ## Run the operator-console-SPA Vitest suite.
	cd src/api/frontend && npm install --prefer-offline && npm run test
```

Lands at the same tier as `signup-test` (line 293-295 of the current Makefile). One line in `make help` output. Decision §7.7 covers whether to also wire it under an aggregate `make js-test` target that runs both `signup-test` and `frontend-test` (recommendation: no — keep targets explicit; an aggregate would obscure failures and is easy to add later).

### 6.2 CI integration — `.github/workflows/ci.yml`

Add a sibling job (or step) that runs `make frontend-test` (and `make signup-test` while we're there — the existing CI does NOT run signup tests today, an oversight that 3g.5 is the right time to fix per Decision §7.3 Option B). Two options for shape, deferred to Decision §7.3:

- **Option A — separate job.** New `frontend` job with its own `actions/setup-node` + npm cache. Cleanest separation; runs in parallel with the Python `test` job.
- **Option B — additional steps in the existing `test` job.** Append `setup-node` + `npm install --prefer-offline` + `npm run test` after the pytest step. Single-job CI; sequential; simpler.

Recommendation: **Option A.** Parallelism + clear failure attribution + separate caching. Same shape as a typical multi-language CI. Slice 3g.5 ships the new job (and adds the signup-test run alongside, so signup test breakage starts gating PRs).

Job draft (for §7.3 review only — not committed yet):

```yaml
  frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: npm
          cache-dependency-path: |
            src/api/frontend/package-lock.json
            apps/signup/package-lock.json
      - name: Install console SPA deps
        run: cd src/api/frontend && npm ci
      - name: Run console SPA tests
        run: cd src/api/frontend && npm run test
      - name: Install signup site deps
        run: cd apps/signup && npm ci
      - name: Run signup site tests
        run: cd apps/signup && npm run test
```

Note: this requires `package-lock.json` to be committed in `src/api/frontend/`. Today's `src/api/frontend/.gitignore` situation needs verification before slice 3g.5 lands; Decision §7.3 covers the lockfile commit policy.

### 6.3 Pre-commit hook integration — out of scope for 3g.5

Adding a pre-commit hook that runs `frontend-test` on SPA changes would mirror the precommit Codex review hook. Decision deferred to Stage A.5 or a dedicated tooling sprint; CI is the floor for 3g.5.

---

## 7. Decisions (locked)

**Status (2026-04-29).** Federico locked all seven decisions §7.1–§7.7. Each subsection's "Recommendation" line is now binding — the prose under each option is the rationale-of-record, not an open deliberation. **§7.3 — the load-bearing one — resolved to Option A + 1**: separate `frontend` CI job parallel to the existing Python `test` job, with `package-lock.json` committed for both `src/api/frontend/` and `apps/signup/`. This makes the §7.11 Option B production-deploy hard-gate mechanical, not advisory; it also retroactively closes the existing CI gap where `apps/signup/` Vitest tests run locally but never gate PRs.

**Locked outcomes (read this table; the subsection prose is the why):**

| § | Topic | Decided 2026-04-29 |
|---|---|---|
| 7.1 | Test file location | Option A — `src/api/frontend/tests/` (mirrors `apps/signup/`) |
| 7.2 | Component test approach | Option A — `@testing-library/svelte` (matches `apps/signup/`) |
| **7.3** | **CI integration shape + lockfile policy** | **Option A + 1 — separate `frontend` job + commit `package-lock.json` for both SPAs. Merge-blocking; §7.11 Option B production-deploy hard-gate is mechanical under this lock.** |
| 7.4 | Countdown-timer testing depth | Option B — `tickRateLimit()` unit tests + browser QA cover the visible decrement; no Vitest fake-timers |
| 7.5 | Bootstrap in-flight collapse test | Option A — required; locks the §2.2 + §3.4 race-mitigation contract |
| 7.6 | Topbar logout component test | Option A — skip (one-line wire over an already-tested state machine) |
| 7.7 | Aggregate `make js-test` target | Option B — skip; keep `make signup-test` and `make frontend-test` explicit |

### 7.1 Test file location

**Question.** Where do the new test files live?

| Option | Description | Trade-offs |
|---|---|---|
| A | `src/api/frontend/tests/*.test.js`. Mirrors `apps/signup/tests/`. | Symmetric with the only other Vitest project in the repo. Easy to find. Vitest's `include: ['tests/**/*.test.js']` matches the apps/signup config verbatim. |
| B | Co-located: `src/api/frontend/src/lib/auth.test.js` next to `auth.svelte.js` etc. | Tests live next to the code they test. Vitest's default `include` glob picks them up. Cost: pollutes source tree with test files; build tooling has to ignore them. |

**Recommendation: Option A.** Symmetry with `apps/signup/` is more valuable than co-location for a six-file test suite. Keeps the Vite build clean (no need to add test-file exclusions to `vite.config.js`). Matches the master-spec convention that all Python tests live in `tests/`.

**Is there a more elegant, simpler way?** Option A IS the simpler way for this scale. Co-location starts paying off above ~50 test files; we have 6.

### 7.2 Component test approach

**Question.** How are `Login.svelte` / `BootstrapEmpty.svelte` / `AllDisabled.svelte` tested?

| Option | Description | Trade-offs |
|---|---|---|
| A | `@testing-library/svelte` `render()` + `screen` + `fireEvent`. Matches `apps/signup/` tooling (already in `apps/signup/package.json`). | Familiar pattern; same dev-deps; rich query API. Slight runtime cost (~200ms per test for jsdom + render). |
| B | Thin shallow render — instantiate the component manually via `mount()` from Svelte's compiled output, query the DOM with `document.querySelector`. | Smaller dep footprint (drop `@testing-library/svelte`). Cost: hand-rolled query helpers; less idiomatic. |

**Recommendation: Option A.** `@testing-library/svelte` is already implied by the dev-dep parity with `apps/signup/`. The library's `screen.getByRole('button', {name: /sign in/i})` is far more readable than `document.querySelectorAll('button').find(...)`, and it forces a11y-aware tests. Adding it costs one dev-dep.

**Is there a more elegant, simpler way?** Option A IS the standard tool; rolling our own would be the cleverness trap.

### 7.3 CI integration shape + lockfile policy — **HEADLINE BLOCKER**

This is the decision the slice 3g.5 spec cannot lock without. See the §7 prose intro for why §7.3 sits above the other six decisions: it determines whether §7.11's production-deploy gate is mechanical (CI fails the PR on red) or advisory (operator self-attestation). The CI baseline today is single-job Python-only — see §6.0 for the surface slice 3g.5 inherits.

**Question (two-part).**

(a) Does `make frontend-test` run in CI as a separate job, as additional steps in the existing `test` job, or not at all (deferred to a follow-up slice)?

(b) Are `src/api/frontend/package-lock.json` and `apps/signup/package-lock.json` committed (required for `npm ci` in CI) or left ignored (CI uses `npm install --prefer-offline`, slower + non-reproducible)?

| (a) Option | Description | Trade-offs | **Gate consequence** |
|---|---|---|---|
| A | New `frontend` job with `actions/setup-node` + npm cache. Runs in parallel with `test`. | Clean failure attribution; parallelism; standard multi-language CI shape. Cost: ~30 LOC of new YAML + a second `actions/setup-node` step. | **Preserves §7.11 hard-gate.** PRs to `main` fail mechanically when SPA tests fail. |
| B | Append `setup-node` + `npm install` + `npm run test` to the existing `test` job (an aggregate `js-test` step inside the Python job). Sequential. | Smaller diff. Cost: failures conflate; pytest passes but Vitest fails reads as "test job red" — operators dig into logs to disambiguate. | **Preserves §7.11 hard-gate.** Mechanically blocks merge on red, just with worse failure attribution. |
| C | Defer the CI job to a follow-up slice. Slice 3g.5 ships only the Makefile target + tests; CI runs Python only. | Minimal slice diff. | **BREAKS §7.11.** Production-deploy gate becomes advisory: operators must remember to run `make frontend-test` locally before merge. No mechanical enforcement. The slice 3g bundle could merge to `main` and push to `prod` with red SPA tests if the operator forgets. **Not acceptable per §7.11 Option B contract.** |

| (b) Option | Description | Trade-offs |
|---|---|---|
| 1 | Commit both `package-lock.json` files. CI uses `npm ci` (deterministic, fail-on-mismatch). | Reproducibility. Auto-renovate / Dependabot can bump lockfiles. Slight diff churn on every dep update. |
| 2 | Don't commit lockfiles. CI uses `npm install --prefer-offline`. | Smaller repo. Cost: non-reproducible installs, no CVE-scan over locked versions. |

**Recommendation: (a) Option A + (b) Option 1.** Separate frontend job for clean attribution; commit both lockfiles for reproducibility. The slice 3g.5 PR commits both new lockfiles + adds the CI job. This also retroactively fixes the existing `apps/signup/` CI gap (signup tests don't run in CI today). Option B is acceptable as a fallback if operator preference is "fewer jobs"; Option C is **not acceptable** without a separate decision to walk back §7.11.

**Is there a more elegant, simpler way?** Not really — multi-language CI has well-trodden shape; the recommendation is the standard.

### 7.4 Countdown-timer testing depth

**Question.** Does `tests/Login.test.js` exercise the `$effect`-driven `setInterval` countdown using Vitest fake timers?

| Option | Description | Trade-offs |
|---|---|---|
| A | Use `vi.useFakeTimers()` + `vi.advanceTimersByTime(1000)` to simulate the countdown ticking; assert the rendered text decrements correctly across multiple ticks. | Full coverage of the `$effect` + `tickRateLimit` interaction. Cost: fake-timers + Svelte 5 runes + `@testing-library/svelte` reactivity have known interaction edges (effect re-fires not always flushing under fake timers); test flakiness risk. |
| B | Cover `tickRateLimit()` logic in `tests/auth.test.js` (state-machine) + cover the rendered countdown number once (snapshot at `auth.retryAfter=42`); leave the actual decrement-over-time path to browser QA. | Less coverage on paper. In practice the state machine + the rendered number are the load-bearing parts; the visual decrement is what eyeball QA catches. Lower flake risk. |

**Recommendation: Option B.** Fake-timers + reactive effects are a known flake hazard in this stack, and the coverage gain is small — `tickRateLimit()` is unit-tested, the rendered number is component-tested, and the decrement is operator-eyeball QA. Option A is more code for less reliable tests.

**Is there a more elegant, simpler way?** Option B's "split the responsibility cleanly" IS the elegant way; mixing fake-timers into a component test is the clever-but-fragile path.

### 7.5 Bootstrap in-flight collapse test

**Question.** Is the `bootstrapInFlight` collapse a load-bearing contract that must be tested, or an implementation detail that can change?

| Option | Description | Trade-offs |
|---|---|---|
| A | **Required.** `tests/bootstrap.test.js` ships with three tests locking the collapse contract. Any future refactor that removes the collapse fails CI. | Locks the spec §2.2 + §3.4 race-mitigation contract. Cost: ~80 LOC of test code + a tiny constraint on future refactors. |
| B | **Nice-to-have.** Skip the dedicated test file; rely on browser QA + the existing `bootstrap()` 401 test in `auth.test.js` to catch regressions. | Less code. Cost: the 401-burst race is exactly the kind of bug that doesn't fire in eyeball QA but fires in production (pubsub event flood after a session expiry). |

**Recommendation: Option A — required.** The collapse is the entire reason the module-level `bootstrapInFlight` promise exists (per `auth.svelte.js:34-37`). Without a test locking it, a future "simplify the auth module" refactor could quietly remove the guard and reintroduce the race; the 401 burst from `App.svelte.initialiseShell()`'s concurrent `fetchDashboard` + `fetchCampaigns` calls would then produce two whoami probes racing two state mutations. This is exactly the kind of contract that needs a regression lock.

**Is there a more elegant, simpler way?** No — three small tests around a load-bearing contract is the elegant shape. Skipping them is the false economy.

### 7.6 Topbar logout component test

**Question.** Does `Topbar.svelte`'s logout button get its own component test?

| Option | Description | Trade-offs |
|---|---|---|
| A | NO — covered by `tests/auth.test.js` test #20 (`logout()` calls `disconnect`, resets state, fires fetch with CSRF header). The Topbar's role is just to wire a click to `logout()`; testing that wire is one assertion away from useless. | Smaller test surface. The "click → handler" wiring is browser-QA territory. |
| B | YES — `tests/Topbar.test.js` (new file, ~30 LOC) renders Topbar, clicks the logout button, asserts `logout()` was called once. | Symmetry with Login component test. Cost: a third component test file for a one-line component edit. |

**Recommendation: Option A.** The Topbar logout button is a four-line wire (`onclick={logout}`) over a state machine that is already heavily tested. A dedicated test file is symmetry-for-symmetry's sake. If a future Topbar change adds logic worth testing, the file appears then.

**Is there a more elegant, simpler way?** Option A IS the simpler way; resist the symmetry instinct.

### 7.7 Aggregate `make js-test` target

**Question.** Add `make js-test` that runs both `signup-test` and `frontend-test`?

| Option | Description | Trade-offs |
|---|---|---|
| A | Add it. `make js-test` becomes the one-command "run all JS tests" entry point. | Convenience. |
| B | Skip it. `make signup-test && make frontend-test` is a two-target compose at the developer's call site; `Makefile` stays minimal. | Smaller diff. |

**Recommendation: Option B.** Two named targets are clearer than one aggregate target. Adding the aggregate later is one line; removing it once added is harder (some user workflow has caught it). Keep targets explicit until a real workflow demands the aggregate.

**Is there a more elegant, simpler way?** Option B IS the simpler way.

---

## 8. Out of scope

Each item below is explicitly NOT in slice 3g.5.

| Item | Lands in | Notes |
|---|---|---|
| End-to-end browser flow against a live server | Future Playwright sprint (not scheduled) | Requires CI dev-stack provisioning; out of frontend-tooling scope. |
| WebSocket auth from the SPA side (`lib/ws.svelte.js`) | Browser QA + the Python `tests/test_console_ws_auth.py` (already shipped in slice 3g commit `f3f95da`) | jsdom + reactive-effect coupling + WS mock plumbing is brittle; browser QA is the right floor. |
| `App.svelte` `$effect` for WS auto-connect/disconnect on `auth.status` flip | Browser QA | This `$effect` is the single WS startup/teardown trigger (slice 3g spec §7.3 Option C). Excluding it narrows the §1 gate claim to "Vitest covers the auth state machine and SPA login UI; the App.svelte WS effect is browser-QA only." Reactive-effect ordering against jsdom + the WS module mock is brittle, and adding an App.svelte integration test expands scope into App-component territory without a proportional safety gain — the state-machine logic that drives the effect is unit-tested in §3, so the failure modes the test would catch are already locked. |
| `connect()` / `disconnect()` happy-path coverage | Browser QA | The mock in `tests/auth.test.js` test #18 asserts `disconnect` is called; the actual WS lifecycle is browser territory. |
| Vitest fake-timer coverage of the rate-limit countdown | Browser QA + the unit tests for `tickRateLimit()` | Per Decision §7.4 Option B. |
| Topbar logout component test | Future if Topbar gains real logic | Per Decision §7.6 Option A. |
| Aggregate `make js-test` target | Future if a workflow demands it | Per Decision §7.7 Option B. |
| Coverage gate (e.g. fail CI under N% line coverage) | Stage A.5 or later | Setting a gate now would inflate scope; Vitest's default coverage reporter is enough for visibility without enforcement. |
| Visual regression (Percy / Chromatic) | Future visual-QA sprint | Not currently using any visual-regression tool; introducing one is a separate decision. |
| Pre-commit hook running `frontend-test` | Stage A.5 or later | Mirrors precommit-Codex pattern; needs a separate decision. |
| SPA Vitest tests for the existing read-only views (Dashboard / Pipeline / Campaigns / etc.) | Future | Slice 3g.5 only covers the auth-flow surface; existing views are browser-QA-only. |

---

## 9. Rollback plan

Slice 3g.5 is purely additive — new dev-deps + new test files + a new Makefile target + a new CI job. No production-runtime code changes, so the production-runtime risk of revert is zero. The hard-gate guarantee from §7.11 Option B, however, IS at risk under partial revert; see §9.2.

### 9.1 Lever 1 — full `git revert`

`git revert <slice-3g-5-merge-sha>` on `feat/stage-a-foundation`. Removes the harness configs, test files, Makefile target, CI job. The slice 3g bundle regresses to "no SPA test floor" — which is exactly slice 3g's pre-3g.5 posture. The §7.11 production-deploy gate then re-engages: slice 3g cannot merge to `main` / push to `prod` until 3g.5 (or its replacement) is re-attempted.

**No production-runtime risk** (zero runtime code changed). Note: this is NOT a "no-risk revert" — the §7.11 hard-gate guarantee is forfeited until the slice is re-attempted, which is itself a risk to the slice 3g delivery timeline. The runtime is safe; the gate is not.

### 9.2 Lever 2 — partial revert (CI-only)

If only the CI integration breaks (e.g. npm install timeout, ci runner image issue), revert just the `.github/workflows/ci.yml` edit + the Makefile target:

1. `git revert -n <slice-3g-5-sha>` (no commit).
2. `git checkout HEAD -- src/api/frontend/tests/ src/api/frontend/vitest.config.js src/api/frontend/package.json` (keep tests + harness).
3. Commit the CI-only revert.
4. Tests still run locally (`make frontend-test`) but don't gate CI.

**Trade-off — the gate degrades.** Under this lever, slice 3g.5 lands but the §7.11 hard-gate is no longer mechanical: tests must pass locally before merge (operator self-attestation), not in CI. This means landing 3g.5 does NOT, by itself, guarantee the hard-gate — the gate's mechanical-ness depends on the CI job being live. Acceptable as a temporary posture during a CI hiccup; not acceptable as a permanent state. If the CI integration cannot be restored within the slice's review window, the right posture is full revert (§9.1) rather than landing a degraded gate.

### 9.3 Lever 3 — full Stage A revert

Per the Stage A master spec §9.3 pattern. Slice 3g.5 is in the full-revert chain.

---

## 10. Appendix A — file map

Files added in slice 3g.5:

```
docs/architecture/stage-a-slice-3g-5-spec.md           # this file
src/api/frontend/vitest.config.js                      # ~20 LOC — Vitest harness config (mirrors apps/signup/)
src/api/frontend/tests/auth.test.js                    # ~250 LOC — state-machine unit tests (32 tests per §3 — incl. one runes-in-jsdom smoke test from §2.6)
src/api/frontend/tests/Login.test.js                   # ~150 LOC — Login.svelte component tests (~10 tests per §4.1)
src/api/frontend/tests/splash.test.js                  # ~80 LOC — BootstrapEmpty + AllDisabled (~6 tests per §4.2)
src/api/frontend/tests/api.test.js                     # ~180 LOC — CSRF threading + 401 redirect (~12 tests per §5.1)
src/api/frontend/tests/bootstrap.test.js               # ~80 LOC — bootstrap in-flight collapse (~3 tests per §5.2)
src/api/frontend/package-lock.json                     # generated by npm install (commit per Decision §7.3)
apps/signup/package-lock.json                          # commit per Decision §7.3 if not already tracked
```

Files modified in slice 3g.5:

```
src/api/frontend/package.json                          # +5 LOC — three dev-deps + "test" script
Makefile                                               # +5 LOC — frontend-test target
.github/workflows/ci.yml                               # +20 LOC — new frontend job (+ retro signup-test)
docs/decisions/log.md                                  # +1 entry — slice 3g.5 locked scope
```

Files DELETED in slice 3g.5:

```
(none)
```

Estimated diff (additive only — no production runtime code changes):

| Bucket | Files | LOC |
|---|---|---|
| Implementation LOC | `vitest.config.js`, `tests/auth.test.js`, `tests/Login.test.js`, `tests/splash.test.js`, `tests/api.test.js`, `tests/bootstrap.test.js`, `package.json` (+5), `Makefile` (+5), `.github/workflows/ci.yml` (+20) | ~810 |
| Spec / docs LOC | `docs/architecture/stage-a-slice-3g-5-spec.md` (this file), `docs/decisions/log.md` (+1 entry) | ~700 |
| Generated lockfiles | `src/api/frontend/package-lock.json`, `apps/signup/package-lock.json` | several thousand (npm-generated; not hand-written, not reviewed line-by-line) |

Total reviewable diff (implementation + spec) ≈ 1480 LOC; the lockfiles bring the apparent diff much higher but should be reviewed as "generated, hash-checked" rather than as code. Runtime SPA code is unchanged.

---

## 11. Appendix B — affected master-spec sections

| Master spec section | Slice 3g.5 touches |
|---|---|
| §3.1 (login flow) | Read; Vitest tests assert SPA conformance to the wire contract. |
| §3.4 (mid-session 401 handling) | Read; tested in `tests/api.test.js` (CSRF + 401 redirect). |
| §3.5 (whoami split states) | Read; tested in `tests/auth.test.js` (six bootstrap branches). |
| §4.1 (cookie names + attributes) | Read; `getCsrfToken()` cookie-fallback test asserts `heimdall_csrf` parsing. |
| §4.4 (CSRF defense) | Read; `tests/api.test.js` asserts `X-CSRF-Token` is on mutating helpers and absent on read helpers. |
| §6.3 (auth router response shapes) | Read; `tests/auth.test.js` asserts the SPA consumes the locked shapes. |
| §8 (test plan) | Extended; the master-spec test plan covers backend; 3g.5 covers the SPA side. |
| §11 (out of scope) | One row resolved (the "SPA Vitest harness" out-of-scope row from slice 3g spec §11). No new master-spec out-of-scope items advanced. |

| Slice 3g spec section | Slice 3g.5 touches |
|---|---|
| §2.1 (state machine table) | All four whoami branches covered in `tests/auth.test.js`. |
| §2.2 (auth.svelte.js shape) | `bootstrapInFlight` collapse locked in `tests/bootstrap.test.js`. |
| §2.3 (Login.svelte UI states) | All five UI states covered in `tests/Login.test.js`. |
| §2.4 (BootstrapEmpty + AllDisabled) | Both splashes covered in `tests/splash.test.js`. |
| §2.5 (App.svelte rewrite) | Covered by browser QA only (per §8 "out of scope"). |
| §2.6 (Topbar logout) | Covered by `tests/auth.test.js` test #18; no dedicated component test (per Decision §7.6). |
| §3.1–§3.5 (CSRF helper) | Threading + cookie-fallback + 403/401 paths all covered in `tests/api.test.js`. |
| §7.1 (login form placement) | N/A — placement decision was for slice 3g, 3g.5 just tests what exists. |
| §7.2 (CSRF token storage) | Cookie-fallback test in `tests/auth.test.js` locks the Option C contract. |
| §7.3 (WS reconnect timing) | NOT covered in 3g.5 (browser QA only — per §8). |
| §7.6 (mid-session 401 UX) | Redirect-to-login covered in `tests/api.test.js` (`handleSessionExpired` mock asserted). |
| §7.10 (legacy retirement) | N/A — legacy already removed in slice 3g (f). |
| §7.11 (SPA-test hard-gate) | This slice IS the gate; landing it green clears the gate. |

---

## 12. Revision history

| Date | Change |
|---|---|
| 2026-04-28 | Initial draft. **DRAFT** status; seven open questions for Federico (§7.1–§7.7). Locks the slice 3g.5 production-deploy gate per parent slice 3g spec §7.11 Option B. |
| 2026-04-28 (post-Codex) | Codex pre-lock review. Edits applied: (1) §3.3 expanded to seven login branches incl. `http_500` + `malformed_response`; §3.4 added logout-503 test; §3.4 renumbered to start at #20 to make room for the §3.3 additions. (2) §4.2 splash "no-fetch" tests reworded to install spy BEFORE render; §5.2 bootstrap-collapse test #1 tightened to "one fetch round trip" + added second assertion that both callers receive the same promise object. (3) §2.6 reworded as implementation assumption to verify in first slice 3g.5 PR (rune modules in Vitest is unproven by `apps/signup/` precedent); added smoke-test mitigation. (4) §7.3 escalated to **headline blocker** — added load-bearing prose intro, gate-blocking column to lock-at-a-glance table, gate-consequence column to §7.3 options, Option C (defer) call-out as not-acceptable; added §6.0 "current CI surface" baseline. (5) §1 / §8 narrowed gate claim — App.svelte WS effect explicitly out-of-scope-but-browser-QA-covered; footnote added to §1 component (g) noting it's necessary-not-sufficient. (6) §9 reworded "no-risk revert" → "no production-runtime risk" + clarified gate degrades under partial revert (lever 2). (7) §10 LOC estimate split into implementation / spec / generated-lockfile buckets. (8) §3 / §4 / §5 trimmed per spec discipline — citation + intent + assertions; removed source-restating prose. |
| 2026-04-29 | Two minor editorial fixes from second Codex pass: (1) §6.0 corrected `make test` → actual command `pytest -m "not integration" --tb=short --timeout=30`; (2) §1 row (b) coverage list expanded to match §3.3's seven `login()` branches (added `http_500` + `malformed_response`) and §3.4's four `logout()` branches. |
| 2026-04-29 | **LOCKED.** Federico locked all seven §7 decisions per the recommendations. §7.3 → Option A + 1 (separate `frontend` CI job + lockfiles committed); §7.11 Option B production-deploy hard-gate is mechanical under this lock. Other six locked at recommended option. Slice 3g.5 implementation unblocked. |

---

**End of slice 3g.5 spec — LOCKED.**
