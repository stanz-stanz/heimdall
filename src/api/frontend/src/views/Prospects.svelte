<script>
  import FilterChips from '../components/FilterChips.svelte';
  import DataTable from '../components/DataTable.svelte';
  import { fetchProspects, fetchCampaigns } from '../lib/api.js';
  import { getSelectedCampaign, setSelectedCampaign } from './prospects-state.svelte.js';
  import { onMount } from 'svelte';

  let campaigns = $state([]);
  let rows = $state([]);
  let activeFilter = $state('all');
  let loaded = $state(false);

  const filterOptions = [
    { label: 'All', value: 'all' },
    { label: 'New', value: 'new' },
    { label: 'Interpreted', value: 'interpreted' },
    { label: 'Sent', value: 'sent' },
  ];

  const columns = [
    { key: 'domain', label: 'Domain', class: 'domain' },
    { key: 'company_name', label: 'Company' },
    { key: 'bucket', label: 'Bucket' },
    { key: 'finding_count', label: 'Findings' },
    { key: 'severity', label: 'Severity' },
    { key: 'outreach_status', label: 'Status' },
  ];

  function escapeHtml(str) {
    if (!str) return '';
    return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  function renderCell(row, key) {
    if (key === 'domain') {
      return `<span class="t-mono-label">${escapeHtml(row.domain)}</span>`;
    }
    if (key === 'bucket') {
      return `<span class="badge-bucket">${escapeHtml(row.bucket)}</span>`;
    }
    if (key === 'finding_count') {
      return `<span style="font-family: var(--mono)">${row.finding_count ?? 0}</span>`;
    }
    if (key === 'severity') {
      let parts = [];
      if (row.critical_count > 0) {
        parts.push(`<span class="badge badge-critical">${row.critical_count} critical</span>`);
      }
      if (row.high_count > 0) {
        parts.push(`<span class="badge badge-high">${row.high_count} high</span>`);
      }
      return parts.length > 0 ? parts.join(' ') : '<span style="color: var(--text-muted)">--</span>';
    }
    if (key === 'outreach_status') {
      const status = (row.outreach_status ?? 'new').toLowerCase();
      const variant = status === 'sent' ? 'sent' : status === 'interpreted' ? 'interpreted' : 'new';
      const label = status.charAt(0).toUpperCase() + status.slice(1);
      return `<span class="badge badge-${variant}">${escapeHtml(label)}</span>`;
    }
    return escapeHtml(row[key] ?? '');
  }

  async function loadProspects() {
    const campaign = getSelectedCampaign();
    if (!campaign) return;
    loaded = false;
    try {
      const statusFilter = activeFilter === 'all' ? '' : activeFilter;
      rows = await fetchProspects(campaign, statusFilter, 100, 0);
    } catch (err) {
      console.error('Prospects fetch failed:', err);
      rows = [];
    }
    loaded = true;
  }

  function handleFilterSelect(value) {
    activeFilter = value;
    loadProspects();
  }

  function handleCampaignSelect(event) {
    setSelectedCampaign(event.target.value);
    loadProspects();
  }

  onMount(async () => {
    try {
      campaigns = await fetchCampaigns();
    } catch (err) {
      console.error('Campaigns list fetch failed:', err);
    }

    if (getSelectedCampaign()) {
      await loadProspects();
    } else {
      loaded = true;
    }
  });

  let currentCampaign = $derived(getSelectedCampaign());
</script>

<div class="section-header" style="margin-top: 0;">
  <span class="section-title">
    Prospects
    {#if currentCampaign}
      — {currentCampaign}
    {/if}
  </span>
  <FilterChips options={filterOptions} active={activeFilter} onSelect={handleFilterSelect} />
</div>

{#if !currentCampaign}
  <div class="card" style="margin-bottom: 20px;">
    <label class="form-label t-label" for="campaign-select">Select Campaign</label>
    <select id="campaign-select" class="form-select t-body" onchange={handleCampaignSelect}>
      <option value="">-- Select a campaign --</option>
      {#each campaigns as c}
        <option value={c.campaign}>{c.campaign} ({c.total} prospects)</option>
      {/each}
    </select>
  </div>
{/if}

{#if currentCampaign}
  <DataTable {columns} {rows} {renderCell} />
{:else if loaded}
  <div class="empty-state">
    <span class="empty-state-text">Select a campaign to view prospects</span>
  </div>
{/if}

<style>
  .form-label {
    display: block;
    color: var(--text-dim);
    margin-bottom: 6px;
  }

  .form-select {
    background: var(--bg-surface);
    border: 1px solid var(--border);
    color: var(--text);
    border-radius: var(--radius-sm);
    padding: 8px 12px;
    width: 100%;
    max-width: 400px;
  }

  .form-select:focus {
    outline: none;
    border-color: var(--gold);
  }
</style>
