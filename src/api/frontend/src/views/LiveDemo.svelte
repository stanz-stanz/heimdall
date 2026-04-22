<script>
  import { onDestroy } from 'svelte';
  import { fade, fly, slide } from 'svelte/transition';
  import { cubicOut, cubicInOut } from 'svelte/easing';

  /** @typedef {'select' | 'scanning' | 'complete'} Phase */

  let phase = $state(/** @type {Phase} */ ('select'));
  let briefs = $state([]);
  let briefsError = $state('');

  let domain = $state('');
  let status = $state('Initializing scan…');
  let elapsedSec = $state(0);
  let timerHandle = null;
  let startedAt = 0;

  let total = $state(0);
  let completed = $state(0);
  let percent = $derived(total > 0 ? Math.round((completed / total) * 100) : 0);
  let scansDone = $derived(total > 0 && completed >= total);

  const CIRC = 2 * Math.PI * 52;
  let radialOffset = $derived(CIRC - (percent / 100) * CIRC);

  let timeline = $state([]); // { id, label, state: 'running' | 'done', duration_ms? }
  let findings = $state([]); // { index, severity, description, risk, typed }
  let findingsTotal = $state(0);

  // True when every finding's typewriter has finished (or there are no
  // findings to type). Gates the swap from scan-hero to the spotlight
  // summary — we don't want "Assessment Complete" landing while risk
  // text is still being typed below.
  let allTyped = $derived(
    findings.length === 0 ||
      findings.every((f) => f.typed.length >= (f.risk?.length ?? 0)),
  );
  let showSummary = $derived(phase === 'complete' && allTyped);

  let summaryText = $state('');

  // --- Brief selector: prefix search + pagination -----------------------

  const PAGE_SIZE = 24;
  let searchQuery = $state('');
  let currentPage = $state(1);

  // Prefix match against company_name, case-insensitive, from char 1.
  // Substring matches are intentionally excluded per product requirement.
  let filteredBriefs = $derived.by(() => {
    const q = searchQuery.trim().toLowerCase();
    if (!q) return briefs;
    return briefs.filter((b) =>
      (b.company_name || '').toLowerCase().startsWith(q),
    );
  });

  let totalPages = $derived(
    Math.max(1, Math.ceil(filteredBriefs.length / PAGE_SIZE)),
  );

  let visibleBriefs = $derived(
    filteredBriefs.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE),
  );

  // Clamp page when the filter shrinks the result set below the current page.
  $effect(() => {
    if (currentPage > totalPages) currentPage = totalPages;
  });

  function clearSearch() {
    searchQuery = '';
    currentPage = 1;
  }

  function prevPage() {
    if (currentPage > 1) currentPage -= 1;
  }

  function nextPage() {
    if (currentPage < totalPages) currentPage += 1;
  }

  let ws = null;
  const typewriters = new Map();

  async function loadBriefs() {
    briefsError = '';
    briefs = [];
    try {
      const res = await fetch('/console/briefs', { credentials: 'same-origin' });
      if (!res.ok) throw new Error(`${res.status}`);
      briefs = await res.json();
    } catch {
      briefsError = 'Could not load targets';
    }
  }

  loadBriefs();

  function resetState() {
    if (ws) {
      try { ws.close(); } catch {}
      ws = null;
    }
    stopTimer();
    for (const h of typewriters.values()) clearTimeout(h);
    typewriters.clear();
    domain = '';
    status = 'Initializing scan…';
    elapsedSec = 0;
    total = 0;
    completed = 0;
    timeline = [];
    findings = [];
    findingsTotal = 0;
    summaryText = '';
  }

  function stopTimer() {
    if (timerHandle) {
      clearInterval(timerHandle);
      timerHandle = null;
    }
  }

  function startTimer() {
    startedAt = performance.now();
    elapsedSec = 0;
    timerHandle = setInterval(() => {
      elapsedSec = (performance.now() - startedAt) / 1000;
    }, 100);
  }

  async function startDemo(targetDomain) {
    resetState();
    phase = 'scanning';
    domain = targetDomain;

    try {
      const res = await fetch('/console/demo/start', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ domain: targetDomain, mode: 'replay' }),
      });
      if (!res.ok) {
        status = 'Failed to start demo';
        return;
      }
      const { scan_id } = await res.json();
      startTimer();
      const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
      ws = new WebSocket(`${proto}//${location.host}/console/demo/ws/${scan_id}`);
      ws.onmessage = (e) => handleEvent(JSON.parse(e.data));
      ws.onclose = stopTimer;
      ws.onerror = stopTimer;
    } catch {
      status = 'Connection error';
    }
  }

  function handleEvent(evt) {
    switch (evt.type) {
      case 'phase':
        status = evt.message ?? status;
        break;
      case 'scan_start':
        if (evt.total && evt.total > total) total = evt.total;
        timeline = [...timeline, { id: evt.scan_type, label: evt.label, state: 'running' }];
        break;
      case 'scan_complete':
        completed += 1;
        timeline = timeline.map((row) =>
          row.id === evt.scan_type
            ? { ...row, state: 'done', duration_ms: evt.duration_ms }
            : row,
        );
        break;
      case 'tech_reveal':
        // Tech stack intentionally not rendered — findings take the stage.
        break;
      case 'finding':
        findingsTotal = evt.total ?? findingsTotal;
        addFinding(evt);
        break;
      case 'complete':
        stopTimer();
        completed = total; // snap radial to 100%
        showComplete(evt);
        break;
    }
  }

  function addFinding(evt) {
    const record = {
      index: evt.index,
      severity: (evt.severity || 'info').toLowerCase(),
      description: evt.description || '',
      risk: evt.risk || '',
      typed: '',
    };
    findings = sortBySeverity([...findings, record]);
    typewrite(evt.index, evt.risk || '');
  }

  function typewrite(index, text) {
    let i = 0;
    const speed = 15;
    const tick = () => {
      if (i >= text.length) {
        typewriters.delete(index);
        return;
      }
      i += 1;
      findings = findings.map((f) =>
        f.index === index ? { ...f, typed: text.slice(0, i) } : f,
      );
      typewriters.set(index, setTimeout(tick, speed));
    };
    typewriters.set(index, setTimeout(tick, speed));
  }

  function showComplete(evt) {
    phase = 'complete';
    const count = evt.findings_count ?? findings.length;
    const seconds = elapsedSec.toFixed(1);
    summaryText = `Assessment complete. ${count} security finding${count !== 1 ? 's' : ''} identified in ${seconds} seconds.`;
    domain = evt.domain || domain;
  }

  function newAssessment() {
    resetState();
    phase = 'select';
    loadBriefs();
  }

  onDestroy(() => {
    resetState();
  });

  const SEVERITY_CLASS = {
    critical: 'sev-critical',
    high: 'sev-high',
    medium: 'sev-medium',
    low: 'sev-low',
    info: 'sev-info',
  };

  const SEVERITY_RANK = {
    critical: 0,
    high: 1,
    medium: 2,
    low: 3,
    info: 4,
  };

  function severityClass(s) {
    return SEVERITY_CLASS[s] ?? 'sev-info';
  }

  function sortBySeverity(list) {
    // Stable sort: Array.prototype.sort is stable in modern engines.
    return [...list].sort(
      (a, b) => (SEVERITY_RANK[a.severity] ?? 99) - (SEVERITY_RANK[b.severity] ?? 99),
    );
  }
