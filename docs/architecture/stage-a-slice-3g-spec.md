# Stage A Slice 3g — SPA login + CSRF + handler-level WS auth — Implementation Spec

**Status:** **LOCKED** — §7.1–§7.11 all decided 2026-04-28 (review pass added §7.10 legacy retirement + §7.11 SPA-test hard-gate). Slice 3g implementation is unblocked.
**Sprint:** Stage A (final auth-plane slice on `feat/stage-a-foundation`). Slice 3g.5 (SPA test harness + auth-flow Vitest tests) is the gating slice between 3g implementation and production deploy.
**Author:** Application Architect agent, 2026-04-28 (post-3f wrap-up); §7.10/§7.11 added 2026-04-28 evening per Federico's review.
**Master spec:** `docs/architecture/stage-a-implementation-spec.md` — cite by section number; never restate contracts here.
**Locks scope from:** `docs/decisions/log.md` 2026-04-28 entry "Stage A slice 3f: SessionAuthMiddleware default mount, `/app` protection preserved" (Unresolved → Next slice scope).

> Slice 3g is **atomic.** None of the five components (a–e) ships without all five. Slice 3f intentionally left `/console/ws` open at the handler layer because `/app/*` was still gated; this slice closes the WS surface and ships the SPA login flow that operators need to actually use the cookie-protected `/app/`. A partial ship would leave a known data-leak window or a UI that can never log in.
> 
> **The `/app` protection is already in place** on the slice 3f baseline (`src/api/auth/middleware.py:97` reads `("/console", "/app")`); slice 3g does NOT need a middleware revert. See §6 for the verification step.

---

## Summary

Slice 3g is the SPA-side completion of Stage A's auth plane. Slices 2 / 3a–3f built every server-side primitive (Argon2id, session ticket, audit writer, rate limiter, ASGI middleware, `/console/auth/{login,logout,whoami}` router, `SessionAuthMiddleware` mounted by default, `/app/*` retained in the protected prefix). Slice 3f could not also ship the SPA because:

1. The SPA had no login form — operators reaching `/app/` after 3f get a static 401 from the middleware with no path forward in default mode.
2. `/console/ws` (`src/api/console.py:811-870`) still does `await websocket.accept()` immediately with no cookie inspection, so anyone who can reach the SPA shell can also `new WebSocket('/console/ws')` and stream live operator pubsub events.
3. SPA mutations (`saveSettings`, `sendCommand`, retention actions) do not send `X-CSRF-Token`, so they would 403 against the middleware's CSRF gate.

Slice 3g lands the SPA login form + whoami bootstrap state machine + CSRF helper threaded through all mutating fetches + handler-level WS auth on `/console/ws` and `/console/demo/ws/{scan_id}` + the test file (`tests/test_console_ws_auth.py`) covering the seven cases from master spec §8.2. After 3g ships, the auth plane is feature-complete; Stage A.5 (Permission enum, `require_permission`, `config_changes` triggers) is the next sprint.

---

## Table of contents

