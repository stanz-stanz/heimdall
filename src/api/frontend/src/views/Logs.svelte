<script>
  import { wsState } from '../lib/ws.svelte.js';
  import { fetchLogs } from '../lib/api.js';
  import { onMount, untrack } from 'svelte';

  const MAX_ENTRIES = 5000;

  const LEVEL_ORDER = { DEBUG: 0, INFO: 1, WARNING: 2, ERROR: 3 };

  const SOURCES = [
    { key: 'all', label: 'All', color: null },
    { key: 'api', label: 'API', color: 'var(--blue)' },
    { key: 'worker', label: 'Worker', color: 'var(--green)' },
    { key: 'delivery', label: 'Delivery', color: 'var(--gold)' },
    { key: 'scheduler', label: 'Sched', color: 'var(--orange)' },
    { key: 'ct-collector', label: 'CT', color: 'var(--text-muted)' },
  ];

  const LEVELS = ['All', 'ERROR', 'WARNING', 'INFO'];

  const TIMEFRAMES = [
    { key: 'all', label: 'All time', seconds: 0 },
    { key: '1m', label: 'Last 1m', seconds: 60 },
    { key: '5m', label: 'Last 5m', seconds: 300 },
    { key: '10m', label: 'Last 10m', seconds: 600 },
    { key: '30m', label: 'Last 30m', seconds: 1800 },
  ];

  let allEntries = $state([]);
  let totalCount = $state(0);
  let loaded = $state(false);

  // Filters
  let activeSources = $state(new Set(['all']));
  let minLevel = $state('All');
  let activeTimeframe = $state('all');
  let searchText = $state('');

  // Auto-scroll
  let logEl = $state(null);
  let userScrolledUp = $state(false);
  let prevAllEntriesLength = $state(0);

  let filtered = $derived(filterEntries(allEntries, activeSources, minLevel, activeTimeframe, searchText));

  function matchSource(entrySource, filterKey) {
    const src = (entrySource ?? '').toLowerCase();
    // 'worker' prefix match covers worker-1, worker-2, worker-3
    if (filterKey === 'worker') return src === 'worker' || src.startsWith('worker-');
    // 'ct-collector' exact match
    if (filterKey === 'ct-collector') return src === 'ct-collector' || src === 'ct';
    // All others: exact match
    return src === filterKey;
  }

  function filterEntries(entries, sources, level, timeframe, search) {
    const minOrd = level === 'All' ? 0 : (LEVEL_ORDER[level] ?? 1);
    const tf = TIMEFRAMES.find(t => t.key === timeframe);
    const cutoff = tf && tf.seconds > 0 ? (Date.now() / 1000) - tf.seconds : 0;
    const searchLower = search.toLowerCase();

    return entries.filter(e => {
      // Level filter
      if ((LEVEL_ORDER[e.level] ?? 0) < minOrd) return false;

      // Source filter — exact/prefix match on readable names
      if (!sources.has('all')) {
        let match = false;
        for (const s of sources) {
          if (matchSource(e.source, s)) { match = true; break; }
        }
        if (!match) return false;
      }

      // Time filter
      if (cutoff > 0 && e.ts < cutoff) return false;

      // Search filter
      if (searchLower && !(e.message ?? '').toLowerCase().includes(searchLower)) return false;

      return true;
    });
  }

  function toggleSource(key) {
    if (key === 'all') {
      activeSources = new Set(['all']);
      return;
    }
    const next = new Set(activeSources);
    next.delete('all');
    if (next.has(key)) {
      next.delete(key);
    } else {
      next.add(key);
    }
    if (next.size === 0) next.add('all');
    activeSources = next;
  }

  function formatTime(ts) {
    const d = new Date(ts * 1000);
    return d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  }

  function padRight(str, len) {
    return str.length >= len ? str.slice(0, len) : str + ' '.repeat(len - str.length);
  }

  function sourceColor(source) {
    const s = (source ?? '').toLowerCase();
    if (s === 'api') return 'var(--blue)';
    if (s === 'worker' || s.startsWith('worker-')) return 'var(--green)';
    if (s === 'delivery') return 'var(--gold)';
    if (s === 'scheduler') return 'var(--orange)';
    if (s === 'ct-collector' || s === 'ct') return 'var(--text-muted)';
    return 'var(--text-dim)';
  }

  function levelColor(level) {
    if (level === 'ERROR') return 'var(--red)';
    if (level === 'WARNING') return 'var(--orange)';
    if (level === 'INFO') return 'var(--text-dim)';
    return 'var(--text-muted)';
  }

  function formatCtx(ctx) {
    if (!ctx || typeof ctx !== 'object') return '';
    const parts = [];
    for (const [k, v] of Object.entries(ctx)) {
      parts.push(`${k}=${v}`);
    }
    return parts.length > 0 ? ' ' + parts.join(' ') : '';
  }

  function scrollToBottom() {
    if (logEl) {
      logEl.scrollTop = logEl.scrollHeight;
      userScrolledUp = false;
    }
  }

  function handleScroll() {
    if (!logEl) return;
    const threshold = 40;
    const atBottom = logEl.scrollHeight - logEl.scrollTop - logEl.clientHeight < threshold;
    userScrolledUp = !atBottom;
  }

  onMount(async () => {
    try {
      const data = await fetchLogs(200);
      allEntries = data.entries ?? [];
      totalCount = data.total ?? allEntries.length;
      prevAllEntriesLength = allEntries.length;
    } catch (err) {
      console.error('Logs fetch failed:', err);
    }
    loaded = true;

    // Auto-scroll on initial load
    requestAnimationFrame(() => scrollToBottom());
  });

  // Live updates from WebSocket
  $effect(() => {
    const msg = wsState.lastMessage;
    if (!msg) return;

    untrack(() => {
      if (msg.type === 'log_batch' && msg.payload?.entries) {
        const newEntries = [...allEntries, ...msg.payload.entries];
        allEntries = newEntries.length > MAX_ENTRIES
          ? newEntries.slice(newEntries.length - MAX_ENTRIES)
          : newEntries;
        totalCount = allEntries.length;
      }
    });
  });

  // Auto-scroll only when NEW entries are added to allEntries (not on filter changes)
  $effect(() => {
    const currentLen = allEntries.length;

    untrack(() => {
      if (currentLen > prevAllEntriesLength && !userScrolledUp && logEl) {
        requestAnimationFrame(() => {
          logEl.scrollTop = logEl.scrollHeight;
        });
      }
      prevAllEntriesLength = currentLen;
    });
  });