</script>

{#if phase === 'select'}
  <section class="demo-select">
    <header class="demo-select-header">
      <h2 class="t-title">Security Assessment</h2>
      <p class="t-help">Select a target to begin the live demonstration.</p>
    </header>

    {#if briefsError}
      <div class="empty-state">
        <p class="t-body">{briefsError}</p>
        <button class="btn btn-sm" onclick={loadBriefs}>Retry</button>
      </div>
    {:else if briefs.length === 0}
      <div class="empty-state">
        <p class="t-body">Loading available targets…</p>
      </div>
    {:else}
      <div class="search-row">
        <input
          type="text"
          class="search-input t-body"
          placeholder="Filter by company name…"
          aria-label="Filter targets by company name"
          bind:value={searchQuery}
        />
        {#if searchQuery}
          <button
            type="button"
            class="search-clear"
            aria-label="Clear search"
            onclick={clearSearch}
          >×</button>
        {/if}
      </div>

      {#if visibleBriefs.length === 0}
        <div class="empty-state">
          <p class="t-body">No targets start with "{searchQuery}".</p>
        </div>
      {:else}
        <div class="briefs-grid">
          {#each visibleBriefs as brief (brief.domain)}
            <button
              type="button"
              class="brief-card"
              onclick={() => startDemo(brief.domain)}
            >
              <div class="brief-domain t-subheading">{brief.domain}</div>
              <div class="brief-company t-body">{brief.company_name}</div>
              <div class="brief-meta t-mono-label">
                <span>Bucket {brief.bucket}</span>
                <span class="meta-dot"></span>
                <span>{brief.findings_count} findings</span>
              </div>
            </button>
          {/each}
        </div>

        {#if totalPages > 1}
          <nav class="pagination" aria-label="Pagination">
            <button
              type="button"
              class="btn btn-sm page-btn"
              disabled={currentPage === 1}
              onclick={prevPage}
            >
              ← Previous
            </button>
            <span class="page-indicator t-mono-label">
              Page {currentPage} of {totalPages}
              <span class="page-count">· {filteredBriefs.length} targets</span>
            </span>
            <button
              type="button"
              class="btn btn-sm page-btn"
              disabled={currentPage === totalPages}
              onclick={nextPage}
            >
              Next →
            </button>
          </nav>
        {/if}
      {/if}
    {/if}
  </section>
{:else}
  <section class="demo-run">
    <div class="stage">
      {#if !showSummary}
        <div
          class="scan-hero"
          out:fly={{ duration: 520, y: -6, easing: cubicInOut }}
        >
          <div class="radial" aria-label="Scan progress {percent}%">
            <svg viewBox="0 0 120 120" aria-hidden="true">
              <circle class="radial-track" cx="60" cy="60" r="52" />
              <circle
                class="radial-fill"
                cx="60"
                cy="60"
                r="52"
                style:stroke-dashoffset={radialOffset}
              />
            </svg>
            <div class="radial-inner">
              <div class="radial-percent t-display">{percent}%</div>
              <div class="radial-label t-caption">Complete</div>
            </div>
          </div>
          <div class="hero-info">
            <div class="hero-domain t-title">{domain}</div>
            <div class="hero-timer t-mono-stat">{elapsedSec.toFixed(1)}s</div>
            <div class="hero-status t-help">{status}</div>
          </div>
        </div>
      {:else}
        <div
          class="summary spotlight"
          in:fly={{ duration: 720, y: 8, delay: 160, easing: cubicInOut }}
        >
          <div class="summary-shield" aria-hidden="true">
            <svg viewBox="0 0 64 64" fill="none">
              <path d="M32 4L8 16v16c0 14.4 10.24 27.84 24 32 13.76-4.16 24-17.6 24-32V16L32 4z" stroke="currentColor" stroke-width="2" fill="currentColor" fill-opacity="0.1"/>
              <path d="M24 32l6 6 12-12" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
          </div>
          <div class="summary-label t-caption">Assessment Complete</div>
          <h2 class="summary-domain t-display">{domain}</h2>
          <p class="summary-text t-body">{summaryText}</p>
          <button type="button" class="btn btn-primary" onclick={newAssessment}>
            New Assessment
          </button>
        </div>
      {/if}
    </div>

    {#if timeline.length > 0 && !scansDone}
      <div
        class="timeline"
        out:slide={{ duration: 450, easing: cubicOut }}
      >
        {#each timeline as row, i (row.id)}
          <div
            class="timeline-row"
            out:fade={{ duration: 220, delay: i * 35, easing: cubicOut }}
          >
            <span class="timeline-dot" class:done={row.state === 'done'} class:running={row.state === 'running'}></span>
            <span class="timeline-label t-body-strong">{row.label}</span>
            {#if row.duration_ms != null}
              <span class="timeline-duration t-mono-label">{row.duration_ms}ms</span>
            {/if}
          </div>
        {/each}
      </div>
    {/if}

    {#if findings.length > 0}
      <div class="section">
        <div class="section-header">
          <h3 class="t-section">Security Findings</h3>
          <span class="section-tag t-caption">{findings.length}{findingsTotal ? ` of ${findingsTotal}` : ''}</span>
        </div>
        <div class="findings">
          {#each findings as f (f.index)}
            <article class="finding {severityClass(f.severity)}">
              <header class="finding-head">
                <span class="finding-sev t-caption {severityClass(f.severity)}">{f.severity}</span>
                <span class="finding-desc t-body-strong">{f.description}</span>
              </header>
              <p class="finding-risk t-body">{f.typed}</p>
            </article>
          {/each}
        </div>
      </div>
    {/if}
  </section>
{/if}

<style>
  .demo-select {
    max-width: 960px;
    margin: 0 auto;
  }

  .demo-select-header {
    text-align: center;
    margin-bottom: 20px;
  }

  .demo-select-header .t-help {
    margin: 6px auto 0;
  }

  /* ---- Search bar ---- */

  .search-row {
    position: relative;
    margin: 0 auto 20px;
    max-width: 420px;
  }

  .search-input {
    width: 100%;
    padding: 10px 36px 10px 14px;
    background: var(--bg-raised);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-sm);
    color: var(--text);
    transition:
      border-color var(--transition),
      box-shadow var(--transition);
  }

  .search-input::placeholder {
    color: var(--text-muted);
  }

  .search-input:focus {
    outline: none;
    border-color: var(--gold);
    box-shadow: 0 0 0 3px var(--gold-glow);
  }

  .search-clear {
    position: absolute;
    right: 6px;
    top: 50%;
    transform: translateY(-50%);
    width: 24px;
    height: 24px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border: none;
    border-radius: 999px;
    background: transparent;
    color: var(--text-dim);
    font-size: 18px;
    line-height: 1;
    cursor: pointer;
    transition: color var(--transition), background-color var(--transition);
  }

  .search-clear:hover {
    color: var(--text);
    background: var(--bg-hover);
  }

  /* ---- Pagination ---- */

  .pagination {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 16px;
    margin-top: 20px;
  }

  .page-btn {
    min-width: 96px;
  }

  .page-btn:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }

  .page-indicator {
    color: var(--text-dim);
    white-space: nowrap;
  }

  .page-count {
    color: var(--text-muted);
  }

  .briefs-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 12px;
  }

  .brief-card {
    background: var(--bg-raised);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius);
    padding: 20px;
    cursor: pointer;
    text-align: left;
    color: inherit;
    font: inherit;
    transition:
      border-color var(--transition),
      transform var(--transition),
      box-shadow var(--transition);
  }

  .brief-card:hover {
    border-color: var(--gold-dim);
    box-shadow: var(--shadow);
  }

  .brief-card:active {
    transform: scale(0.99);
  }

  .brief-domain {
    color: var(--text);
    margin-bottom: 4px;
  }

  .brief-company {
    color: var(--text-dim);
  }

  .brief-meta {
    display: flex;
    align-items: center;
    gap: 8px;
    color: var(--text-dim);
    margin-top: 10px;
  }

  .meta-dot {
    width: 3px;
    height: 3px;
    border-radius: 50%;
    background: var(--text-muted);
  }

  .empty-state {
    text-align: center;
    padding: 40px 24px;
    color: var(--text-dim);
  }

  .empty-state .btn {
    margin-top: 14px;
  }

  /* ---- Scan view ---- */

  .demo-run {
    max-width: 960px;
    margin: 0 auto;
    display: flex;
    flex-direction: column;
    gap: 28px;
  }

  /* Stage: a single slot that both scan-hero and spotlight summary
     share via CSS grid. Guarantees they overlap during the crossfade
     (no layout jump) and caps the slot height so content below does
     not shift when the swap happens. */
  .stage {
    display: grid;
    min-height: 260px;
    place-items: center;
  }

  .stage > * {
    grid-column: 1;
    grid-row: 1;
    width: 100%;
    align-self: center;
  }

  .scan-hero {
    display: flex;
    flex-direction: column;
    align-items: center;
    text-align: center;
    gap: 20px;
    padding: 8px 0 4px;
  }

  @media (min-width: 640px) {
    .scan-hero {
      flex-direction: row;
      text-align: left;
      gap: 36px;
    }
  }

  .radial {
    position: relative;
    width: 140px;
    height: 140px;
    flex-shrink: 0;
  }

  .radial svg {
    width: 100%;
    height: 100%;
    transform: rotate(-90deg);
  }

  .radial-track {
    fill: none;
    stroke: var(--border);
    stroke-width: 4;
  }

  .radial-fill {
    fill: none;
    stroke: var(--gold);
    stroke-width: 4;
    stroke-linecap: round;
    stroke-dasharray: 326.73;
    transition: stroke-dashoffset 0.6s ease;
    filter: drop-shadow(0 0 8px var(--gold-glow));
  }

  .radial-inner {
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    text-align: center;
  }

  .radial-percent {
    color: var(--text);
    line-height: 1.1;
  }

  .radial-label {
    color: var(--text-dim);
  }

  .hero-info {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .hero-domain {
    color: var(--text);
  }

  .hero-timer {
    color: var(--gold);
  }

  .hero-status {
    min-height: 20px;
    margin: 0;
  }

  /* ---- Timeline ---- */

  .timeline {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .timeline-row {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 12px 14px;
    background: var(--bg-raised);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-sm);
    animation: slide-in 0.35s ease-out;
  }

  .timeline-dot {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    background: var(--text-muted);
    flex-shrink: 0;
    transition: background var(--transition), box-shadow var(--transition);
  }

  .timeline-dot.running {
    background: var(--gold);
    box-shadow: 0 0 10px var(--gold-glow);
    animation: scan-pulse 1.2s ease-in-out infinite;
  }

  .timeline-dot.done {
    background: var(--green);
  }

  .timeline-label {
    flex: 1;
    color: var(--text-dim);
  }

  .timeline-duration {
    color: var(--text-dim);
  }

  /* ---- Sections ---- */

  .section {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .section-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .section-header .t-section {
    color: var(--text-dim);
  }

  .section-tag {
    background: var(--gold-glow);
    color: var(--gold);
    padding: 4px 10px;
    border-radius: 999px;
  }

  /* ---- Findings (warm-only severity per design system) ---- */

  .findings {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .finding {
    background: var(--bg-raised);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius);
    padding: 18px;
    border-left: 3px solid var(--text-muted);
    animation: slide-up 0.4s ease-out both;
  }

  .finding.sev-critical { border-left-color: var(--red); }
  .finding.sev-high     { border-left-color: var(--orange); }
  .finding.sev-medium   { border-left-color: var(--red-soft); }
  .finding.sev-low      { border-left-color: var(--red-outline); }
  .finding.sev-info     { border-left-color: var(--text-dim); }

  .finding-head {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 8px;
  }

  .finding-sev {
    padding: 3px 8px;
    border-radius: var(--radius-xs);
  }

  .finding-sev.sev-critical { background: var(--red-dim);    color: var(--red); }
  .finding-sev.sev-high     { background: var(--orange-dim); color: var(--orange); }
  .finding-sev.sev-medium   {
    background: var(--red-muted);
    color: var(--red-soft);
    border: 1px solid var(--red-outline);
  }
  .finding-sev.sev-low      {
    background: var(--red-muted);
    color: var(--text-dim);
    border: 1px solid var(--red-outline);
  }
  .finding-sev.sev-info     {
    background: transparent;
    color: var(--text-dim);
    border: 1px solid var(--border);
  }

  .finding-desc {
    color: var(--text);
  }

  .finding-risk {
    color: var(--text-dim);
    line-height: 1.6;
    margin: 0;
    min-height: 1.6em;
    white-space: pre-wrap;
  }

  /* ---- Summary ---- */

  .summary {
    text-align: center;
    padding: 32px 24px;
    max-width: 520px;
    margin: 0 auto;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 12px;
  }

  /* Spotlight: takes the scan-hero's slot after completion. Bigger
     footprint, centered, dominates the top of the stage. */
  .summary.spotlight {
    padding: 40px 24px 32px;
    max-width: 640px;
    gap: 16px;
  }

  .summary-shield {
    width: 80px;
    height: 80px;
    color: var(--green);
    animation: shield-soft 680ms cubic-bezier(0.22, 0.61, 0.36, 1) 260ms both;
  }

  .summary.spotlight .summary-shield {
    width: 108px;
    height: 108px;
  }

  .summary-shield svg {
    width: 100%;
    height: 100%;
  }

  .summary-domain {
    color: var(--text);
    margin: 0;
  }

  .summary.spotlight .summary-domain {
    letter-spacing: -0.02em;
  }

  .summary.spotlight .summary-text {
    max-width: 52ch;
    color: var(--text-dim);
    margin: 0;
  }

  .summary-label {
    color: var(--green);
  }

  .summary-text {
    margin: 0;
  }

  /* ---- Animations ---- */

  @keyframes scan-pulse {
    0%, 100% { opacity: 0.55; transform: scale(0.85); }
    50%      { opacity: 1;    transform: scale(1.15); }
  }

  @keyframes slide-in {
    from { opacity: 0; transform: translateX(-16px); }
    to   { opacity: 1; transform: translateX(0); }
  }

  @keyframes slide-up {
    from { opacity: 0; transform: translateY(20px); }
    to   { opacity: 1; transform: translateY(0); }
  }



  @keyframes shield-soft {
    0%   { opacity: 0; transform: scale(0.92); }
    100% { opacity: 1; transform: scale(1); }
  }
</style>
