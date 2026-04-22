<script>
  import DataTable from '../components/DataTable.svelte';
  import { fetchBriefs } from '../lib/api.js';
  import { router } from '../lib/router.svelte.js';
  import { onMount } from 'svelte';

  let rows = $state([]);
  let loaded = $state(false);
  let error = $state('');

  let criticalOnly = $derived(router.params?.critical === '1');

  const columns = [
    { key: 'domain', label: 'Domain', class: 'domain' },
    { key: 'bucket', label: 'Bucket' },
    { key: 'cms', label: 'CMS' },
    { key: 'hosting', label: 'Hosting' },
    { key: 'severity', label: 'Severity' },
    { key: 'finding_count', label: 'Findings' },
    { key: 'scan_date', label: 'Scan date' },
  ];

  function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    return String(str)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  function renderCell(row, key) {
    if (key === 'domain') {
      return `<span class="t-mono-label">${escapeHtml(row.domain)}</span>`;
    }
    if (key === 'bucket') {
      return row.bucket ? `<span class="badge-bucket">${escapeHtml(row.bucket)}</span>` : '';
    }
    if (key === 'severity') {
      const parts = [];
      if ((row.critical_count ?? 0) > 0)
        parts.push(`<span class="badge badge-critical">${row.critical_count} critical</span>`);
      if ((row.high_count ?? 0) > 0)
        parts.push(`<span class="badge badge-high">${row.high_count} high</span>`);
      if ((row.medium_count ?? 0) > 0)
        parts.push(`<span class="badge badge-medium">${row.medium_count} medium</span>`);
      return parts.length ? parts.join(' ') : '<span style="color: var(--text-muted)">--</span>';
    }
    if (key === 'finding_count') {
      return `<span class="t-mono-label">${row.finding_count ?? 0}</span>`;
    }
    if (key === 'scan_date') {
      return `<span class="t-mono-label">${escapeHtml(row.scan_date ?? '')}</span>`;
    }
    return escapeHtml(row[key] ?? '');
  }

  async function load() {
    loaded = false;
    error = '';
    try {
      rows = await fetchBriefs(criticalOnly, 500);
    } catch (err) {
      error = `Failed to load briefs: ${err.message}`;
      rows = [];
    }
    loaded = true;
  }

  onMount(load);

  // Refetch when the critical filter toggles (e.g. Dashboard → Briefs, then Dashboard → Critical)
  $effect(() => {
    // depend on criticalOnly
    const _ = criticalOnly;
    load();
  });
</script>

<div class="section-header" style="margin-top: 0;">
  <span class="section-title">
    {criticalOnly ? 'Critical Briefs' : 'Current Briefs'}
  </span>
  {#if loaded}
    <span class="t-label" style="color: var(--text-dim);">{rows.length} total</span>
  {/if}
</div>

{#if criticalOnly}
  <div class="filter-banner t-label">
    Filtered: briefs with at least one critical finding
    <button
      class="btn btn-ghost btn-sm filter-clear"
      onclick={() => (window.location.hash = '#/briefs')}
    >
      Clear
    </button>
  </div>
{/if}

{#if error}
  <div class="card" style="margin-bottom: 16px; border-color: var(--red-dim);">
    <span class="t-body" style="color: var(--red);">{error}</span>
  </div>
{/if}

{#if !loaded}
  <div class="empty-state">
    <span class="empty-state-text">Loading briefs…</span>
  </div>
{:else if rows.length === 0}
  <div class="empty-state">
    <span class="empty-state-text">
      {criticalOnly ? 'No briefs with critical findings.' : 'No briefs yet — run the pipeline to generate them.'}
    </span>
  </div>
{:else}
  <DataTable {columns} {rows} {renderCell} />
{/if}

<style>
  .filter-banner {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 12px;
    margin-bottom: 12px;
    background: var(--gold-glow);
    border: 1px solid var(--gold);
    border-radius: var(--radius-sm);
    color: var(--gold);
  }

  .filter-clear {
    margin-left: auto;
  }
</style>
