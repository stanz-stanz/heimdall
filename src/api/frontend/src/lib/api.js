/** Fetch wrappers for console REST endpoints. */

async function fetchJSON(url) {
  const res = await fetch(url);
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
export const fetchSettings = () => fetchJSON('/console/settings');

export async function saveSettings(name, data) {
  const res = await fetch(`/console/settings/${name}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

export async function sendCommand(command, payload = {}) {
  const res = await fetch(`/console/commands/${command}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}