1. [Locked scope (atomic)](#1-locked-scope-atomic)
2. [SPA login + whoami bootstrap (a + b)](#2-spa-login--whoami-bootstrap-a--b)
3. [CSRF helper (c)](#3-csrf-helper-c)
4. [Handler-level WS auth (d)](#4-handler-level-ws-auth-d)
5. [Test plan (e)](#5-test-plan-e)
6. [`/app` protection revert](#6-app-protection-revert)
7. [Decisions (locked)](#7-decisions-locked)
8. [Out of scope](#8-out-of-scope)
9. [Rollback plan](#9-rollback-plan)
10. [Appendix A — file map](#10-appendix-a--file-map)
11. [Appendix B — affected master-spec sections](#11-appendix-b--affected-master-spec-sections)
12. [Revision history](#12-revision-history)

---

## 1. Locked scope (atomic)

The six components below ship in one commit. Each refers to a master-spec section by number and inherits its contract.

| ID | Component | Master-spec ref | Lands in |
|---|---|---|---|
| (a) | SPA login view wired to `POST /console/auth/login` (cookie-aware fetch). On 200 stores `csrf_token` in centralised app state; 401 surfaces `invalid_credentials`; 429 surfaces `Retry-After` countdown. | §3.1, §6.3 (login response shapes) | `src/api/frontend/src/views/Login.svelte` (new) + `src/api/frontend/src/App.svelte` (state-machine wiring) |
| (b) | `GET /console/auth/whoami` bootstrap probe on app mount that drives the 200 / 401 / 204 / 409 state machine into the right UI branch. | §3.5, §6.3 (whoami response shapes) | `src/api/frontend/src/App.svelte` + `src/api/frontend/src/lib/auth.svelte.js` (new) |
| (c) | `X-CSRF-Token` header helper threaded through every state-changing fetch: `postJSON`, `saveSettings`, `sendCommand`, `forceRunRetentionJob`, `cancelRetentionJob`, `retryRetentionJob`. Read methods (`fetchJSON`) skip CSRF — the middleware's check is method-gated (§4.4). | §4.4 (CSRF defense) | `src/api/frontend/src/lib/api.js` (centralised state in new `lib/auth.svelte.js`) |
| (d) | Handler-level WS auth in both `/console/ws` and `/console/demo/ws/{scan_id}`: read `ws.cookies['heimdall_session']` → SHA-256 → `validate_session_by_hash` → `ws.accept()` then `ws.close(code=4401)` BEFORE any pubsub setup on miss; on hit, `ws.accept()` + `liveops.ws_connected` audit row + normal stream. | §5.2 (Option 2), §5.3 (handler entry contract), §5.5 (demo WS), §5.7 (close codes), §5.8 (per-WS audit row) | `src/api/console.py:811-870` (the `/console/ws` block) + `src/api/console.py:983-1027` (`/console/demo/ws/{scan_id}`) |
| (e) | New `tests/test_console_ws_auth.py` covering all 7 cases from §8.2 + the middleware-bypass-on-WS-scope assertion. | §8.2 (`test_console_ws_auth.py` block) | `tests/test_console_ws_auth.py` (new) |
| (f) | **Retire legacy auth path** per §7.10: delete `LegacyBasicAuthMiddleware` class from `src/api/app.py`, remove the `HEIMDALL_LEGACY_BASIC_AUTH` env-flip branch in `create_app`, simplify the auth-router include logic to unconditional. Delete the three branch-mount tests (`test_legacy_flag_with_creds_mounts_legacy`, `test_legacy_flag_without_creds_falls_back_to_session`, and possibly inline `test_default_branch_mounts_session_auth`) from `tests/test_session_auth.py`. Remove the `LegacyBasicAuthMiddleware` import from that file. | §9.1 (Stage A spec rollback runbook — needs a one-line update noting legacy retired) | `src/api/app.py` (-60 LOC), `tests/test_session_auth.py` (-50 LOC), and a one-line edit to master spec §9.1. |

**Note on `/app` protection:** verified during draft — the constant is already `("/console", "/app")` on the committed slice 3f baseline (no revert needed). `tests/test_session_auth.py::test_app_prefix_protected` already asserts 401 on `/app/`. See §6 for the verification step.

**Why atomic.** SPA login form depends on WS not leaking (otherwise unauthenticated browsers loading the SPA shell can stream operator pubsub regardless of UI state). WS handler auth depends on SPA presenting cookies (otherwise legitimate operators can't connect). CSRF helper depends on login (otherwise SPA mutations 403 on every action). Whoami bootstrap depends on the login view existing (otherwise the 401 branch has no UI to render). The legacy retirement (f) ships in the same commit because keeping the env-flip lever past 3g would mean shipping a SPA that breaks under the rollback flag (per the §7.10 deliberation); retiring legacy and landing the new SPA login flow in one commit ensures the rollback story is honest. These five mutually load-bearing requirements fold into one commit; the test file (e) is the proof harness.

**Production-deploy gate (§7.11).** Slice 3g implementation merges to `feat/stage-a-foundation`. The bundle does NOT merge to `main` or push to `prod` until slice 3g.5 (SPA Vitest test harness + auth-flow tests) lands and is green. Rationale: a new auth-critical frontend state machine without automated coverage is too thin a test floor for a control-plane cutover; `src/api/frontend/` has no Vitest harness today, and setting one up would balloon slice 3g into a frontend-tooling slice. The 3g.5 slice (out of scope for this spec — see §11) ships the harness + tests; only after it lands does the deploy proceed.

---

## 2. SPA login + whoami bootstrap (a + b)

### 2.1 State machine

App mount runs `GET /console/auth/whoami` BEFORE rendering any view. The four wire states (master spec §3.5) map to four UI branches:

| whoami state | Status | UI branch | What renders |
|---|---|---|---|
| State 1 — empty bootstrap | 204 | `BootstrapEmpty` | "No operators seeded — talk to your admin" splash. Read-only. No login form. |
| State 2 — all operators disabled | 409 | `AllDisabled` | "All operators disabled — contact owner / re-enable per runbook §9.2" splash. |
| State 3 — authenticated | 200 | `App` (current default) | Existing dashboard / sidebar / topbar / view router. `csrf_token` from response body stored in app state. |
| State 4 — unauthenticated | 401 | `Login` view | Login form. On successful submit transitions to state 3. |

The SPA must NOT call `connect()` (WebSocket) until state 3 has been reached and the session cookie is present. This is enforced by gating the existing `onMount` in `src/api/frontend/src/App.svelte` on `auth.status === 'authenticated'`.

### 2.2 New module: `src/api/frontend/src/lib/auth.svelte.js`

Centralised authentication state and helpers. New file. Approximate shape (Svelte 5 runes; mirrors the pattern in `lib/theme.svelte.js` and `lib/ws.svelte.js`):

```js
// $state runes hold the live values; exported helpers are the only
// writers. Components read `auth.status`, `auth.operator`, `auth.error`.
export const auth = $state({
  status: 'loading',          // 'loading' | 'unauthenticated' | 'authenticated' | 'bootstrap-empty' | 'all-disabled' | 'rate-limited'
  operator: null,             // {id, username, display_name, role_hint} on success
  csrfToken: null,            // string on success; null otherwise
  retryAfter: 0,              // seconds; non-zero only when status === 'rate-limited'
  error: null,                // last user-facing error string ('invalid_credentials' | 'service_unavailable' | …)
});

export async function bootstrap() { /* GET /console/auth/whoami → set status */ }
export async function login(username, password) { /* POST /console/auth/login → set status + csrfToken */ }
export async function logout() { /* POST /console/auth/logout → reset state */ }
export function getCsrfToken() { return auth.csrfToken; }    // for lib/api.js to read
```

`bootstrap()` is called from `App.svelte`'s `onMount` BEFORE any other fetch. It maps 200 / 204 / 409 / 401 to the corresponding `auth.status` value.

`login()` posts the credentials, captures `csrf_token` from the 200 body, and transitions `auth.status` to `'authenticated'`. The 429 branch sets `auth.retryAfter` from the `Retry-After` header and `auth.status = 'rate-limited'`; the login view shows a countdown that returns to the form when it hits 0.

`logout()` posts to `/console/auth/logout` (CSRF-token threaded automatically through `lib/api.js`), then resets `auth.status` to `'unauthenticated'` regardless of response status (the cookie is server-cleared on 204; even on 401 we want the local UI to reset).

### 2.3 New view: `src/api/frontend/src/views/Login.svelte`

Two text inputs (username + password), one submit button, error region for the failure paths. Mounted by `App.svelte` when `auth.status === 'unauthenticated'`. On submit, calls `login()` from `lib/auth.svelte.js`. UI states:

- Idle → `auth.status === 'unauthenticated'`. Form active.
- Submitting → button disabled, spinner.
- Failed (401) → form re-enabled, error region shows "Invalid username or password." (mapped from `invalid_credentials`).
- Rate-limited (429) → form disabled, message shows "Too many failed attempts. Try again in N seconds." with a 1s `setInterval` decrementing `auth.retryAfter`. When it hits 0, form re-enables; `auth.status` returns to `'unauthenticated'`.
- Service unavailable (503) → form re-enabled, error region shows "Server unavailable. Please try again."

Open question §7.1: whether this is a standalone hash route (`#/login`), an inline modal, or a separate component mounted by App.svelte's whoami state machine. The locked scope description above assumes the third option; final placement is for Federico to decide.

### 2.4 Bootstrap splash views

Two more new files for the dead-end states:

- `src/api/frontend/src/views/BootstrapEmpty.svelte` — splash for `auth.status === 'bootstrap-empty'`. Static copy: "No operators seeded. Run the seed step per runbook §2.2 or contact your administrator." Open question §7.4: whether to link to the runbook explicitly.
- `src/api/frontend/src/views/AllDisabled.svelte` — splash for `auth.status === 'all-disabled'`. Static copy: "All operators are currently disabled. Contact the owner to re-enable per runbook §9.2." Open question §7.5: whether copy emphasises the distinction from State 1.

### 2.5 `App.svelte` rewrite

The current `App.svelte` (`src/api/frontend/src/App.svelte:22-32`) calls `connect()`, `fetchDashboard()`, and `fetchCampaigns()` unconditionally on mount. After 3g, the mount runs `bootstrap()` first and gates the rest of the lifecycle on `auth.status`:

```
onMount async:
  await auth.bootstrap()
  if auth.status === 'authenticated':
    connect()
    fetchDashboard().then(...)
    fetchCampaigns().then(...)
    return () => disconnect()
  else:
    // BootstrapEmpty / AllDisabled / Login render via the {#if} chain
    return () => {}
```

The view-switching `{#if router.view === 'dashboard'}` block is wrapped in an outer `{#if auth.status === 'authenticated'}` so the existing dashboard/sidebar/etc. only render in state 3. The four new branches each render their own component.

A successful `login()` transitions `auth.status` to `'authenticated'`; the outer `{#if}` flips and the existing dashboard appears. WebSocket reconnect on this transition is open question §7.3 — current proposal is auto-reconnect (call `connect()` from inside `login()` after `auth.status` is set).

### 2.6 `Topbar.svelte` — logout button

Add a logout button to the right side of `src/api/frontend/src/components/Topbar.svelte` next to the existing `ThemeToggle`. Click handler calls `auth.logout()` from `lib/auth.svelte.js`. Optional: small "logged in as `display_name`" label. Final styling for Federico to spec; minimal viable shape is a button that says "Log out" and a span showing `auth.operator.display_name`.

---

## 3. CSRF helper (c)

### 3.1 Threading model

The CSRF token is a per-session value (master spec §4.4): server generates it at login, returns it in the 200 body, and stores it as the non-`HttpOnly` `heimdall_csrf` companion cookie. The SPA must read it and echo it back as `X-CSRF-Token` on every state-changing request (POST / PUT / PATCH / DELETE). Safe methods (GET / HEAD / OPTIONS) skip the header — the middleware's CSRF check is method-gated (§4.4 step 2).

### 3.2 Source of truth for the token

Master spec §4.1 says the SPA can read it either from the `heimdall_csrf` cookie (via `document.cookie`) or from the login response body. Slice 3g's API helper reads from the centralised app state (`auth.csrfToken` on `lib/auth.svelte.js`) which is populated from the login 200 body and also refreshed from the whoami 200 body. The cookie path is a fallback only — if `auth.csrfToken` is null but `document.cookie` has `heimdall_csrf=<v>`, the helper hydrates `auth.csrfToken` from the cookie before sending. This survives a hard page refresh that loses in-memory state but keeps the cookie. Open question §7.2 covers whether to also persist `auth.csrfToken` to `sessionStorage` for refresh-survivability without round-tripping through the cookie.

### 3.3 `lib/api.js` edits

Current shape (`src/api/frontend/src/lib/api.js:24-49`):

```js
async function postJSON(url, body = null) {
  const init = { method: 'POST', credentials: 'same-origin' };
  ...
}
```

After 3g, every state-changing helper threads `X-CSRF-Token` automatically:

```js
function csrfHeaders() {
  const token = getCsrfToken();              // from lib/auth.svelte.js
  return token ? { 'X-CSRF-Token': token } : {};
}

async function postJSON(url, body = null) {
  const init = {
    method: 'POST',
    credentials: 'same-origin',
    headers: { ...csrfHeaders() },
  };
  if (body !== null && body !== undefined) {
    init.headers['Content-Type'] = 'application/json';
    init.body = JSON.stringify(body);
  }
  ...
}
```

Same shape applied to `saveSettings` (PUT) and `sendCommand` (POST). The three retention helpers (`forceRunRetentionJob`, `cancelRetentionJob`, `retryRetentionJob`) already go through `postJSON`, so they inherit the header automatically. `fetchJSON` and the read-only `fetchDashboard` / `fetchCampaigns` / `fetchClients` / `fetchBriefs` / `fetchLogs` / `fetchSettings` / `fetchPipelineLast` / `fetchProspects` / `fetchTrialExpiring` / `fetchRetentionQueue` are unchanged.

### 3.4 Mid-session 401

A 401 response from any `/console/*` endpoint after the SPA has loaded means the session expired (idle TTL hit, absolute TTL hit, or operator was disabled mid-session). Slice 3f's loop-break edits already throw `SESSION_REQUIRED_MESSAGE` from `fetchJSON` / `postJSON` on 401. Slice 3g extends this: the 401 handler also calls `auth.bootstrap()` to re-probe whoami, which transitions `auth.status` back to `'unauthenticated'` (or `'all-disabled'` if the operator was just disabled), and the App.svelte outer `{#if}` re-renders the login form. Open question §7.6 covers UX for this re-auth flow.

### 3.5 403 csrf_mismatch

A 403 response with body `{"error": "csrf_mismatch"}` means the session is intact but the CSRF token didn't match. This is a SPA bug, not a session expiry. Slice 3g surfaces this as a non-fatal error toast (the session stays alive, no logout). Pragmatically this should never happen in production; the test for it lives in `tests/test_auth_csrf.py` already.

---

## 4. Handler-level WS auth (d)

### 4.1 Current state — what slice 3g changes

`src/api/console.py:811-933` (the `/console/ws` block). Today's entry pattern (line 813-815):

```python
@router.websocket("/ws")
async def console_ws(websocket: WebSocket):
    """WebSocket for live console updates — queue polling + Redis pub/sub forwarding."""
    await websocket.accept()
    redis_conn = getattr(websocket.app.state, "redis", None)
```

This is the data-leak surface called out in slice 3f's decision-log (`docs/decisions/log.md:1787` "src/api/console.py:811-814 is the data-leak surface this commit does NOT close"). Slice 3g rewrites the entry per master spec §5.3.

### 4.2 New entry contract — `/console/ws`

Per master spec §5.3 (Option 2, chosen path):

```python
@router.websocket("/ws")
async def console_ws(websocket: WebSocket) -> None:
    """WebSocket for live console updates — handler-level cookie auth."""
    cookie_value = websocket.cookies.get(SESSION_COOKIE)
    if not cookie_value:
        await websocket.accept()
        await websocket.close(code=4401)
        return

    presented_hash = hashlib.sha256(cookie_value.encode("utf-8")).hexdigest()
    console_db_path = getattr(
        websocket.app.state, "console_db_path", DEFAULT_CONSOLE_DB_PATH
    )
    conn = await asyncio.to_thread(get_console_conn, console_db_path)
    try:
        session_row = await asyncio.to_thread(
            validate_session_by_hash, conn, presented_hash
        )
        if session_row is None:
            await websocket.accept()
            await websocket.close(code=4401)
            return

        await websocket.accept()

        # Per §5.8: write the per-WS audit row inside the same
        # connection that authorized the connection. Same DB, no
        # cross-DB atomicity question.
        with conn:
            write_console_audit_row(
                conn,
                _build_pseudo_request(websocket),
                action="liveops.ws_connected",
                target_type="websocket",
                target_id=None,
                payload={"path": "/console/ws"},
                operator_id=session_row["operator_id"],
                session_id=session_row["id"],
            )
    finally:
        conn.close()

    redis_conn = getattr(websocket.app.state, "redis", None)
    # … existing pubsub task setup, ping/pong loop, command dispatch …
```

Several mechanical points:

- **Cookie before accept.** The cookie SELECT and SHA-256 hash and DB lookup all happen BEFORE `websocket.accept()`. On miss, we accept-then-close so the client sees a clean WS-protocol close with code 4401 rather than an HTTP-level connection refusal. This matches RFC 6455's requirement that you accept before you can close cleanly.
- **`asyncio.to_thread` wrappers.** SQLite is sync; the existing handler already uses `asyncio.to_thread` for `pipe.execute` etc. The same pattern applies to `get_console_conn` and `validate_session_by_hash`.
- **`SESSION_COOKIE` import.** Reuse the constant from `src/api/auth/middleware.py` (`SESSION_COOKIE = "heimdall_session"`). Avoids hard-coding the cookie name in two files.
- **`DEFAULT_CONSOLE_DB_PATH` import** from `src/db/console_connection.py`. Same fallback the auth router uses (`src/api/routers/auth.py:101`).
- **`_build_pseudo_request` — locked to Option (i).** The audit writer signature takes a `Request` object; WebSocket scope doesn't have one. **Decided 2026-04-28: build a small adapter inside `src/api/console.py` that exposes `.client.host`, `.headers`, `.state`, `.app` from the WebSocket scope as a duck-typed Request-like object.** Rationale: keeps `write_console_audit_row` HTTP-Request-only (no signature drift, no transport branch inside the audit writer), localises the adaptation to the WS handler module where it's needed, preserves IP attribution by reading `websocket.client.host` and UA by reading `websocket.headers["user-agent"]`. Rejected alternative: widening `write_console_audit_row` to accept either a `Request` or a `WebSocket` — pollutes the audit writer with transport-aware code and makes future audit call sites harder to reason about. The adapter is ~15 LOC in `src/api/console.py`, used by both `/console/ws` and `/console/demo/ws/{scan_id}`, and is the single seam between WS scope and the audit writer.
- **Audit row inside `with conn:`** so the row commits atomically with the connection. Per master spec §5.8 the `liveops.ws_connected` row is paired with the session's connection authorization (no separate mutation, but the framing is consistent with §7's "audit-paired" rule).

### 4.3 `/console/demo/ws/{scan_id}` — same shape

Master spec §5.5: "the demo WS endpoint follows the same contract: read cookie, hash, validate, accept-or-close-with-4401. Demo replay is operator-only by design."

`src/api/console.py:983-997` (current):

```python
@router.websocket("/demo/ws/{scan_id}")
async def demo_websocket(websocket: WebSocket, scan_id: str):
    """Stream demo events to the client via WebSocket."""
    await websocket.accept()
    pending = getattr(websocket.app.state, "_pending_demos", {})
    brief = pending.pop(scan_id, None)
    if brief is None:
        await websocket.close(code=1008, reason="Unknown scan_id")
        return
```

After 3g, the same auth-prelude block from `console_ws` is prepended. The existing `1008 Unknown scan_id` close stays as a separate post-auth check. The `liveops.ws_connected` audit row is also written here (with `payload={"path": "/console/demo/ws", "scan_id": scan_id}`).

Open question §7.7 asks whether the demo endpoint ships in this slice or is deferred. Recommendation: ships together — same handler shape, same imports, same auth helpers; the marginal cost is a few duplicated lines that a small extracted `_authenticate_ws(websocket)` helper could collapse into one call site each. The recommendation is to extract the helper inside `src/api/console.py` and have both handlers call it.

### 4.4 What the middleware does NOT do (re-statement)

Per master spec §5.6, the `SessionAuthMiddleware` HTTP-only scope branch already early-returns on `scope["type"] != "http"` (`src/api/auth/middleware.py:144-146`). Slice 3g does not change the middleware. The middleware whitelist (`/console/auth/login`, `/console/auth/whoami`) is unchanged. WS auth lives entirely in the handler.

---

## 5. Test plan (e)

### 5.1 New file: `tests/test_console_ws_auth.py`

Per master spec §8.2 the file covers seven WS auth cases plus one middleware-bypass assertion. Approximate test count: 8 tests, ~180 LOC. Pattern mirrors `tests/test_console_endpoints.py:373-387` (`TestConsoleWebSocket`) plus the `seed_console_operator` / `login_console_client` helper from `tests/_console_auth_helpers.py`.

| # | Test name | Assertion |
|---|---|---|
| 1 | `test_ws_valid_cookie_accepts` | After login, `client.websocket_connect("/console/ws")` succeeds; first server frame is queue_status (or pong reply to a client-sent ping); audit_log has one row with `action='liveops.ws_connected'`, `target_type='websocket'`, `operator_id=<seeded id>`, `session_id=<active session id>`. |
| 2 | `test_ws_no_cookie_closes_4401` | `unauthed_client.websocket_connect("/console/ws")` raises `WebSocketDisconnect(code=4401)`. No audit row written. No DB session refresh happened (SELECT against `sessions.last_seen_at` returns the same value as before the attempt). No pubsub subscription registered (assert via fakeredis pubsub channel count). |
| 3 | `test_ws_unknown_cookie_closes_4401` | Manually attach a cookie that does not hash to any row. Same close + same negative assertions as case 2. |
| 4 | `test_ws_revoked_session_closes_4401` | Login, then `revoke_session(conn, token)` directly, then attempt WS connect with the still-held cookie. close(4401). |
| 5 | `test_ws_idle_expired_closes_4401` | Login, fast-forward `sessions.expires_at` to a past timestamp, attempt WS connect. close(4401). |
| 6 | `test_ws_absolute_expired_closes_4401` | Login, fast-forward `sessions.absolute_expires_at` to a past timestamp, attempt WS connect. close(4401). |
| 7 | `test_ws_disabled_operator_closes_4401` | Login, set `operators.disabled_at = now`, attempt WS connect. close(4401). (Note: this is the WS analogue of the middleware's `auth.session_rejected_disabled` audit row from slice 3e. Whether the WS path also writes that row is open question §7.9 — recommend YES for symmetry, but flag the read-side audit overhead.) |
| 8 | `test_ws_middleware_does_not_auth_upgrade` | Spin up `create_app()` with the real `SessionAuthMiddleware` mounted. Open WS to `/console/ws` with NO cookie. Patch the WS handler to record entry (e.g. via a module-level boolean flag set in the first line of the handler, OR via monkeypatching `validate_session_by_hash` to log a sentinel). Assert that the handler entry was reached (the middleware did NOT short-circuit the upgrade). This locks in the design that the handler is the gate, not the middleware. |

The same suite exercises `/console/demo/ws/{scan_id}` for cases 1–7 as a parameterised second pass (same logic, different path) — total ≈14 effective assertions. Implementation may collapse the duplication via `pytest.mark.parametrize`.

### 5.2 Existing tests that need adjustment

- `tests/test_console_endpoints.py:373-387` (`TestConsoleWebSocket`) — **update.** The existing `test_ws_connects` and `test_ws_ping_pong` use the authenticated `client` fixture (which logs in via `login_console_client`). After 3g they still pass — the cookie jar carries the session through `client.websocket_connect`, which is the happy path. No code change needed; mark them as covered-by-side-effect of the new auth gate.
- `tests/test_console.py:272-275` (`test_websocket_connects`) — **verify.** Uses `client.websocket_connect("/console/demo/ws/test-id")`. Same situation — authenticated `client` fixture should carry cookies through.
- `tests/test_session_auth.py` — `test_app_prefix_protected` — **unchanged.** `/app/*` is already in `_PROTECTED_PREFIXES` on the slice 3f baseline (see §6); the test continues to assert 401 and gates against any regression on the constant.

### 5.3 New SPA tests (out of scope for the Python harness — flagged for future)

The SPA additions (login view, bootstrap state machine, CSRF helper threading) currently have no Vitest harness; the existing frontend Vite project doesn't include one. Slice 3g should NOT introduce a Vitest harness — that is a separate infrastructure concern. SPA verification is browser-eyeball QA in DEV against `make dev-up` (per memory `feedback_test_frontend_in_browser`). Federico signs off on the SPA before commit.

If a Vitest harness is later added (precedent: `apps/signup/` has one — `make signup-test`), the SPA tests for slice 3g would be:

- whoami → 200 → render Dashboard.
- whoami → 204 → render BootstrapEmpty.
- whoami → 409 → render AllDisabled.
- whoami → 401 → render Login form.
- Login submit → 200 → store csrf_token → connect WS.
- Login submit → 401 → show invalid_credentials error.
- Login submit → 429 → show countdown derived from Retry-After.
- `postJSON` mutating fetch → header includes `X-CSRF-Token`.
- `fetchJSON` read fetch → header does NOT include `X-CSRF-Token`.

Out of scope for this slice; flagged here for visibility.

---

## 6. `/app` protection — verification step (no code change)

`src/api/auth/middleware.py:97` already reads `_PROTECTED_PREFIXES = ("/console", "/app")` on the committed slice 3f baseline (commit `d0bc063`). The original slice 3f session briefly carved `/app` out as part of an option-2 attempt that was reverted before commit; that's the source of the "single-line revert" framing in earlier briefs. **No middleware change is needed in slice 3g.**

The implementation PR's only obligation here is a verification grep at the start of work to confirm the constant hasn't drifted. If it has, the PR restores the tuple. `tests/test_session_auth.py::test_app_prefix_protected` continues to assert 401 on `/app/` regardless, so any regression on the constant fails CI before merge.

### 6.1 Postscript — SPA bypass added in PR #54 (2026-04-30)

§6 above stands as locked rationale-of-record. Browser smoke testing after slice 3g + 3g.5 merged surfaced the chicken-and-egg gap that §6 (and master spec §8.2 `/app/...` test bullet) missed: `SessionAuthMiddleware` 401s `/app/*` for unauth users, but the SPA bundle is the surface that drives auth state via `whoami` (204 / 409 / 401 / 200). Gating the bundle itself means an unauth user can never reach BootstrapEmpty / Login / AllDisabled.

PR #54 (`9b5e443`) added a method-restricted, path-restricted SPA bypass on top of `_PROTECTED_PREFIXES`:

- `_SPA_SHELL_PATHS = {"/app", "/app/", "/app/index.html"}` — exact-match SPA shell entry points.
- `_SPA_ASSET_PREFIXES = ("/app/assets/",)` — vite-emitted asset directory.
- `_SPA_BYPASS_METHODS = frozenset({"GET", "HEAD"})` — read-only methods only.

`_is_spa_public_asset(path)` matches the union and explicitly excludes `/app/api/*` / `/app/ws/*`. The middleware short-circuits to pass-through inside the protected prefix only when both predicates (path + method) match. Mutating methods on the same paths still require auth.

`tests/test_session_auth.py::test_app_prefix_protected` URL changed from `/app/` to `/app/whatever-else` post-bypass; 8 new tests in `tests/test_auth_middleware.py` cover the bypass + cross-prefix exclusion. Production smoke on `heimdall-api:0a8a9ca-dirty` confirmed all 11 expected URLs match (5 bypass-200, 5 gated-401, 1 redirect-307).

This postscript exists so a reader landing on §6 from a search hit knows the constants in `_PROTECTED_PREFIXES` are authoritative AND insufficient — both gates fire. Master spec §8.2 test enumeration (`/app/...` bullet) is reconciled in the same doc-PR.

### 6.2 Locked-spec passages superseded by PR #54

Three passages elsewhere in this LOCKED spec pre-date PR #54 and must be read with §6.1 in mind. The original prose is preserved per the LOCKED-preservation pattern; the bullets below are the corrected reading. References use section anchors rather than line numbers so the pointer survives subsequent appends.

- **§5.2 — `tests/test_session_auth.py` "unchanged" claim.** The bullet describes `test_app_prefix_protected` as unchanged. PR #54 moved the asserted URL from `/app/` to `/app/whatever-else` so the 401 assertion still holds against a non-bypass path. The test still gates against any regression on `_PROTECTED_PREFIXES`; only the asserted URL moved off the bypass set.
- **§6 — verification step.** "Continues to assert 401 on `/app/` regardless." Post-#54, that exact URL bypasses the middleware on GET/HEAD; the test asserts 401 on `/app/whatever-else` instead. Regression coverage on the prefix constant is unchanged.
- **§9.1 — `Lever 1 — git revert` procedure.** The procedure describes a single-commit revert (`git revert <slice-3g-merge-sha>`) restoring slice 3f's posture with `/app/*` returning a static 401 to anonymous browsers. Post-#54, the revert chain is two commits, ordered: revert `9b5e443` (PR #54) **first**, then `ee8662d` (slice 3g). PR #54's `_SPA_*` additions sit inside `src/api/auth/middleware.py` whose creation/structure was introduced by slice 3g; reverting slice 3g first leaves PR #54's modifications hanging on a file the revert is trying to delete, and `git apply -R` does not produce a clean tree. After both reverts, the posture matches slice 3f (no `_SPA_*` constants, `/app/*` fully gated). Recovery time is still ~5 min; the chain is two commits.

---

## 7. Decisions (locked)

**Status (2026-04-28).** Federico reviewed the nine items §7.1–§7.9 below and accepted the recommendation under each. The "Recommendation" line in each subsection is binding — the prose is the rationale-of-record, not an open deliberation. §7.10 is the **only** open item; slice 3g implementation is blocked on its resolution.

**Locked outcomes (read this table; the subsection prose is the why):**

| § | Topic | Decided 2026-04-28 |
|---|---|---|
| 7.1 | Login form placement | Option C — separate `Login.svelte` mounted by App.svelte's whoami state machine |
| 7.2 | CSRF token storage | Option C — re-derive from `heimdall_csrf` cookie via `document.cookie`; `lib/auth.svelte.js` is a fast cache |
| 7.3 | WS reconnect timing after login | Option C — direct `connect()` call from inside `login()` after `auth.status='authenticated'` |
| 7.4 | 204 (no operators seeded) UX | Option C — distinct splash, copy only, no runbook link |
| 7.5 | 409 (all operators disabled) UX | Option B — distinct components per state |
| 7.6 | Mid-session 401 UX | Option B — redirect-to-login |
| 7.7 | `/console/demo/ws/{scan_id}` handler auth | Option A — ships together; extract `_authenticate_ws(websocket)` helper |
| 7.8 | `liveops.ws_connected` audit-row test shape | Option A — real `websocket_connect` round trip via TestClient |
| 7.9 | Disabled-operator audit row on WS rejection | Option A — symmetry with HTTP middleware; extract `_maybe_write_disabled_operator_audit` to `src/api/auth/audit.py` |
| 7.10 | Legacy-mode SPA behavior | Option B — **retire `LegacyBasicAuthMiddleware` + `HEIMDALL_LEGACY_BASIC_AUTH` in slice 3g.** Rollback is `git revert`. |
| 7.11 | SPA automated test coverage | Option B — **hard-gate production deploy on slice 3g.5** (SPA Vitest tests). Slice 3g implementation merges to `feat/stage-a-foundation`; the bundle does NOT merge to `main` or push to `prod` until 3g.5 lands the SPA test harness + auth-flow tests. Rationale: `src/api/frontend/package.json` has no Vitest dep / no harness; setting it up plus writing the auth-state-machine tests is a meaningful side-project that would balloon slice 3g into a frontend-tooling slice. Decoupling preserves slice 3g's narrow scope and still gates the production deploy on real SPA test evidence. |

### 7.1 Login form placement

**Question.** Where does the login form live in the SPA?

| Option | Description | Trade-offs |
|---|---|---|
| A | Standalone hash route `#/login` driven by `router.svelte.js`. The router gains a `'login'` view; App.svelte's outer `{#if}` chain handles it like any other view. | Symmetric with existing views. `router.params` could carry a post-login redirect target. Slight overhead — adds a view to `VALID_VIEWS` that doesn't fit the data-page metaphor. |
| B | Inline modal in `App.svelte` rendered as an overlay over a blurred dashboard. Bootstrap state determines whether the modal blocks interaction. | Tight wiring with whoami state machine. Modal-style auth feels invasive on cold-start; the blurred dashboard underneath is meaningless data the user hasn't loaded yet. |
| C | Separate `Login.svelte` component mounted by `App.svelte` based on `auth.status === 'unauthenticated'`. NOT a route; just a component. The router doesn't know about it. | Cleanest separation — login is an app state, not a navigation target. Matches `BootstrapEmpty.svelte` and `AllDisabled.svelte`'s pattern. Doesn't need router changes. |

**Recommendation: Option C.** Login is a state of the application, not a navigable view. Treating it as a route forces the router to know about authentication, which couples two concerns that should stay independent. Option C also extends naturally to the bootstrap-empty / all-disabled splash screens which have the same "this is a state, not a page" character.

**Is there a more elegant, simpler way?** Option C is already the simplest of the three; there's no clever trick that beats "render a different component when auth.status is X." Skip the cleverness, ship the obvious shape.

### 7.2 CSRF token storage

**Question.** Where does `auth.csrfToken` live across SPA mounts and refreshes?

| Option | Description | Trade-offs |
|---|---|---|
| A | In-memory only (module state inside `lib/auth.svelte.js`). Page refresh forces re-login. | Smallest exposure surface. UX cost: any hard refresh logs the user out (whoami probe runs again, but if the cookie is HttpOnly the session is alive on the server — the SPA just loses the CSRF token until next login). |
| B | `sessionStorage`. Survives reload within a tab session, dies on tab close. | Refresh-survivable. `sessionStorage` is per-tab + per-origin, not shared across tabs (each tab logs in independently). Slightly broader exposure (XSS can read `sessionStorage`, but XSS can also intercept fetch headers anyway). |
| C | Re-derive from the `heimdall_csrf` cookie via `document.cookie`. Cookie is non-`HttpOnly` by spec design (master §4.1). | Refresh-survivable, no extra storage. Slightly slower path (cookie parse on every getter). |

**Recommendation: Option C.** The cookie is already the wire-level companion to the session token; reading it via `document.cookie` is the spec-blessed access path (master §4.1 "the SPA must read it via `document.cookie` to put in `X-CSRF-Token`"). In-memory state in `lib/auth.svelte.js` is a fast cache that is repopulated from the cookie on a fresh module load. This avoids the duplicated truth problem of Option B (sessionStorage value vs cookie value diverging) and avoids the UX cost of Option A.

**Is there a more elegant, simpler way?** Option C IS the simpler way — it leverages the existing wire contract instead of inventing a parallel storage. The fast-cache in `lib/auth.svelte.js` is mostly an ergonomic getter (`getCsrfToken()`) rather than load-bearing state.

### 7.3 WS reconnect timing after login

**Question.** After successful login transitions `auth.status` to `'authenticated'`, when does `connect()` (WebSocket) fire?

| Option | Description | Trade-offs |
|---|---|---|
| A | Auto-reconnect via Svelte 5 reactive effect: `$effect` watches `auth.status`, calls `connect()` when it flips to `'authenticated'`. | Zero-click UX. Reactive effects can re-fire on unrelated reactivity if `auth` is mutated for any other reason — needs care. |
| B | Explicit user action — login success shows a "connect to live updates" button, user clicks. | Predictable; no surprise reconnect. UX cost: meaningless click for the operator who just successfully logged in. |
| C | Direct call from `login()` after `auth.status` is set, but BEFORE returning to the caller. | Imperative + simple; no reactive coupling. Tight coupling between auth and ws modules — one writes, the other reads. |

**Recommendation: Option C.** The `login()` function is the canonical post-auth action; calling `connect()` from within it is the most explicit shape and avoids both the reactive-effect-re-fire risk of A and the dead-click cost of B. The existing `App.svelte:23` already calls `connect()` from `onMount`; slice 3g moves that call into `login()` (and into `App.svelte`'s mount when whoami already returns 200, i.e. user re-loads with valid cookie).

**Is there a more elegant, simpler way?** No. Direct call is the obvious shape; reactive effects are a more powerful tool reserved for cases where the trigger is genuinely indirect.

### 7.4 BootstrapEmpty (204) UX

**Question.** What does the "no operators seeded" splash look like, and does it link to any runbook?

| Option | Description | Trade-offs |
|---|---|---|
| A | Same screen as the login form, with a non-dismissible banner reading "No operators seeded — talk to your admin." Login form disabled. | Single splash component for both states (login form + this banner). Compact. UX cost: shows form fields the user can't use, which is product-hostile. |
| B | Distinct screen with operator-bootstrap copy. Includes a link to the runbook section that tells admin how to seed. Link can be internal (markdown rendered) or external (GitHub URL). | Clear separation. Link risk: runbook URL changes break the link; if internal markdown rendering, adds a renderer dependency. |
| C | Distinct screen with copy only, no link. Admin googles the runbook. | Simplest; nothing to maintain. Operator gets less guidance. |

**Recommendation: Option C.** SMB-targeted product; the only realistic "operator" who hits this screen is Federico himself or whoever inherits the deployment. A static copy block ("No operators seeded. Run the seed step or contact your administrator.") is enough; the runbook is inside the repo, not on the public Internet, so a link from the SPA wouldn't survive air-gapping anyway. If the splash is ever shown to a real third-party operator, a one-line addition can include a link without rebuilding the component.

**Is there a more elegant, simpler way?** Option C is already the simplest; A is more code for less helpful UX, B is more code for marginally helpful UX.

### 7.5 AllDisabled (409) UX

**Question.** Same screen as 204 with different copy, or distinct screen?

| Option | Description | Trade-offs |
|---|---|---|
| A | Single component parameterised on `auth.status` ('bootstrap-empty' vs 'all-disabled'), same layout, different copy block. | DRY. One file to style. |
| B | Distinct components per state, even though they render the same shape. | Verbose but maximally clear; tests can target each independently. |

**Recommendation: Option B.** The two states are operationally distinct (master spec §3.5: "the SPA needs to render a different UX for each, and the wire signal must say which is which"). Two small components are clearer than one parameterised component, and the redundancy is small (≤30 lines each). Federico can review each splash's copy without diff-noise from the other.

**Is there a more elegant, simpler way?** Option B's redundancy IS the simpler way — splash screens that differ only in copy are clearer when each is its own file. DRY for two-line variants is fake DRY.

### 7.6 Mid-session 401 UX

**Question.** When a `/console/*` endpoint returns 401 mid-session (idle TTL hit, absolute TTL hit, operator disabled mid-session), how does the SPA recover?

| Option | Description | Trade-offs |
|---|---|---|
| A | Silent retry once. The 401 handler in `lib/api.js` re-probes whoami; if whoami returns 200 (rare race), re-issue the original fetch; if whoami returns 401, transition to login view. | Smooth UX for the rare race. Still loses unsaved state on the second branch. Adds a code path for a ~1ms edge case. |
| B | Redirect to login view immediately. Loses any unsaved local state (e.g. an unfilled command form). | Predictable. Operator re-logs in, loses some state. |
| C | Error toast with "Log in again" button. Operator clicks; transitions to login. Local state preserved (though probably stale after 15min idle anyway). | Friendliest. Slightly more code (toast component + click handler). |

**Recommendation: Option B.** The operator console's UI is predominantly read-only (dashboard counters, lists, log streams); the only mutating actions are settings PUT, command POST, and retention actions. None of these maintain partial-input state worth preserving across an idle-expiry. Option C's "preserve state" claim is mostly fiction — by the time the user notices they're logged out, the form they were filling is 15+ minutes stale anyway. Option B's predictable UX wins.

**Is there a more elegant, simpler way?** Option B IS the simpler way; A and C add code paths for edges that don't occur in practice for this product.

### 7.7 `/console/demo/ws/{scan_id}` — same handler auth or deferred?

**Question.** Does the demo WS endpoint ship with the same handler-level auth as `/console/ws` in slice 3g, or is it deferred to a later slice?

| Option | Description | Trade-offs |
|---|---|---|
| A | Ships together. Both endpoints get the auth prelude. | Same handler shape, free. Doubles the test surface in `tests/test_console_ws_auth.py` (parameterise) but no new logic. |
| B | Deferred to a later slice. `/console/demo/ws` stays unauthenticated. | Smaller diff. Demo WS endpoint is operator-internal runtime tooling (master §6.2); leaving it open is a smaller leak surface than `/console/ws` (queue depths + pubsub) but still inappropriate. |

**Recommendation: Option A — ships together.** Same handler shape, same imports, same auth helpers; the marginal cost of including it is a few lines and a parameterised test pass. Master spec §5.5 is explicit that demo endpoint follows the same contract. Deferring creates a known-incomplete state and a future scoping conversation. Recommend the helper extraction (`_authenticate_ws(websocket)` in `src/api/console.py`) so both handlers call into one auth path.

**Is there a more elegant, simpler way?** The helper extraction is the elegant way — instead of copy-pasting the auth prelude, extract once and call twice. That's the simpler shape and the spec follows naturally.

### 7.8 `liveops.ws_connected` audit-row test shape

**Question.** How does `tests/test_console_ws_auth.py` verify the audit row was written?

| Option | Description | Trade-offs |
|---|---|---|
| A | Real `client.websocket_connect("/console/ws")` round trip in TestClient. After the connection is established (and immediately closed), open `console.db` and SELECT the audit_log rows. | High fidelity; tests the real handler path. Slower (full WS handshake + cleanup). Some flakiness risk from the async pubsub task setup. |
| B | Unit-test with a fake WebSocket scope. Construct a `starlette.websockets.WebSocket` directly with a minimal `send`/`receive` mock and call the handler function. | Faster, deterministic. Doesn't exercise the real ASGI plumbing; if Starlette changes how `ws.cookies` works, the test passes but production breaks. |

**Recommendation: Option A.** The whole point of the test file is to lock in the handler's behaviour against real ASGI plumbing — that's where the data-leak surface lives. Unit tests against a mock WebSocket would have passed slice 3f's pre-fix state (`await websocket.accept()` works fine in a mock; the bug is conceptual, not mechanical). The real round trip via TestClient is what the existing `tests/test_console_endpoints.py:373` pattern uses, and it's the right shape.

**Is there a more elegant, simpler way?** Use the existing `TestConsoleWebSocket` pattern verbatim with the new authenticated `client` fixture. The "elegance" is in not inventing a new test harness for the same shape.

### 7.9 Disabled-operator audit row on WS rejection

**Question.** When the WS handler closes with 4401 because the operator was disabled mid-session (test case 7), should it write an `auth.session_rejected_disabled` audit row analogous to the HTTP middleware's behaviour from slice 3e?

| Option | Description | Trade-offs |
|---|---|---|
| A | YES — symmetry with the HTTP middleware (`src/api/auth/middleware.py:282-339`). The handler runs the same probe SELECT as `_maybe_write_disabled_operator_audit` and writes the row before the close. | Consistent forensic trail. Adds ~10 lines to the handler. |
| B | NO — WS rejection is read-side; per master spec §7.3 read-side audit is a Stage A.5 concern. The middleware's slice 3e write was an exception because the disabled operator's continued cookie attempts ARE a security signal. WS connection attempts arguably are too. | Less code; less audit volume. Loses the symmetry. |

**Recommendation: Option A.** The disabled-operator-mid-session signal is forensically valuable in both transports; if a compromised cookie is being used to repeatedly attempt connections, the audit log should show every attempt. The cost is small (one extra probe SELECT + one INSERT, both in the failure path). This is the same reasoning slice 3e applied for the HTTP path.

**Is there a more elegant, simpler way?** Extracting `_maybe_write_disabled_operator_audit` from `src/api/auth/middleware.py:282-339` into a shared helper that both the middleware and the WS handler call would prevent drift. Recommend a small refactor: move the function to `src/api/auth/audit.py` and import it from both call sites. This is a marginal scope expansion but avoids the duplicated-implementation drift risk.

### 7.10 Legacy-mode SPA behavior — DECIDED 2026-04-28: Option B (retire legacy)

**Decided 2026-04-28: Option B — retire `LegacyBasicAuthMiddleware` and `HEIMDALL_LEGACY_BASIC_AUTH` in slice 3g.** Slice 3g becomes the slice that completes the Stage A auth migration AND removes the rollback lever. Roll-forward only: rollback is `git revert` of the slice-3g merge SHA. The original deliberation, options table, and rationale are preserved below as the rationale-of-record.

---

**Question (resolved).** Slice 3f's `HEIMDALL_LEGACY_BASIC_AUTH=1` flag mounts `LegacyBasicAuthMiddleware` instead of `SessionAuthMiddleware` and skips the auth-router include. Under that flag, an operator hitting `/app/` gets the legacy Basic Auth dialog from the browser; once authenticated, the SPA loads. But the SPA itself — once slice 3g lands — runs the new whoami bootstrap on mount, which probes `/console/auth/whoami`, which is NOT mounted in legacy mode (the auth router was skipped). Result without an explicit decision: the SPA gets a 404 from `/console/auth/whoami`, which today's code path would surface as `auth.status === 'unauthenticated'`, which renders the new login form, which then posts to `/console/auth/login` (also not mounted), 404 again. The SPA in legacy mode is broken — same operational dead-end Codex flagged in slice 3f's pass 2/3/4/5 deliberation chain, just shifted into the legacy-flag branch.

Federico's constraint (2026-04-28): "if legacy-mode SPA behavior is still part of the rollback story, that branch should stop being optional before implementation starts."

| Option | Description | Trade-offs |
|---|---|---|
| A | **SPA detects legacy mode via 404 from `/console/auth/whoami` and renders a thin "legacy mode active" splash.** No login form attempt. The splash explains: "This deployment is on the legacy auth fallback. Full session-based features will return when `HEIMDALL_LEGACY_BASIC_AUTH` is unset." Read-only views (dashboard, logs) still work because `/console/*` is gated by Basic Auth at the middleware layer; mutations from the SPA work too because legacy mode skips CSRF entirely. | Keeps legacy as a real rollback lever for one more release. Costs ~30 LOC of SPA-side handling for a path that should rarely fire. The "legacy detection" branch is a code surface that could rot if untested. |
| B | **Retire `LegacyBasicAuthMiddleware` and `HEIMDALL_LEGACY_BASIC_AUTH` in slice 3g.** Slice 3g becomes the slice that completes the Stage A auth migration AND removes the rollback lever. Roll-forward only: if slice 3g has a bug, `git revert` the merge SHA and ship a fixed PR. | Cleanest endgame. ~60 LOC removed from `src/api/app.py` (the legacy branching) + `LegacyBasicAuthMiddleware` class deleted + the three branch-mount tests in `tests/test_session_auth.py` deleted. Spec §9.1 shrinks. Cost: loses the env-flip rollback path; `git revert` becomes the only recovery option for the next release window. |
| C | **Keep legacy mode but document the SPA as session-only.** Operators using legacy mode access the API directly via curl/scripts (`scripts/dev/console_login.sh`); the SPA is unsupported under legacy. The SPA's legacy-mode behavior is "broken" and explicitly documented as such; nobody is supposed to rely on it. | Smallest spec change (just a docstring + runbook note). Cost: the rollback lever exists but its UX is degraded; if Federico actually flips the flag in production, he can't use the SPA. The lever is for the API, not the UI. |

**Recommendation: Option B — retire legacy mode in slice 3g.** Reasoning:

1. Slice 3g brings session auth to feature parity (login form + WS auth + CSRF). The premise of the legacy lever was "if session auth has a critical bug, fall back to the known-working Basic Auth path." Once slice 3g ships green, that premise's "if" is much smaller — the entire auth surface has been exercised end-to-end.
2. Spec §9.1 of the master Stage A spec explicitly plans for legacy retirement "in the release after Stage A ships in prod." Slice 3g IS that release — it's the last Stage A slice (after this, the next sprint is Stage A.5 / V2 onboarding). Retiring legacy in 3g lines up with the spec's roadmap.
3. The maintenance cost of Option A's legacy-detection-in-SPA branch is real: a code path that rarely fires is a code path that rots. Federico's instinct ("stop being optional") points the same direction.
4. Rollback under Option B is `git revert` the slice-3g merge SHA → automatic redeploy. ~5 minutes. Compared to "edit env file + restart api container" (Option A's lever), the loss of velocity is small.
5. The deletion is mechanical: ~60 LOC across `src/api/app.py` (the `legacy_active` branching) + `LegacyBasicAuthMiddleware` class + three branch-mount tests in `tests/test_session_auth.py`. No behavior change for any non-rollback operator.

**Is there a more elegant, simpler way?** Option B is already the elegant shape — fewer code paths, fewer spec branches, cleaner endgame. Option A is more code for a path that exists only to be removed in the release after.

**Implementation note if B is selected.** The `tests/test_session_auth.py` branch-mount tests (`test_legacy_flag_with_creds_mounts_legacy`, `test_legacy_flag_without_creds_falls_back_to_session`) get deleted; `test_default_branch_mounts_session_auth` becomes the only branch-mount test (and can be inlined into a less ceremonious shape). The `_console_auth_helpers.py` helper continues to work unchanged. Spec §9.1 shrinks to "Lever 1 — git revert." Master spec §9.1 needs a one-line update noting legacy was retired in slice 3g.

---

## 8. Out of scope

Each item below is explicitly NOT in slice 3g.

| Item | Lands in | Notes |
|---|---|---|
| Vitest harness for SPA tests | **Slice 3g.5** (locked per §7.11 Option B; production-deploy gate) | Pattern exists in `apps/signup/` for reference. Slice 3g.5 ships the harness + auth-flow tests (login 200/401/429 paths, whoami 200/204/409/401 branching, CSRF threading on mutations, mid-session 401 redirect, Retry-After countdown). 3g implementation merges to `feat/stage-a-foundation` immediately; the bundle does NOT merge to `main` or push to `prod` until 3g.5 is green. |
| First-frame WS auth fallback | Master spec §5.4 — not planned | Cookie-only path is sufficient for browser clients; non-browser ops scripts can use `scripts/dev/console_login.sh` to capture the cookie. |
| Per-WS-disconnect audit row | Master spec §5.8 — deliberate Stage A simplification | Volume + signal-to-noise ratio. |
| Audit row on `/console/demo/ws` connect | Same as `/console/ws` — ships in 3g if Option 7.7-A is chosen | Parameterised case in the test file. |
| Stage A.5 control-plane guarantees | Stage A.5 sprint | Permission enum, `require_permission`, `config_changes` triggers, X-Request-ID middleware. |
| V2 onboarding view | After Stage A.5 | First feature that consumes the foundation. |

---

## 9. Rollback plan

Slice 3g is a behavioural change to the SPA + a tightening of the WS handler. Rollback levers in order of preference:

### 9.1 Lever 1 — `git revert` (locked per §7.10 Option B)

Slice 3g retires the `HEIMDALL_LEGACY_BASIC_AUTH` env-flip lever (per §7.10). The single recovery path:

1. `git revert <slice-3g-merge-sha>` on `feat/stage-a-foundation` (or directly on `main` if slice 3g has already merged).
2. Push to `prod` with `HEIMDALL_APPROVED=1`; SSH Pi5; `heimdall-deploy`.
3. Total recovery time: ~5 minutes.

This restores slice 3f's posture — `SessionAuthMiddleware` mounted by default, no SPA login form, no WS handler auth, and `/app/*` returning a static 401 to anonymous browsers. Operators can still hit the API via cookie auth using `tests/_console_auth_helpers.py` patterns or curl with the cookie set. There is no env-flip path; the recovery is a git operation only.

If slice 3g.5 (SPA Vitest tests) has also merged, the revert chain reverts both 3g and 3g.5 to land at slice 3f's known-good state.

### 9.2 Lever 2 — WS handler revert only

If the SPA flow is fine but the WS handler's auth gate is breaking some legitimate WS client, revert the handler edit alone:

1. `git revert <commit-sha>` for the WS-handler portion (cherry-pick if the commit is mixed).
2. Push to `prod` with `HEIMDALL_APPROVED=1`; SSH Pi5; `heimdall-deploy`.

Trade-off: this re-opens the data-leak surface. Only acceptable as a fast emergency revert; full revert (lever 9.1) is preferred.

### 9.3 Lever 3 — full revert

`git revert <stage-A-slice-3g-merge-sha>` per the Stage A master spec §9.3 pattern.

---

## 10. Appendix A — file map

Files added in slice 3g:

```
docs/architecture/stage-a-slice-3g-spec.md          # this file
src/api/frontend/src/lib/auth.svelte.js             # ~80 LOC — bootstrap/login/logout state machine
src/api/frontend/src/views/Login.svelte             # ~120 LOC — login form + 401/429/503 branches
src/api/frontend/src/views/BootstrapEmpty.svelte    # ~30 LOC — 204 splash
src/api/frontend/src/views/AllDisabled.svelte       # ~30 LOC — 409 splash
tests/test_console_ws_auth.py                       # ~180 LOC — 8 tests (or 14 with parameterise) per master §8.2
```

Files modified in slice 3g:

```
src/api/frontend/src/App.svelte                     # +30/-10 LOC — onMount runs bootstrap, outer {#if} on auth.status
src/api/frontend/src/lib/api.js                     # +20 LOC — csrfHeaders() + thread through postJSON / saveSettings / sendCommand
src/api/frontend/src/components/Topbar.svelte       # +15 LOC — logout button + display_name span
src/api/console.py                                  # +60 LOC — auth prelude on /console/ws + /console/demo/ws/{scan_id} + extracted helper + _build_pseudo_request adapter
src/api/auth/audit.py                               # +20 LOC — extract _maybe_write_disabled_operator_audit (per §7.9)
src/api/auth/middleware.py                          # -10 LOC — import the extracted helper instead of inline
src/api/app.py                                      # -60 LOC — delete LegacyBasicAuthMiddleware class + HEIMDALL_LEGACY_BASIC_AUTH env-flip branch + simplify auth-router include (per §7.10 Option B)
tests/test_session_auth.py                          # -50 LOC — delete test_legacy_flag_with_creds_mounts_legacy + test_legacy_flag_without_creds_falls_back_to_session; trim test_default_branch_mounts_session_auth to one-liner
docs/architecture/stage-a-implementation-spec.md    # one-line update to §9.1 noting legacy retired in slice 3g
docs/decisions/log.md                               # +1 entry — slice 3g locked scope (see addendum) + reference to slice 3g.5 hard-gate
```

Files DELETED in slice 3g:

```
(none — `LegacyBasicAuthMiddleware` is a class deletion inside src/api/app.py, not a file deletion)
```

Estimated total diff: +600 / -120 LOC across ~12 files. The legacy retirement adds ~110 LOC of deletes; the rest matches the prior estimate. Slice 3g.5 (SPA Vitest harness + auth-flow tests) is a separate slice, scoped to ~400 LOC of frontend tests + harness configs.

---

## 11. Appendix B — affected master-spec sections

| Master spec section | Slice 3g touches |
|---|---|
| §3.1 (login flow) | Read; SPA implements client side of the existing wire contract. |
| §3.5 (whoami split states) | Read; SPA's bootstrap state machine consumes the four states. |
| §4.1 (cookie names + attributes) | Read; SPA's CSRF helper reads `heimdall_csrf` per the spec. |
| §4.4 (CSRF defense) | Read; SPA threads `X-CSRF-Token` per double-submit pattern. |
| §5.2–§5.3 (WS auth — chosen path) | Implemented for the first time. The handler-level auth Option 2 was specified but not built until 3g. |
| §5.5 (demo WS) | Implemented (per §7.7 recommendation). |
| §5.7 (close codes) | Used. 4401 is the close code on auth failure. |
| §5.8 (per-WS audit row) | Implemented. `liveops.ws_connected` row written in the same `with conn:` block. |
| §6.3 (auth router response shapes) | Read; SPA login + logout consume them. |
| §8.2 (`test_console_ws_auth.py`) | Implemented. The seven cases land here. |
| §11 (out of scope) | This slice does NOT advance any master-spec out-of-scope item. |

---

## 12. Revision history

| Date | Change |
|---|---|
| 2026-04-28 (post-3f wrap-up) | Initial draft. **DRAFT** status; nine open questions for Federico. |

---

**End of slice 3g spec — DRAFT.**
