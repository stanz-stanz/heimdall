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