</script>

<div class="section-header">
  <div class="title-row">
    <span class="section-title">Logs</span>
    <span class="log-badge t-mono-label">{totalCount.toLocaleString()}</span>
  </div>
</div>

<div class="log-filter-rows">
  <div class="log-filter-bar">
    {#each SOURCES as src}
      <button
        class="filter-chip"
        class:active={activeSources.has(src.key)}
        onclick={() => toggleSource(src.key)}
      >
        {#if src.color}
          <span class="source-dot" style="background: {src.color}"></span>
        {/if}
        {src.label}
      </button>
    {/each}

    <input
      class="log-search t-label"
      type="text"
      placeholder="Search..."
      bind:value={searchText}
    />
  </div>

  <div class="log-filter-bar">
    {#each LEVELS as level}
      <button
        class="filter-chip"
        class:active={minLevel === level}
        onclick={() => minLevel = level}
      >
        {level}
      </button>
    {/each}
  </div>

  <div class="log-filter-bar">
    {#each TIMEFRAMES as tf}
      <button
        class="filter-chip time-chip"
        class:active={activeTimeframe === tf.key}
        onclick={() => activeTimeframe = tf.key}
      >
        {tf.label}
      </button>
    {/each}
  </div>
</div>

<div
  class="log-container"
  bind:this={logEl}
  onscroll={handleScroll}
>
  {#if filtered.length === 0 && loaded}
    <div class="empty-state">
      <span class="empty-state-text">No logs yet — waiting for container activity</span>
    </div>
  {/if}

  {#each filtered as entry}
    <div class="log-row t-mono-label">
      <span class="log-ts">{formatTime(entry.ts)}</span>
      <span class="log-source" style="color: {sourceColor(entry.source)}">{padRight(entry.source ?? '', 10)}</span>
      <span class="log-level" style="color: {levelColor(entry.level)}">{padRight(entry.level ?? '', 8)}</span>
      <span class="log-msg">{entry.message ?? ''}{formatCtx(entry.ctx)}</span>
    </div>
    {#if entry.exc}
      <div class="log-exc t-mono-label">{entry.exc}</div>
    {/if}
  {/each}

  {#if userScrolledUp}
    <button class="jump-btn t-label" onclick={scrollToBottom}>Jump to bottom</button>
  {/if}
</div>

<style>
  /* ── Title row ──────────────────────────────────────── */
  .title-row {
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .log-badge {
    color: var(--text-dim);
    background: var(--bg-surface);
    border: 1px solid var(--border-subtle);
    border-radius: 10px;
    padding: 2px 8px;
  }

  /* ── Single filter bar ──────────────────────────────── */
  .log-filter-rows {
    display: flex;
    flex-direction: column;
    gap: 8px;
    margin-bottom: 12px;
  }

  .log-filter-bar {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
  }


  .filter-sep {
    width: 1px;
    height: 20px;
    background: var(--border);
    flex-shrink: 0;
  }

  .source-dot {
    display: inline-block;
    width: 6px;
    height: 6px;
    border-radius: 50%;
    flex-shrink: 0;
  }

  .time-chip.active {
    background: var(--blue-dim);
    color: var(--blue);
    border-color: rgba(59, 130, 246, 0.3);
  }

  .log-search {
    margin-left: auto;
    background: var(--bg-surface);
    border: 1px solid var(--border);
    color: var(--text);
    padding: 6px 12px;
    border-radius: 20px;
    width: 180px;
    outline: none;
    transition: border-color var(--transition);
  }

  .log-search::placeholder {
    color: var(--text-muted);
  }

  .log-search:focus {
    border-color: var(--text-muted);
  }

  /* ── Log container ──────────────────────────────────── */
  .log-container {
    background: var(--bg-raised);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    flex: 1;
    overflow-y: auto;
    padding: 12px;
    position: relative;
    min-height: 0;
    max-height: calc(100vh - 260px);
  }

  .log-container::-webkit-scrollbar {
    width: 6px;
  }

  .log-container::-webkit-scrollbar-track {
    background: transparent;
  }

  .log-container::-webkit-scrollbar-thumb {
    background: var(--border);
    border-radius: 3px;
  }

  .log-container::-webkit-scrollbar-thumb:hover {
    background: var(--text-muted);
  }

  /* ── Log rows ───────────────────────────────────────── */
  .log-row {
    display: flex;
    align-items: baseline;
    gap: 0;
    line-height: 1.6;
    white-space: nowrap;
  }

  .log-row:hover {
    background: var(--bg-hover);
  }

  .log-ts {
    color: var(--text-dim);
    width: 7em;
    flex-shrink: 0;
  }

  .log-source {
    width: 10em;
    flex-shrink: 0;
    white-space: pre;
  }

  .log-level {
    width: 8em;
    flex-shrink: 0;
    font-weight: 600;
    white-space: pre;
  }

  .log-msg {
    color: var(--text-dim);
    overflow: hidden;
    text-overflow: ellipsis;
    min-width: 0;
  }

  .log-exc {
    color: var(--red);
    padding-left: 7em;
    white-space: pre-wrap;
    word-break: break-all;
    margin-bottom: 4px;
  }

  /* ── Jump button ────────────────────────────────────── */
  .jump-btn {
    position: sticky;
    bottom: 8px;
    left: 50%;
    transform: translateX(-50%);
    display: block;
    margin: 8px auto 0;
    padding: 6px 16px;
    background: var(--bg-surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    color: var(--text-dim);
    cursor: pointer;
    transition: all var(--transition);
    z-index: 10;
  }

  .jump-btn:hover {
    background: var(--bg-hover);
    border-color: var(--text-muted);
    color: var(--text);
  }
</style>
