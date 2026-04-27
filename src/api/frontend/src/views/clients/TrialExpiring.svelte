<!--
  V1 — Trial Expiring.

  Read-only list of Watchman trials that are within the look-ahead
  window (default 7 days) AND have not engaged with the Sentinel
  upgrade flow. Used by the operator to spot trials that need a
  manual nudge before the retention cron purges them.

  No row-level actions in this slice — Federico chose read-only.
  Operator messages clients out-of-band via Telegram.

  Refresh model: fetch on mount + reload button + refetch on window
  focus regain.
-->

<script>
  import DataTable from '../../components/DataTable.svelte';
  import { fetchTrialExpiring } from '../../lib/api.js';
  import { onMount, onDestroy } from 'svelte';

  let { onCount = null } = $props();

  let rows = $state([]);
  let loaded = $state(false);
  let error = $state('');

  const columns = [
    { key: 'company_name', label: 'Company' },
    { key: 'domain', label: 'Domain', class: 'domain' },
    { key: 'trial_started_at', label: 'Started' },
    { key: 'trial_expires_at', label: 'Expires' },
    { key: 'days_remaining', label: 'Days Left' },
    { key: 'telegram_chat_id', label: 'Telegram?' },
  ];

  function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    return String(str)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  function shortDate(iso) {
    if (!iso) return '--';
    return iso.replace('T', ' ').slice(0, 16);
  }

  function renderCell(row, key) {
    if (key === 'domain') {
      return row.domain
        ? `<span class="t-mono-label">${escapeHtml(row.domain)}</span>`
        : '<span style="color: var(--text-muted)">--</span>';
    }
    if (key === 'trial_started_at' || key === 'trial_expires_at') {
      return `<span class="t-mono-label">${escapeHtml(shortDate(row[key]))}</span>`;
    }
    if (key === 'days_remaining') {
      const d = row.days_remaining ?? 0;
      const cls = d <= 2 ? 'badge-critical' : d <= 4 ? 'badge-high' : 'badge-medium';
      return `<span class="badge ${cls}">${d}d</span>`;
    }
    if (key === 'telegram_chat_id') {
      return row.telegram_chat_id
        ? '<span class="badge badge-new">linked</span>'
        : '<span style="color: var(--text-muted)">no</span>';
    }
    if (key === 'company_name') {
      return escapeHtml(row.company_name ?? '--');
    }
    return escapeHtml(row[key] ?? '');
  }

  async function load() {
    loaded = false;
    error = '';
    try {
      const data = await fetchTrialExpiring(7);
      // The endpoint returns either a list (success) or a {error,detail}
      // dict (DB unavailable / corruption). Normalise both shapes.
      if (Array.isArray(data)) {
        rows = data;
      } else {
        rows = [];
        error = data?.error ?? 'Failed to load trials';
      }
    } catch (err) {
      error = `Failed to load trials: ${err.message}`;
      rows = [];
    }
    loaded = true;
    if (onCount) onCount(rows.length);
  }

  function onWindowFocus() {
    load();
  }

  onMount(() => {
    load();
    if (typeof window !== 'undefined') {
      window.addEventListener('focus', onWindowFocus);
    }
  });

  onDestroy(() => {
    if (typeof window !== 'undefined') {
      window.removeEventListener('focus', onWindowFocus);
    }
  });
</script>

<div class="section-header" style="margin-top: 0;">
  <span class="section-title">Trial Expiring (≤7 days, no conversion intent)</span>
  <button class="btn btn-ghost btn-sm" onclick={load} disabled={!loaded}>
    Reload
  </button>
</div>

{#if error}
  <div class="card" style="margin-bottom: 16px; border-color: var(--red-dim);">
    <span class="t-body" style="color: var(--red);">{error}</span>
  </div>
{/if}

{#if !loaded}
  <div class="empty-state">
    <span class="empty-state-text">Loading…</span>
  </div>
{:else if rows.length === 0}
  <div class="empty-state">
    <span class="empty-state-text">
      No Watchman trials expiring in the next 7 days without conversion engagement.
    </span>
  </div>
{:else}
  <DataTable {columns} {rows} {renderCell} />
{/if}
