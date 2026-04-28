/**
 * Authentication state machine for the operator console SPA.
 *
 * Stage A slice 3g (a)(b)(c) per docs/architecture/stage-a-slice-3g-spec.md
 * §2 + §3. Mirrors the wire contract from the master spec §3.1 / §3.5 /
 * §4.1 / §4.4 / §6.3.
 *
 * Five user-facing states drive App.svelte's outer {#if} chain:
 *
 *   loading           — bootstrap() in flight; render nothing yet.
 *   bootstrap-empty   — whoami returned 204 (no operators seeded).
 *   all-disabled      — whoami returned 409 (every operator disabled).
 *   unauthenticated   — whoami returned 401 (or login failed); render Login.
 *   authenticated     — whoami / login returned 200; render the app shell.
 *
 * One transient state is layered on top of the wire states:
 *
 *   rate-limited      — login returned 429; Login view shows a countdown
 *                       and reverts to "unauthenticated" when retryAfter
 *                       reaches 0.
 *
 * CSRF token storage is Option C from spec §7.2: the canonical source is
 * the non-HttpOnly heimdall_csrf cookie (set alongside heimdall_session
 * by the login handler). This module keeps a fast in-memory cache via
 * auth.csrfToken so callers don't parse document.cookie on every fetch,
 * but a hard refresh that clears the cache transparently re-hydrates
 * from the cookie on the next getCsrfToken() call.
 */

import { disconnect } from './ws.svelte.js';

const CSRF_COOKIE = 'heimdall_csrf';

// Single in-flight bootstrap probe so a burst of mid-session 401s
// (or a 401 racing against the onMount call) collapses to one whoami
// round trip with one final state mutation.
let bootstrapInFlight = null;

export const auth = $state({
  status: 'loading',
  operator: null,
  csrfToken: null,
  retryAfter: 0,
  error: null,
});

function readCsrfFromCookie() {
  if (typeof document === 'undefined' || !document.cookie) return null;
  const parts = document.cookie.split(';');
  for (const part of parts) {
    const eq = part.indexOf('=');
    if (eq < 0) continue;
    const name = part.slice(0, eq).trim();
    if (name === CSRF_COOKIE) {
      return decodeURIComponent(part.slice(eq + 1)) || null;
    }
  }
  return null;
}

/** Read the current CSRF token. Re-hydrates from the heimdall_csrf
 *  cookie when the in-memory cache is empty (e.g. after a hard
 *  refresh that nukes module state but leaves the cookie). */
export function getCsrfToken() {
  if (auth.csrfToken) return auth.csrfToken;
  const fromCookie = readCsrfFromCookie();
  if (fromCookie) {
    auth.csrfToken = fromCookie;
    return fromCookie;
  }
  return null;
}

function applyAuthedSession(body) {
  auth.operator = body.operator ?? null;
  auth.csrfToken = body.csrf_token ?? readCsrfFromCookie();
  auth.retryAfter = 0;
  auth.error = null;
  auth.status = 'authenticated';
}

function clearAuthedSession() {
  auth.operator = null;
  auth.csrfToken = null;
  auth.retryAfter = 0;
}

async function _bootstrapImpl() {
  // Don't blank out an already-authenticated session while we re-probe;
  // only prime the loading state on the first probe so the boot splash
  // shows for fresh page loads but mid-session re-probes don't flicker.
  if (auth.status !== 'authenticated') {
    auth.status = 'loading';
  }
  auth.error = null;
  let res;
  try {
    res = await fetch('/console/auth/whoami', { credentials: 'same-origin' });
  } catch {
    clearAuthedSession();
    auth.status = 'unauthenticated';
    auth.error = 'network';
    return;
  }

  if (res.status === 204) {
    clearAuthedSession();
    auth.status = 'bootstrap-empty';
    return;
  }
  if (res.status === 409) {
    clearAuthedSession();
    auth.status = 'all-disabled';
    return;
  }
  if (res.status === 401) {
    clearAuthedSession();
    auth.status = 'unauthenticated';
    return;
  }
  if (res.status === 503) {
    clearAuthedSession();
    auth.status = 'unauthenticated';
    auth.error = 'service_unavailable';
    return;
  }
  if (res.ok) {
    let body;
    try {
      body = await res.json();
    } catch {
      clearAuthedSession();
      auth.status = 'unauthenticated';
      auth.error = 'malformed_response';
      return;
    }
    applyAuthedSession(body);
    return;
  }

  // Anything unexpected (5xx other than 503) lands the operator on
  // the login form with a generic error rather than a half-loaded UI.
  clearAuthedSession();
  auth.status = 'unauthenticated';
  auth.error = `http_${res.status}`;
}

