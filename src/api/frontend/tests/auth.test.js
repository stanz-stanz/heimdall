/**
 * Auth state-machine unit tests for `src/lib/auth.svelte.js`.
 *
 * Stage A slice 3g.5 §3 (32 tests). Spec citations on each subsection.
 * Pattern mirrors `apps/signup/tests/api.test.js` — `vi.stubGlobal('fetch', ...)`
 * before calling the helper, assertions on the `auth` $state proxy.
 *
 * `connect` / `disconnect` from `ws.svelte.js` are mocked at the top so
 * logout tests don't touch the real WebSocket module (browser-QA territory
 * per slice 3g.5 spec §8).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock the WS module BEFORE importing auth.svelte.js so the auth module's
// `import { disconnect } from './ws.svelte.js'` resolves to the mock.
vi.mock('$lib/ws.svelte.js', () => ({
  connect: vi.fn(),
  disconnect: vi.fn(),
}));

import {
  auth,
  bootstrap,
  login,
  logout,
  getCsrfToken,
  tickRateLimit,
  handleSessionExpired,
} from '$lib/auth.svelte.js';
import { disconnect } from '$lib/ws.svelte.js';


function jsonResponse(status, body, headers = {}) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: {
      get: (name) => headers[name] ?? headers[name?.toLowerCase()] ?? null,
    },
    json: async () => body,
  };
}

function malformedJsonResponse(status) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: { get: () => null },
    json: async () => {
      throw new SyntaxError('Unexpected token');
    },
  };
}


beforeEach(() => {
  vi.restoreAllMocks();
  auth.status = 'loading';
  auth.operator = null;
  auth.csrfToken = null;
  auth.retryAfter = 0;
  auth.error = null;
  // Clear the heimdall_csrf cookie so the cookie-fallback test isn't
  // polluted by a prior test's auth.csrfToken write.
  document.cookie = 'heimdall_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/';
});


// ---------------------------------------------------------------------------
// 3.2 — bootstrap() ten branches
// ---------------------------------------------------------------------------

describe('bootstrap()', () => {
  it('test_bootstrap_200_authenticated', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse(200, {
        operator: { id: 1, username: 'op', display_name: 'Op', role_hint: 'owner' },
        session: {},
        csrf_token: 'tok',
      })),
    );
    await bootstrap();
    expect(auth.status).toBe('authenticated');
    expect(auth.operator).toEqual({
      id: 1, username: 'op', display_name: 'Op', role_hint: 'owner',
    });
    expect(auth.csrfToken).toBe('tok');
    expect(auth.error).toBeNull();
  });

  it('test_bootstrap_204_bootstrap_empty', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(204, null)));
    auth.operator = { id: 9 };
    auth.csrfToken = 'leftover';
    await bootstrap();
    expect(auth.status).toBe('bootstrap-empty');
    expect(auth.operator).toBeNull();
    expect(auth.csrfToken).toBeNull();
  });

  it('test_bootstrap_409_all_disabled', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse(409, { error: 'all_operators_disabled' })),
    );
    await bootstrap();
    expect(auth.status).toBe('all-disabled');
  });

  it('test_bootstrap_401_unauthenticated', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse(401, { error: 'not_authenticated' })),
    );
    await bootstrap();
    expect(auth.status).toBe('unauthenticated');
    expect(auth.error).toBeNull();
  });

  it('test_bootstrap_503_service_unavailable', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(503, {})));
    await bootstrap();
    expect(auth.status).toBe('unauthenticated');
    expect(auth.error).toBe('service_unavailable');
  });

  it('test_bootstrap_network_error', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('Failed to fetch'); }));
    await bootstrap();
    expect(auth.status).toBe('unauthenticated');
    expect(auth.error).toBe('network');
  });

  it('test_bootstrap_5xx_other_falls_through', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(500, {})));
    await bootstrap();
    expect(auth.status).toBe('unauthenticated');
    expect(auth.error).toBe('http_500');
  });

  it('test_bootstrap_malformed_200_body', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => malformedJsonResponse(200)));
    await bootstrap();
    expect(auth.status).toBe('unauthenticated');
    expect(auth.error).toBe('malformed_response');
  });

  it('test_bootstrap_loading_state_set_first_time', async () => {
    auth.status = 'unauthenticated';
    let observedDuringFetch = null;
    vi.stubGlobal('fetch', vi.fn(async () => {
      observedDuringFetch = auth.status;
      return jsonResponse(401, { error: 'not_authenticated' });
    }));
    await bootstrap();
    expect(observedDuringFetch).toBe('loading');
    expect(auth.status).toBe('unauthenticated');
  });

  it('test_bootstrap_no_loading_flicker_when_authenticated', async () => {
    auth.status = 'authenticated';
    auth.operator = { id: 1, username: 'op', display_name: 'Op', role_hint: 'owner' };
    auth.csrfToken = 'tok';
    let observedDuringFetch = null;
    vi.stubGlobal('fetch', vi.fn(async () => {
      observedDuringFetch = auth.status;
      return jsonResponse(200, {
        operator: { id: 1, username: 'op', display_name: 'Op', role_hint: 'owner' },
        session: {},
        csrf_token: 'tok',
      });
    }));
    await bootstrap();
    expect(observedDuringFetch).toBe('authenticated');
    expect(auth.status).toBe('authenticated');
  });
});


// ---------------------------------------------------------------------------
// 3.3 — login() seven branches (with Retry-After clamp/floor + malformed)
// ---------------------------------------------------------------------------

describe('login()', () => {
  it('test_login_200_authenticated', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse(200, {
        operator: { id: 1, username: 'op', display_name: 'Op', role_hint: 'owner' },
        session: {},
        csrf_token: 'tok',
      })),
    );
    const ok = await login('op', 'pw');
    expect(ok).toBe(true);
    expect(auth.status).toBe('authenticated');
    expect(auth.csrfToken).toBe('tok');
  });

  it('test_login_401_invalid_credentials', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse(401, { error: 'invalid_credentials' })),
    );
    const ok = await login('op', 'wrong');
    expect(ok).toBe(false);
    expect(auth.status).toBe('unauthenticated');
    expect(auth.error).toBe('invalid_credentials');
  });

  it('test_login_429_rate_limited', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse(
        429, { error: 'rate_limited' }, { 'Retry-After': '60' },
      )),
    );
    await login('op', 'pw');
    expect(auth.status).toBe('rate-limited');
    expect(auth.retryAfter).toBe(60);
    expect(auth.error).toBe('rate_limited');
  });

  it('test_login_429_retry_after_clamped_to_3600', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse(
        429, { error: 'rate_limited' }, { 'Retry-After': '99999' },
      )),
    );
    await login('op', 'pw');
    expect(auth.retryAfter).toBe(3600);
  });

  it('test_login_429_retry_after_floor_one', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse(
        429, { error: 'rate_limited' }, { 'Retry-After': null },
      )),
    );
    await login('op', 'pw');
    expect(auth.retryAfter).toBe(1);
  });

  it('test_login_503_service_unavailable', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(503, {})));
    await login('op', 'pw');
    expect(auth.error).toBe('service_unavailable');
    expect(auth.status).toBe('unauthenticated');
  });

  it('test_login_500_generic_http_error', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(500, {})));
    await login('op', 'pw');
    expect(auth.status).toBe('unauthenticated');
    expect(auth.error).toBe('http_500');
  });

  it('test_login_malformed_200_body', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => malformedJsonResponse(200)));
    const ok = await login('op', 'pw');
    expect(ok).toBe(false);
    expect(auth.status).toBe('unauthenticated');
    expect(auth.error).toBe('malformed_response');
  });

  it('test_login_network_error', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('boom'); }));
    const ok = await login('op', 'pw');
    expect(ok).toBe(false);
    expect(auth.error).toBe('network');
  });
});


// ---------------------------------------------------------------------------
// 3.4 — logout() / getCsrfToken() / tickRateLimit() / handleSessionExpired()
// ---------------------------------------------------------------------------

describe('logout()', () => {
  it('test_logout_resets_state_on_204', async () => {
    auth.status = 'authenticated';
    auth.operator = { id: 1, username: 'op', display_name: 'Op', role_hint: 'owner' };
    auth.csrfToken = 'tok';
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(204, null)));
    await logout();
    expect(auth.status).toBe('unauthenticated');
    expect(auth.operator).toBeNull();
    expect(auth.csrfToken).toBeNull();
    expect(disconnect).toHaveBeenCalled();
  });

  it('test_logout_resets_state_on_401', async () => {
    auth.status = 'authenticated';
    auth.operator = { id: 1 };
    auth.csrfToken = 'tok';
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(401, {})));
    await logout();
    expect(auth.status).toBe('unauthenticated');
    expect(auth.operator).toBeNull();
    expect(auth.csrfToken).toBeNull();
  });

  it('test_logout_resets_state_on_503', async () => {
    auth.status = 'authenticated';
    auth.operator = { id: 1 };
    auth.csrfToken = 'tok';
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(503, {})));
    await logout();
    expect(auth.status).toBe('unauthenticated');
    expect(auth.operator).toBeNull();
    expect(auth.csrfToken).toBeNull();
  });

  it('test_logout_resets_state_on_network_error', async () => {
    auth.status = 'authenticated';
    auth.operator = { id: 1 };
    auth.csrfToken = 'tok';
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('boom'); }));
    await logout();
    expect(auth.status).toBe('unauthenticated');
    expect(auth.operator).toBeNull();
    expect(auth.csrfToken).toBeNull();
  });

  it('test_logout_threads_csrf_header', async () => {
    auth.status = 'authenticated';
    auth.csrfToken = 'abc';
    let capturedInit = null;
    vi.stubGlobal('fetch', vi.fn(async (_url, init) => {
      capturedInit = init;
      return jsonResponse(204, null);
    }));
    await logout();
    expect(capturedInit?.headers?.['X-CSRF-Token']).toBe('abc');
  });
});

describe('getCsrfToken()', () => {
  it('test_get_csrf_returns_in_memory_first', () => {
    auth.csrfToken = 'cached';
    document.cookie = 'heimdall_csrf=from-cookie; path=/';
    expect(getCsrfToken()).toBe('cached');
  });

  it('test_get_csrf_falls_back_to_cookie', () => {
    auth.csrfToken = null;
    document.cookie = 'heimdall_csrf=from-cookie; path=/';
    expect(getCsrfToken()).toBe('from-cookie');
    // Re-hydration: subsequent reads return the cached value.
    expect(auth.csrfToken).toBe('from-cookie');
  });

  it('test_get_csrf_returns_null_when_neither', () => {
    auth.csrfToken = null;
    expect(getCsrfToken()).toBeNull();
  });

  it('test_get_csrf_handles_url_encoded_cookie', () => {
    auth.csrfToken = null;
    document.cookie = 'heimdall_csrf=tok%2Bvalue; path=/';
    expect(getCsrfToken()).toBe('tok+value');
  });
});

describe('tickRateLimit()', () => {
  it('test_tick_rate_limit_decrements', () => {
    auth.status = 'rate-limited';
    auth.retryAfter = 5;
    const released = tickRateLimit();
    expect(released).toBe(false);
    expect(auth.retryAfter).toBe(4);
    expect(auth.status).toBe('rate-limited');
  });

  it('test_tick_rate_limit_terminates', () => {
    auth.status = 'rate-limited';
    auth.retryAfter = 1;
    const released = tickRateLimit();
    expect(released).toBe(true);
    expect(auth.retryAfter).toBe(0);
    expect(auth.status).toBe('unauthenticated');
  });

  it('test_tick_rate_limit_noop_when_not_rate_limited', () => {
    auth.status = 'authenticated';
    auth.retryAfter = 0;
    const released = tickRateLimit();
    expect(released).toBe(false);
    expect(auth.status).toBe('authenticated');
  });
});

describe('handleSessionExpired()', () => {
  it('test_handle_session_expired_reprobes_whoami', async () => {
    auth.status = 'authenticated';
    auth.operator = { id: 1 };
    auth.csrfToken = 'tok';
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse(401, { error: 'not_authenticated' })),
    );
    await handleSessionExpired();
    expect(auth.status).toBe('unauthenticated');
  });
});
