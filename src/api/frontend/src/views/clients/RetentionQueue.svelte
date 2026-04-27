<!--
  V6 — Retention Queue.

  Pending+due retention jobs (status='pending' AND scheduled_for <= now).
  Operator can:
    - Force run: advance scheduled_for to now (cron picks up on next
      tick, ≤5 min).
    - Cancel: pending → cancelled (atomic CAS — bails out 404 if the
      cron beat us).
    - Retry: failed → pending. (Strict-spec V6 doesn't surface failed
      rows, so this button effectively dark-ships in this slice. The
      backend supports it for the eventual "show failed" widening.)

  Refresh model: same as TrialExpiring — fetch on mount, refetch on
  window focus, plus a manual reload button. After every successful
  action the list is refetched.
-->

<script>
  import DataTable from '../../components/DataTable.svelte';
  import ConfirmModal from '../../components/ConfirmModal.svelte';
  import {
    fetchRetentionQueue,
    forceRunRetentionJob,
    cancelRetentionJob,
    retryRetentionJob,
  } from '../../lib/api.js';
  import { onMount, onDestroy } from 'svelte';

  let { onCount = null } = $props();

  let rows = $state([]);
  let loaded = $state(false);
  let error = $state('');

  // Modal state — single shared modal driven by a pending-action object.
  let modalOpen = $state(false);
  let modalTitle = $state('');
  let modalBody = $state('');
  let modalConfirmLabel = $state('Confirm');
  let modalAction = $state(null); // () => Promise<void>

  const columns = [
    { key: 'id', label: 'ID' },
    { key: 'cvr', label: 'CVR' },
    { key: 'company_name', label: 'Company' },
    { key: 'action', label: 'Action' },
    { key: 'scheduled_for', label: 'Scheduled For' },
    { key: 'status', label: 'Status' },
    { key: 'actions', label: 'Actions' },
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
    if (key === 'id') {
      return `<span class="t-mono-label">#${row.id}</span>`;
    }
    if (key === 'cvr') {
      return `<span class="t-mono-label">${escapeHtml(row.cvr)}</span>`;
    }
    if (key === 'company_name') {
      return escapeHtml(row.company_name ?? '--');
    }
    if (key === 'action') {
      return `<span class="badge badge-new">${escapeHtml(row.action)}</span>`;
    }
    if (key === 'scheduled_for') {
      return `<span class="t-mono-label">${escapeHtml(shortDate(row.scheduled_for))}</span>`;
    }
    if (key === 'status') {
      const cls = row.status === 'failed' ? 'badge-critical'
        : row.status === 'running' ? 'badge-high'
        : 'badge-new';
      return `<span class="badge ${cls}">${escapeHtml(row.status)}</span>`;
    }
    if (key === 'actions') {
      // Action buttons rendered separately via Svelte (not raw HTML)
      // so the click handlers stay reactive — return a placeholder.
      return `<span data-actions-row="${row.id}"></span>`;
    }
    return escapeHtml(row[key] ?? '');
  }

  async function load() {
    loaded = false;
    error = '';
    try {
      const data = await fetchRetentionQueue();
      if (Array.isArray(data)) {
        rows = data;
      } else {
        rows = [];
        error = data?.error ?? 'Failed to load retention queue';
      }
    } catch (err) {
      error = `Failed to load retention queue: ${err.message}`;
      rows = [];
    }
    loaded = true;
    if (onCount) onCount(rows.length);
  }

  function openConfirm({ title, body, confirmLabel, action }) {
    modalTitle = title;
    modalBody = body;
    modalConfirmLabel = confirmLabel;
    modalAction = action;
    modalOpen = true;
  }

  async function runAction(fn, id, label) {
    try {
      await fn(id);
      await load();
    } catch (err) {
      error = `${label} failed (#${id}): ${err.message}`;
    }
  }

  function confirmForceRun(row) {
    openConfirm({
      title: `Force-run retention job #${row.id}?`,
      body: `Advance scheduled_for to now. The cron will claim within ≤5 min and execute action “${row.action}” for CVR ${row.cvr}.`,
      confirmLabel: 'Force run',
      action: () => runAction(forceRunRetentionJob, row.id, 'Force run'),
    });
  }

  function confirmCancel(row) {
    openConfirm({
      title: `Cancel retention job #${row.id}?`,
      body: `This cannot be undone. A new retention schedule must be created manually if you need it back. (CVR ${row.cvr}, action “${row.action}”.)`,
      confirmLabel: 'Cancel job',
      action: () => runAction(cancelRetentionJob, row.id, 'Cancel'),
    });
  }

  function confirmRetry(row) {
    openConfirm({
      title: `Retry failed job #${row.id}?`,
      body: `Re-queue the job for the cron to retry on next tick.`,
      confirmLabel: 'Retry',
      action: () => runAction(retryRetentionJob, row.id, 'Retry'),
    });
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

  // Modal style is destructive for force-run + cancel (both delete
  // user data downstream) and default for retry.
  let modalStyle = $derived(
    modalConfirmLabel === 'Retry' ? 'default' : 'destructive',
  );
</script>

<div class="section-header" style="margin-top: 0;">
  <span class="section-title">Retention Queue (pending and due)</span>
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
      No retention jobs pending and due. The cron is caught up.
    </span>
  </div>
{:else}
  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          {#each columns as col}
            <th>{col.label}</th>
          {/each}
        </tr>
      </thead>
      <tbody>
        {#each rows as row (row.id)}
          <tr>
            {#each columns as col}
              {#if col.key === 'actions'}
                <td>
                  <div class="row-actions">
                    {#if row.status === 'pending'}
                      <button
                        class="btn btn-ghost btn-sm"
                        onclick={() => confirmForceRun(row)}
                      >
                        Force run
                      </button>
                      <button
                        class="btn btn-ghost btn-sm"
                        onclick={() => confirmCancel(row)}
                      >
                        Cancel
                      </button>
                    {/if}
                    {#if row.status === 'failed'}
                      <button
                        class="btn btn-ghost btn-sm"
                        onclick={() => confirmRetry(row)}
                      >
                        Retry
                      </button>
                    {/if}
                  </div>
                </td>
              {:else}
                <td class={col.class ?? ''}>
                  {@html renderCell(row, col.key)}
                </td>
              {/if}
            {/each}
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
{/if}

<ConfirmModal
  bind:open={modalOpen}
  title={modalTitle}
  body={modalBody}
  confirmLabel={modalConfirmLabel}
  confirmStyle={modalStyle}
  onConfirm={() => modalAction && modalAction()}
/>

<style>
  .row-actions {
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
  }
</style>