/** Probe GET /console/auth/whoami and transition into the matching
 *  branch. Always called from App.svelte's onMount before any other
 *  fetch — the rest of the SPA must not run until status reaches
 *  'authenticated'. Concurrent callers share the same in-flight probe
 *  so a 401 burst can't race overlapping state mutations.
 *
 *  Not declared `async` — the runtime would wrap the returned in-flight
 *  promise in a fresh promise on each call, defeating the
 *  `p1 === p2` identity guarantee that slice 3g.5 §5.2 test #1 locks. */
export function bootstrap() {
  if (bootstrapInFlight) return bootstrapInFlight;
  const probe = _bootstrapImpl();
  bootstrapInFlight = probe;
  // Clear the in-flight slot whether the probe resolves or rejects so
  // a subsequent call retries instead of returning a dead promise.
  // Use `.then(...).then(...)` rather than `.finally(...)` so we can
  // guarantee the slot clears before any chained `.then` on the
  // returned promise observes the result — without that ordering, a
  // caller's `.then` could fire while bootstrapInFlight still points
  // at the resolved promise, briefly hiding a release-on-throw bug.
  probe.then(
    () => { if (bootstrapInFlight === probe) bootstrapInFlight = null; },
    () => { if (bootstrapInFlight === probe) bootstrapInFlight = null; },
  );
  return probe;
}

function parseRetryAfter(headerValue) {
  if (!headerValue) return 0;
  const n = Number.parseInt(headerValue, 10);
  if (!Number.isFinite(n) || n < 0) return 0;
  // Clamp extreme values to a sane upper bound so the countdown UI
  // never renders something operationally absurd (the server's own
  // CONSOLE_LOGIN_RATE_LIMIT_TTL_SEC defaults to 900s; allow up to 1h).
  return Math.min(n, 3600);
}

/** POST /console/auth/login and transition into the matching branch.
 *  On 200, applies the new session + connects the WebSocket per spec
 *  §7.3 Option C (direct call from inside login()). */
export async function login(username, password) {
  auth.error = null;
  auth.retryAfter = 0;
  let res;
  try {
    res = await fetch('/console/auth/login', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    });
  } catch {
    auth.error = 'network';
    return false;
  }

  if (res.status === 429) {
    const seconds = parseRetryAfter(res.headers.get('Retry-After'));
    auth.retryAfter = seconds > 0 ? seconds : 1;
    auth.status = 'rate-limited';
    auth.error = 'rate_limited';
    return false;
  }
  if (res.status === 401) {
    auth.error = 'invalid_credentials';
    auth.status = 'unauthenticated';
    return false;
  }
  if (res.status === 503) {
    auth.error = 'service_unavailable';
    auth.status = 'unauthenticated';
    return false;
  }
  if (!res.ok) {
    auth.error = `http_${res.status}`;
    auth.status = 'unauthenticated';
    return false;
  }

  let body;
  try {
    body = await res.json();
  } catch {
    auth.error = 'malformed_response';
    auth.status = 'unauthenticated';
    return false;
  }
  applyAuthedSession(body);
  // Spec §7.3 Option C wires the WebSocket startup to the
  // 'authenticated' transition — App.svelte's $effect on auth.status
  // owns the single connect() call site, avoiding the duplicate-WS
  // race that two parallel connect() invocations would create when
  // the first socket is still in the CONNECTING state.
  return true;
}

/** POST /console/auth/logout and reset local state regardless of
 *  response. The server clears cookies on 204; even on 401 we want
 *  the SPA to reset to the login view. */
export async function logout() {
  const csrf = getCsrfToken();
  try {
    await fetch('/console/auth/logout', {
      method: 'POST',
      credentials: 'same-origin',
      headers: csrf ? { 'X-CSRF-Token': csrf } : {},
    });
  } catch {
    /* network failure still falls through to the local reset */
  }
  try {
    disconnect();
  } catch {
    /* ignore */
  }
  clearAuthedSession();
  auth.error = null;
  auth.status = 'unauthenticated';
}

/** Counter helper for the rate-limited Login view. Returns true when
 *  the countdown reached zero and the form re-enabled. */
export function tickRateLimit() {
  if (auth.status !== 'rate-limited') return false;
  if (auth.retryAfter > 1) {
    auth.retryAfter -= 1;
    return false;
  }
  auth.retryAfter = 0;
  auth.status = 'unauthenticated';
  auth.error = null;
  return true;
}

/** Handle a mid-session 401 from any /console/* endpoint: re-probe
 *  whoami, which transitions back to 'unauthenticated' (or
 *  'all-disabled' if the operator was just disabled). Per spec §3.4
 *  + §7.6 Option B. */
export async function handleSessionExpired() {
  await bootstrap();
}
