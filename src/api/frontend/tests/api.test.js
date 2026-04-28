/**
 * Integration tests for `src/lib/api.js`.
 *
 * Stage A slice 3g.5 §5.1 (12 tests). Spec citation: slice 3g spec
 * §3.3 (CSRF threading), §3.4 (mid-session 401 redirect), §3.5
 * (helper error shapes) + master spec §4.4 (CSRF defense).
 *
 * Locks the wire shape of `lib/api.js`: which helpers send X-CSRF-Token,
 * which don't, and how 401 / 403 / 5xx are surfaced. The
 * `handleSessionExpired` import is mocked so we can assert it is called
 * (or not) per response code without triggering a real whoami probe.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock ws.svelte.js because auth.svelte.js imports it.
vi.mock('$lib/ws.svelte.js', () => ({
  connect: vi.fn(),
  disconnect: vi.fn(),
}));

// Mock auth.svelte.js BEFORE importing lib/api.js so the api module's
// `import { getCsrfToken, handleSessionExpired } from './auth.svelte.js'`
// resolves to controllable mocks.
vi.mock('$lib/auth.svelte.js', () => {
  const auth = {
    status: 'authenticated',
    operator: null,
    csrfToken: null,
    retryAfter: 0,
    error: null,
  };
  return {
    auth,
    bootstrap: vi.fn(),
    login: vi.fn(),
    logout: vi.fn(),
    getCsrfToken: vi.fn(() => null),
    handleSessionExpired: vi.fn(async () => {}),
    tickRateLimit: vi.fn(),
  };
});

import * as api from '$lib/api.js';
import { auth, getCsrfToken, handleSessionExpired } from '$lib/auth.svelte.js';

const { fetchDashboard } = api;


function jsonResponse(status, body, headers = {}) {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: `HTTP ${status}`,
    headers: {
      get: (name) => headers[name] ?? headers[name?.toLowerCase()] ?? null,
    },
    json: async () => body,
  };
}


beforeEach(() => {
  vi.clearAllMocks();
  vi.restoreAllMocks();
  auth.status = 'authenticated';
  auth.csrfToken = null;
  document.cookie = 'heimdall_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/';
  getCsrfToken.mockImplementation(() => null);
  handleSessionExpired.mockImplementation(async () => {});
});


describe('CSRF threading', () => {
  it('test_post_threads_csrf_when_token_present', async () => {
    getCsrfToken.mockImplementation(() => 'tok');
    let capturedInit = null;
    vi.stubGlobal('fetch', vi.fn(async (_url, init) => {
      capturedInit = init;
      return jsonResponse(200, { ok: true });
    }));
    // Use sendCommand which is the public POST wrapper that routes
    // through postJSON internally.
    await api.sendCommand('reload', { a: 1 });
    expect(capturedInit?.headers?.['X-CSRF-Token']).toBe('tok');
  });

  it('test_post_omits_csrf_when_token_null', async () => {
    getCsrfToken.mockImplementation(() => null);
    let capturedInit = null;
    vi.stubGlobal('fetch', vi.fn(async (_url, init) => {
      capturedInit = init;
      return jsonResponse(200, { ok: true });
    }));
    await api.forceRunRetentionJob('job-1');
    expect(capturedInit?.headers?.['X-CSRF-Token']).toBeUndefined();
  });

  it('test_post_uses_cookie_fallback_csrf', async () => {
    // Simulate getCsrfToken's cookie-fallback path returning the
    // cookie value when memory is null.
    getCsrfToken.mockImplementation(() => 'cookie-tok');
    let capturedInit = null;
    vi.stubGlobal('fetch', vi.fn(async (_url, init) => {
      capturedInit = init;
      return jsonResponse(200, { ok: true });
    }));
    await api.forceRunRetentionJob('job-1');
    expect(capturedInit?.headers?.['X-CSRF-Token']).toBe('cookie-tok');
  });

  it('test_save_settings_threads_csrf', async () => {
    getCsrfToken.mockImplementation(() => 'tok');
    let capturedInit = null;
    vi.stubGlobal('fetch', vi.fn(async (_url, init) => {
      capturedInit = init;
      return jsonResponse(200, { ok: true });
    }));
    await api.saveSettings('foo', { a: 1 });
    expect(capturedInit?.method).toBe('PUT');
    expect(capturedInit?.headers?.['X-CSRF-Token']).toBe('tok');
    expect(capturedInit?.headers?.['Content-Type']).toBe('application/json');
  });

  it('test_send_command_threads_csrf', async () => {
    getCsrfToken.mockImplementation(() => 'tok');
    let capturedInit = null;
    vi.stubGlobal('fetch', vi.fn(async (_url, init) => {
      capturedInit = init;
      return jsonResponse(200, { ok: true });
    }));
    await api.sendCommand('reload', { a: 1 });
    expect(capturedInit?.method).toBe('POST');
    expect(capturedInit?.headers?.['X-CSRF-Token']).toBe('tok');
    expect(capturedInit?.headers?.['Content-Type']).toBe('application/json');
  });

  it('test_fetch_json_does_not_send_csrf', async () => {
    getCsrfToken.mockImplementation(() => 'tok');
    let capturedInit = null;
    vi.stubGlobal('fetch', vi.fn(async (_url, init) => {
      capturedInit = init;
      return jsonResponse(200, { prospects: 1 });
    }));
    await fetchDashboard();
    expect(capturedInit?.headers).toBeFalsy();
  });
});


describe('Mid-session 401 → handleSessionExpired', () => {
  it('test_post_401_calls_handle_session_expired', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(401, {})));
    await expect(api.forceRunRetentionJob('job-1')).rejects.toThrow(
      'Session required — log in to continue.',
    );
    expect(handleSessionExpired).toHaveBeenCalledTimes(1);
  });

  it('test_save_settings_401_calls_handle_session_expired', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(401, {})));
    await expect(api.saveSettings('foo', { a: 1 })).rejects.toThrow(
      'Session required — log in to continue.',
    );
    expect(handleSessionExpired).toHaveBeenCalledTimes(1);
  });

  it('test_send_command_401_calls_handle_session_expired', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(401, {})));
    await expect(api.sendCommand('reload')).rejects.toThrow(
      'Session required — log in to continue.',
    );
    expect(handleSessionExpired).toHaveBeenCalledTimes(1);
  });

  it('test_fetch_json_401_calls_handle_session_expired', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(401, {})));
    await expect(fetchDashboard()).rejects.toThrow(
      'Session required — log in to continue.',
    );
    expect(handleSessionExpired).toHaveBeenCalledTimes(1);
  });
});


describe('Non-401 error shapes', () => {
  it('test_post_403_csrf_mismatch_does_not_logout', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(
      403, { error: 'csrf_mismatch' },
    )));
    await expect(api.forceRunRetentionJob('job-1')).rejects.toThrow(
      /csrf_mismatch/,
    );
    expect(handleSessionExpired).not.toHaveBeenCalled();
    expect(auth.status).toBe('authenticated');
  });

  it('test_post_500_throws_status_error', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(
      500, { detail: 'oops' },
    )));
    await expect(api.forceRunRetentionJob('job-1')).rejects.toThrow(
      /500.*oops/,
    );
    expect(handleSessionExpired).not.toHaveBeenCalled();
  });
});
