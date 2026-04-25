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
