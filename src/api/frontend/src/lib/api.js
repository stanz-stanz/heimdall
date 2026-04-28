/** Fetch wrappers for console REST endpoints. */

import { getCsrfToken, handleSessionExpired } from './auth.svelte.js';

// Slice 3g (a)(b)(c) — the SPA login state machine handles 401 by
// re-probing /console/auth/whoami and routing back to the login view.
// callers see a thrown error so their normal failure UI renders while
// the auth module flips auth.status to 'unauthenticated'.
const SESSION_REQUIRED_MESSAGE = 'Session required — log in to continue.';

function csrfHeaders() {
  const token = getCsrfToken();
  return token ? { 'X-CSRF-Token': token } : {};
}

function noteSessionExpired() {
  // Fire-and-forget — the bootstrap probe is async but the fetch
  // throw must surface synchronously. The state transition runs in
  // parallel and re-renders App.svelte once whoami resolves.
  handleSessionExpired().catch(() => {});
}

async function fetchJSON(url) {
  const res = await fetch(url, { credentials: 'same-origin' });
  if (res.status === 401) {
    noteSessionExpired();
    throw new Error(SESSION_REQUIRED_MESSAGE);
  }
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
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
  const res = await fetch(url, init);
  if (res.status === 401) {
    noteSessionExpired();
    throw new Error(SESSION_REQUIRED_MESSAGE);
  }
  if (!res.ok) {
    let detail = '';
    try {
      const errBody = await res.json();
      detail = errBody?.detail ?? errBody?.error ?? '';
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
    headers: { 'Content-Type': 'application/json', ...csrfHeaders() },
    body: JSON.stringify(data),
  });
  if (res.status === 401) {
    noteSessionExpired();
    throw new Error(SESSION_REQUIRED_MESSAGE);
  }
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

export async function sendCommand(command, payload = {}) {
  const res = await fetch(`/console/commands/${command}`, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', ...csrfHeaders() },
    body: JSON.stringify(payload),
  });
  if (res.status === 401) {
    noteSessionExpired();
    throw new Error(SESSION_REQUIRED_MESSAGE);
  }
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
