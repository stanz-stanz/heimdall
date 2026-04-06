<script>
  import { wsState } from '../lib/ws.svelte.js';
  import { onMount, untrack } from 'svelte';

  const MAX_ENTRIES = 5000;

  const LEVEL_ORDER = { DEBUG: 0, INFO: 1, WARNING: 2, ERROR: 3 };

  const SOURCES = [
    { key: 'all', label: 'All' },
    { key: 'api', label: 'API' },
    { key: 'worker', label: 'Worker' },
    { key: 'delivery', label: 'Delivery' },
    { key: 'scheduler', label: 'Sched' },
    { key: 'ct', label: 'CT' },
  ];

  const LEVELS = ['ERROR', 'WARNING', 'INFO', 'DEBUG'];

  const TIMEFRAMES = [
    { key: 'all', label: 'All', seconds: 0 },
    { key: '1m', label: '1m', seconds: 60 },
    { key: '5m', label: '5m', seconds: 300 },
    { key: '10m', label: '10m', seconds: 600 },
    { key: '30m', label: '30m', seconds: 1800 },
  ];

  let allEntries = $state([]);
  let totalCount = $state(0);
  let loaded = $state(false);

  // Filters
  let activeSources = $state(new Set(['all']));
  let minLevel = $state('INFO');
  let activeTimeframe = $state('all');
  let searchText = $state('');

  // Auto-scroll
  let logEl = $state(null);
  let userScrolledUp = $state(false);

  let filtered = $derived(filterEntries(allEntries, activeSources, minLevel, activeTimeframe, searchText));

  function filterEntries(entries, sources, level, timeframe, search) {
    const minOrd = LEVEL_ORDER[level] ?? 1;
    const tf = TIMEFRAMES.find(t => t.key === timeframe);
    const cutoff = tf && tf.seconds > 0 ? (Date.now() / 1000) - tf.seconds : 0;
    const searchLower = search.toLowerCase();

    return entries.filter(e => {
      // Level filter
      if ((LEVEL_ORDER[e.level] ?? 0) < minOrd) return false;

      // Source filter
      if (!sources.has('all')) {
        const src = (e.source ?? '').toLowerCase();
        let match = false;
        for (const s of sources) {
          if (src.includes(s)) { match = true; break; }
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
    if (s.includes('api')) return 'var(--blue)';
    if (s.includes('worker')) return 'var(--green)';
    if (s.includes('delivery')) return 'var(--gold)';
    if (s.includes('scheduler')) return 'var(--orange)';
    if (s.includes('ct')) return 'var(--text-muted)';
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
      const res = await fetch('/console/logs?limit=200');
      if (res.ok) {
        const data = await res.json();
        allEntries = data.entries ?? [];
        totalCount = data.total ?? allEntries.length;
      }
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

  // Auto-scroll when new filtered entries arrive (if user hasn't scrolled up)
  $effect(() => {
    // Track filtered length to trigger on new entries
    filtered.length;

    untrack(() => {
      if (!userScrolledUp && logEl) {
        requestAnimationFrame(() => {
          logEl.scrollTop = logEl.scrollHeight;
        });
      }
    });
  });
</script>

<div class="section-header">
  <span class="section-title">Logs</span>
  <span class="log-total">total: {totalCount.toLocaleString()}</span>
</div>

<div class="log-filters">
  <div class="filter-row">
    <span class="filter-label">Source</span>
    <div class="filters">
      {#each SOURCES as src}
        <button
          class="filter-chip"
          class:active={activeSources.has(src.key)}
          onclick={() => toggleSource(src.key)}
        >
          {src.label}
        </button>
      {/each}
    </div>
  </div>

  <div class="filter-row">
    <span class="filter-label">Level</span>
    <div class="filters">
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
  </div>

  <div class="filter-row">
    <span class="filter-label">Time</span>
    <div class="filters">
      {#each TIMEFRAMES as tf}
        <button
          class="filter-chip"
          class:active={activeTimeframe === tf.key}
          onclick={() => activeTimeframe = tf.key}
        >
          {tf.label}
        </button>
      {/each}
    </div>
    <input
      class="log-search"
      type="text"
      placeholder="Search messages..."
      bind:value={searchText}
    />
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
    <div class="log-row">
      <span class="log-ts">{formatTime(entry.ts)}</span>
      <span class="log-source" style="color: {sourceColor(entry.source)}">{padRight(entry.source ?? '', 10)}</span>
      <span class="log-level" style="color: {levelColor(entry.level)}">{padRight(entry.level ?? '', 8)}</span>
      <span class="log-msg">{entry.message ?? ''}{formatCtx(entry.ctx)}</span>
    </div>
    {#if entry.exc}
      <div class="log-exc">{entry.exc}</div>
    {/if}
  {/each}

  {#if userScrolledUp}
    <button class="jump-btn" onclick={scrollToBottom}>Jump to bottom</button>
  {/if}
</div>

<style>
  .log-total {
    font-family: var(--mono);
    font-size: 12px;
    color: var(--text-muted);
  }

  .log-filters {
    display: flex;
    flex-direction: column;
    gap: 10px;
    margin-bottom: 16px;
  }

  .filter-row {
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .filter-label {
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--text-muted);
    width: 52px;
    flex-shrink: 0;
  }

  .log-search {
    margin-left: auto;
    background: var(--bg-surface);
    border: 1px solid var(--border);
    color: var(--text);
    padding: 6px 12px;
    border-radius: var(--radius-sm);
    font-size: 12px;
    font-family: var(--sans);
    width: 200px;
    outline: none;
    transition: border-color var(--transition);
  }

  .log-search::placeholder {
    color: var(--text-muted);
  }

  .log-search:focus {
    border-color: var(--text-muted);
  }

  .log-container {
    background: var(--bg-raised);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    flex: 1;
    overflow-y: auto;
    padding: 12px;
    position: relative;
    min-height: 0;
    max-height: calc(100vh - 300px);
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

  .log-row {
    display: flex;
    align-items: baseline;
    gap: 0;
    font-family: var(--mono);
    font-size: 12px;
    line-height: 1.6;
    white-space: nowrap;
  }

  .log-row:hover {
    background: var(--bg-hover);
  }

  .log-ts {
    color: var(--text-muted);
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
    font-family: var(--mono);
    font-size: 11px;
    color: var(--red);
    padding-left: 7em;
    line-height: 1.4;
    white-space: pre-wrap;
    word-break: break-all;
    margin-bottom: 4px;
  }

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
    font-family: var(--sans);
    font-size: 12px;
    font-weight: 500;
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
