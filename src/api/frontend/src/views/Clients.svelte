<script>
  import DataTable from '../components/DataTable.svelte';
  import { fetchClients } from '../lib/api.js';
  import { onMount } from 'svelte';

  let rows = $state([]);
  let loaded = $state(false);

  const columns = [
    { key: 'domain', label: 'Domain', class: 'domain' },
    { key: 'company_name', label: 'Company' },
    { key: 'plan', label: 'Plan' },
    { key: 'status', label: 'Status' },
    { key: 'last_scan', label: 'Last Scan' },
    { key: 'open_findings', label: 'Open Findings' },
    { key: 'last_delivery', label: 'Last Delivery' },
  ];

  function escapeHtml(str) {
    if (!str) return '';
    return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  function renderCell(row, key) {
    if (key === 'domain') {
      return `<span class="t-mono-label">${escapeHtml(row.domain)}</span>`;
    }
    if (key === 'plan') {
      const plan = (row.plan ?? '').toLowerCase();
      const cls = plan === 'sentinel' ? 'plan-sentinel' : plan === 'guardian' ? 'plan-guardian' : 'plan-watchman';
      return `<span class="client-plan ${cls}">${escapeHtml((row.plan ?? 'Watchman').toUpperCase())}</span>`;
    }
    if (key === 'status') {
      return `<span class="badge badge-new">${escapeHtml(row.status ?? 'Active')}</span>`;
    }
    if (key === 'open_findings') {
      return `<span style="font-family: var(--mono)">${row.open_findings ?? 0}</span>`;
    }
    if (key === 'last_delivery') {
      const date = row.last_delivery ?? '';
      if (!date) return '<span style="color: var(--text-muted)">--</span>';
      return escapeHtml(date);
    }
    if (key === 'last_scan') {
      return escapeHtml(row.last_scan ?? '--');
    }
    return escapeHtml(row[key] ?? '');
  }

  onMount(async () => {
    try {
      rows = await fetchClients();
    } catch (err) {
      console.error('Clients fetch failed:', err);
    }
    loaded = true;
  });
</script>

<div class="section-header" style="margin-top: 0;">
  <span class="section-title">Onboarded Clients</span>
</div>

<DataTable {columns} {rows} {renderCell} />
