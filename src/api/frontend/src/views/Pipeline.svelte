<script>
  import ProgressBar from '../components/ProgressBar.svelte';
  import { fetchPipelineLast, sendCommand } from '../lib/api.js';
  import { wsState } from '../lib/ws.svelte.js';
  import { onMount, untrack } from 'svelte';

  let running = $state(false);
  let progress = $state({ pct: 0, label: '', message: '' });
  let showProgress = $state(false);
  let lastRun = $state(null);
  let error = $state('');

  function formatDuration(ms) {
    if (!ms) return '--';
    const minutes = Math.round(ms / 60000);
    return minutes > 0 ? `${minutes}m` : '<1m';
  }

  function formatDate(dateStr) {
    if (!dateStr) return '--';
    return dateStr.replace('T', ' ').substring(0, 16);
  }

  async function handleRunPipeline() {
    running = true;
    showProgress = true;
    error = '';
    progress = { pct: 0, label: '0%', message: 'Starting pipeline...' };
    try {
      await sendCommand('run-pipeline');
    } catch (err) {
      error = `Failed to start pipeline: ${err.message}`;
      running = false;
      showProgress = false;
    }
  }

  onMount(async () => {
    try {
      const data = await fetchPipelineLast();
      if (data && data.status !== 'no_runs') {
        lastRun = data;
      }
    } catch (err) {
      console.error('Pipeline last run fetch failed:', err);
    }
  });

  // Listen for WebSocket pipeline events
  $effect(() => {
    const msg = wsState.lastMessage;
    if (!msg) return;

    untrack(() => {
      if (msg.type === 'pipeline_progress' && msg.payload) {
        const p = msg.payload;
        const pct = p.pct ?? p.percent ?? 0;
        showProgress = true;
        progress = {
          pct,
          label: `${Math.round(pct)}%`,
          message: p.message ?? `Scanning domain ${p.current ?? ''}/${p.total ?? ''}: ${p.domain ?? ''}`,
        };
      }

      if (msg.type === 'command_result' && msg.payload?.command === 'run-pipeline') {
        running = false;
        if (msg.payload.status === 'completed' || msg.payload.status === 'ok') {
          showProgress = false;
          fetchPipelineLast().then(data => {
            if (data && data.status !== 'no_runs') lastRun = data;
          }).catch(() => {});
        }
      }

      if (msg.type === 'pipeline_complete') {
        running = false;
        showProgress = false;
        fetchPipelineLast().then(data => {
          if (data && data.status !== 'no_runs') lastRun = data;
        }).catch(() => {});
      }
    });
  });
</script>

<div class="card" style="margin-bottom: 20px;">
  <div style="display: flex; justify-content: space-between; align-items: center;">
    <div>
      <div class="card-label">Prospecting Pipeline</div>
      <div class="card-sub" style="margin-top: 6px;">
        Scans all domains from CVR extract. Produces briefs and prospect list.
      </div>
    </div>
    <button
      class="btn btn-primary"
      onclick={handleRunPipeline}
      disabled={running}
    >
      {running ? 'Running...' : 'Run Pipeline'}
    </button>
  </div>
</div>

{#if error}
  <div class="card" style="margin-bottom: 20px; border-color: var(--red-dim);">
    <span style="color: var(--red); font-size: 13px;">{error}</span>
  </div>
{/if}

{#if showProgress}
  <div style="margin-bottom: 20px;">
    <ProgressBar pct={progress.pct} label={progress.label} message={progress.message} />
  </div>
{/if}

{#if lastRun}
  <div class="section-header">
    <span class="section-title">Last Run</span>
    <span style="font-size: 11px; color: var(--text-muted);">{formatDate(lastRun.run_date)}</span>
  </div>

  <div class="grid grid-4">
    <div class="card">
      <div class="card-label">Domains</div>
      <div class="card-value" style="color: var(--text)">
        {(lastRun.domain_count ?? 0).toLocaleString()}
      </div>
    </div>
    <div class="card">
      <div class="card-label">Findings</div>
      <div class="card-value" style="color: var(--text)">
        {(lastRun.finding_count ?? 0).toLocaleString()}
      </div>
    </div>
    <div class="card">
      <div class="card-label">Critical</div>
      <div class="card-value" style="color: var(--gold)">
        {(lastRun.critical_count ?? 0).toLocaleString()}
      </div>
    </div>
    <div class="card">
      <div class="card-label">Duration</div>
      <div class="card-value" style="color: var(--text)">
        {formatDuration(lastRun.total_duration_ms)}
      </div>
    </div>
  </div>
{:else}
  <div class="empty-state">
    <span class="empty-state-text">No pipeline runs yet</span>
  </div>
{/if}

<style>
  button:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
</style>
