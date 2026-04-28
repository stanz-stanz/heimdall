/** Fetch wrappers for console REST endpoints. */

// Stage A slice 3f transitional behaviour: 401 from /console/* used
// to call window.location.reload() to re-trigger the legacy Basic
// Auth dialog. Under SessionAuthMiddleware no such dialog exists, so
// reloading produces an infinite 401-reload loop in browsers without
// an existing session cookie. Throw instead — callers render the
// error in their normal failure UI. The SPA login slice (next)
// replaces this with a proper redirect to the login view; until then
// "Session required — flip HEIMDALL_LEGACY_BASIC_AUTH=1 on the Pi5
// for UI access" is the operator-facing instruction.
const SESSION_REQUIRED_MESSAGE =
  'Session required — log in via the legacy Basic Auth path until the SPA login slice ships.';

async function fetchJSON(url) {
  const res = await fetch(url, { credentials: 'same-origin' });
  if (res.status === 401) {
    throw new Error(SESSION_REQUIRED_MESSAGE);
  }
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

async function postJSON(url, body = null) {
  const init = {
    method: 'POST',
    credentials: 'same-origin',
  };
  if (body !== null && body !== undefined) {
    init.headers = { 'Content-Type': 'application/json' };
    init.body = JSON.stringify(body);
  }
  const res = await fetch(url, init);
  if (res.status === 401) {
    throw new Error(SESSION_REQUIRED_MESSAGE);
  }
  if (!res.ok) {
    let detail = '';
    try {
      const body = await res.json();
      detail = body?.detail ?? '';
    } catch {
      // ignore
    }
    const suffix = detail ? `: ${detail}` : '';
    throw new Error(`${res.status} ${res.statusText}${suffix}`);
  }
  return res.json();
}

export const fetchDashboard = () => fetchJSON('/console/dashboard');
export const fetchPipelineLast = () => fetchJSON('/console/pipeline/last');
export const fetchCampaigns = () => fetchJSON('/console/campaigns');

export const fetchProspects = (campaign, status, limit = 50, offset = 0) => {
  const params = new URLSearchParams({ limit, offset });
  if (status) params.set('status', status);
  return fetchJSON(`/console/campaigns/${encodeURIComponent(campaign)}/prospects?${params}`);
};

export const fetchClients = () => fetchJSON('/console/clients/list');

export const fetchBriefs = (criticalOnly = false, limit = 200) => {
  const params = new URLSearchParams({ limit });
  if (criticalOnly) params.set('critical', 'true');
  return fetchJSON(`/console/briefs/list?${params}`);
};
export const fetchLogs = (limit = 200) => fetchJSON(`/console/logs?limit=${limit}`);
export const fetchSettings = () => fetchJSON('/console/settings');

export async function saveSettings(name, data) {
  const res = await fetch(`/console/settings/${name}`, {
    method: 'PUT',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

export async function sendCommand(command, payload = {}) {
  const res = await fetch(`/console/commands/${command}`, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

// Operator-console V1 / V6 wrappers
export const fetchTrialExpiring = (windowDays = 7) =>
  fetchJSON(`/console/clients/trial-expiring?window_days=${windowDays}`);

export const fetchRetentionQueue = (limit = 200, offset = 0) =>
  fetchJSON(`/console/clients/retention-queue?limit=${limit}&offset=${offset}`);

export const forceRunRetentionJob = (id) =>
  postJSON(`/console/retention-jobs/${id}/force-run`);

export const cancelRetentionJob = (id, notes = null) =>
  postJSON(`/console/retention-jobs/${id}/cancel`, notes ? { notes } : null);

export const retryRetentionJob = (id) =>
  postJSON(`/console/retention-jobs/${id}/retry`);
