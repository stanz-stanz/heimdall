/**
 * `bootstrap()` in-flight collapse contract test.
 *
 * Stage A slice 3g.5 §5.2 (3 tests). Spec citation: slice 3g spec
 * §2.2 + §3.4 (bootstrapInFlight race-mitigation).
 *
 * Locks the contract that concurrent `bootstrap()` callers share one
 * fetch round trip AND receive the same promise object. Without this
 * guarantee, a 401 burst from `App.svelte.initialiseShell()`'s parallel
 * `fetchDashboard` + `fetchCampaigns` calls would produce two whoami
 * probes racing two state mutations (slice 3g spec §3.4).
 *
 * Decision §7.5 Option A — required (locks the §2.2 + §3.4 race-mitigation
 * contract from `auth.svelte.js:34-37`).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('$lib/ws.svelte.js', () => ({
  connect: vi.fn(),
  disconnect: vi.fn(),
}));

import { auth, bootstrap } from '$lib/auth.svelte.js';


function jsonResponse(status, body) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: { get: () => null },
    json: async () => body,
  };
}


beforeEach(() => {
  vi.restoreAllMocks();
  auth.status = 'loading';
  auth.operator = null;
  auth.csrfToken = null;
  auth.retryAfter = 0;
  auth.error = null;
});


describe('bootstrap() in-flight collapse', () => {
  it('test_bootstrap_collapses_to_one_fetch_round_trip', async () => {
    // Deferred fetch — captures resolve so we can hold the in-flight
    // window open while we make the second call. Wrap assertions in
    // try/finally so any failure still resolves the deferred promise
    // and clears module-level `bootstrapInFlight`; otherwise a failed
    // assertion here pollutes subsequent tests in the file.
    let resolveFetch;
    const fetchSpy = vi.fn(() => new Promise((resolve) => {
      resolveFetch = resolve;
    }));
    vi.stubGlobal('fetch', fetchSpy);

    const p1 = bootstrap();
    const p2 = bootstrap();
    try {
      // Both callers must receive the same promise object — the
      // wrapper returns `bootstrapInFlight` directly when one is active.
      expect(p1).toBe(p2);
    } finally {
      resolveFetch(jsonResponse(401, { error: 'not_authenticated' }));
      await Promise.all([p1, p2]);
    }

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    expect(auth.status).toBe('unauthenticated');
  });

  it('test_bootstrap_releases_in_flight_after_resolve', async () => {
    const fetchSpy = vi.fn(async () => jsonResponse(401, {}));
    vi.stubGlobal('fetch', fetchSpy);

    await bootstrap();
    expect(fetchSpy).toHaveBeenCalledTimes(1);

    await bootstrap();
    expect(fetchSpy).toHaveBeenCalledTimes(2);
  });

  it('test_bootstrap_releases_in_flight_after_throw', async () => {
    // First call: fetch throws (network failure) — `_bootstrapImpl`
    // catches the throw and translates it into `auth.error='network'`
    // + `auth.status='unauthenticated'`, so this test exercises the
    // RESOLVE-arm of the wrapper's cleanup chain (release after a
    // handled error), not the explicit reject-arm. The reject-arm
    // cleanup callback is dead under the current `_bootstrapImpl`
    // contract and exists only as defense-in-depth against a future
    // refactor that lets a rejection escape the impl. Test name
    // preserved for spec §5.2 traceability.
    const fetchSpy = vi.fn();
    fetchSpy.mockImplementationOnce(async () => { throw new TypeError('net'); });
    fetchSpy.mockImplementationOnce(async () => jsonResponse(200, {
      operator: { id: 1, username: 'op', display_name: 'Op', role_hint: 'owner' },
      session: {},
      csrf_token: 'tok',
    }));
    vi.stubGlobal('fetch', fetchSpy);

    await bootstrap();
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    expect(auth.status).toBe('unauthenticated');
    expect(auth.error).toBe('network');

    await bootstrap();
    expect(fetchSpy).toHaveBeenCalledTimes(2);
    expect(auth.status).toBe('authenticated');
  });
});
