/** Fetch wrappers for console REST endpoints. */

async function fetchJSON(url) {
  const res = await fetch(url, { credentials: 'same-origin' });
  if (res.status === 401) {
    window.location.reload();
    throw new Error('Authentication required');
  }
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
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
