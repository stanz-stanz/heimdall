/* ============================================================
   Heimdall Console — Client Logic
   Monitor polling + Demo WebSocket + Animations
   ============================================================ */

(function () {
  'use strict';

  // ---- Tab switching ----

  const tabs = document.querySelectorAll('.tab');
  const views = document.querySelectorAll('.view');

  tabs.forEach((tab) => {
    tab.addEventListener('click', () => {
      const target = tab.dataset.tab;
      tabs.forEach((t) => t.classList.remove('active'));
      views.forEach((v) => v.classList.remove('active'));
      tab.classList.add('active');
      document.getElementById(target).classList.add('active');

      if (target === 'monitor') startMonitor();
      if (target === 'demo') loadBriefs();
    });
  });

  // ================================================================
  // MONITOR MODE
  // ================================================================

  let monitorInterval = null;

  function startMonitor() {
    fetchStatus();
    if (monitorInterval) clearInterval(monitorInterval);
    monitorInterval = setInterval(fetchStatus, 5000);
  }

  async function fetchStatus() {
    try {
      const resp = await fetch('/console/status');
      if (!resp.ok) return;
      const data = await resp.json();
      renderStatus(data);
    } catch (e) {
      // Network error — leave previous state
    }
  }

  function renderStatus(data) {
    // Timestamp
    const ts = data.timestamp ? new Date(data.timestamp) : new Date();
    document.getElementById('monitor-time').textContent =
      ts.toLocaleTimeString('da-DK', { hour: '2-digit', minute: '2-digit', second: '2-digit' });

    // Queue cards
    setQueueValue('q-scan-val', data.queues.scan);
    setQueueValue('q-enrich-val', data.queues.enrichment);
    setQueueValue('q-wpscan-val', data.queues.wpscan);

    // Enrichment: show progress if active
    const enrich = data.enrichment;
    const enrichEl = document.getElementById('q-enrich-val');
    if (enrich.total > 0 && enrich.completed < enrich.total) {
      enrichEl.textContent = `${enrich.completed}/${enrich.total}`;
    }

    // Cache
    document.getElementById('cache-val').textContent = data.cache_keys.toLocaleString();

    // Recent scans
    const list = document.getElementById('scans-list');
    const countEl = document.getElementById('scans-count');
    if (!data.recent_scans || data.recent_scans.length === 0) {
      list.innerHTML = '<div class="empty-state"><svg class="empty-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg><p>No scans yet</p></div>';
      if (countEl) countEl.textContent = '';
      return;
    }
    if (countEl) countEl.textContent = `${data.recent_scans.length} total`;
    list.innerHTML = data.recent_scans.map(renderScanRow).join('');
  }

  function setQueueValue(id, value) {
    const el = document.getElementById(id);
    el.textContent = value;
    el.className = 'card-value';
    if (value > 100) el.classList.add('high');
    else if (value > 0) el.classList.add('active');
  }

  function renderScanRow(scan) {
    const count = scan.findings_count || 0;
    const badgeClass = count === 0 ? 'badge-ok' : count <= 3 ? 'badge-low' : count <= 6 ? 'badge-medium' : 'badge-high';
    const badgeText = count === 0 ? 'Clean' : `${count} findings`;
    return `
      <div class="scan-row">
        <span class="scan-domain">${esc(scan.domain)}</span>
        <span class="scan-badge ${badgeClass}">${badgeText}</span>
        <span class="scan-date">${esc(scan.scan_date || '')}</span>
      </div>`;
  }

  // ================================================================
  // DEMO MODE
  // ================================================================

  let ws = null;
  let demoTimer = null;
  let demoStartTime = 0;
  let totalScans = 0;
  let completedScans = 0;
  let demoMode = 'replay'; // 'replay' or 'live'

  async function loadBriefs() {
    try {
      const resp = await fetch('/console/briefs');
      if (!resp.ok) return;
      const briefs = await resp.json();
      renderBriefs(briefs);
    } catch (e) {
      document.getElementById('briefs-grid').innerHTML =
        '<div class="empty-state"><svg class="empty-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg><p>Could not load targets</p></div>';
    }
  }

  function renderBriefs(briefs) {
    const grid = document.getElementById('briefs-grid');
    if (briefs.length === 0) {
      grid.innerHTML = '<div class="empty-state"><svg class="empty-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg><p>No targets available</p></div>';
      return;
    }
    // Mode toggle
    const toggleHtml = `
      <div class="demo-mode-toggle">
        <button class="mode-btn active" data-mode="replay">Replay</button>
        <button class="mode-btn" data-mode="live">Live Twin</button>
      </div>`;
    grid.innerHTML = toggleHtml + briefs.map((b) => `
      <div class="brief-card" data-domain="${esc(b.domain)}">
        <div class="brief-domain">${esc(b.domain)}</div>
        <div class="brief-company">${esc(b.company_name)}</div>
        <div class="brief-meta">
          <span>Bucket ${esc(b.bucket)}</span>
          <span class="brief-meta-dot"></span>
          <span>${b.findings_count} findings</span>
        </div>
      </div>`).join('');

    grid.querySelectorAll('.mode-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        grid.querySelectorAll('.mode-btn').forEach((b) => b.classList.remove('active'));
        btn.classList.add('active');
        demoMode = btn.dataset.mode;
      });
    });

    grid.querySelectorAll('.brief-card').forEach((card) => {
      card.addEventListener('click', () => startDemo(card.dataset.domain));
    });
  }

  async function startDemo(domain) {
    // Reset UI
    resetDemo();

    try {
      const resp = await fetch('/console/demo/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ domain, mode: demoMode }),
      });
      if (!resp.ok) {
        alert('Failed to start demo');
        return;
      }
      const { scan_id } = await resp.json();

      // Show scanning phase
      showPhase('demo-scanning');
      document.getElementById('demo-domain').textContent = domain;

      // Reset progress
      totalScans = 0;
      completedScans = 0;
      updateRadialProgress(0);

      // Start timer
      demoStartTime = performance.now();
      demoTimer = setInterval(updateTimer, 100);

      // Connect WebSocket
      const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
      ws = new WebSocket(`${proto}//${location.host}/console/demo/ws/${scan_id}`);
      ws.onmessage = (e) => handleDemoEvent(JSON.parse(e.data));
      ws.onclose = () => { if (demoTimer) clearInterval(demoTimer); };
      ws.onerror = () => { if (demoTimer) clearInterval(demoTimer); };
    } catch (e) {
      alert('Connection error');
    }
  }

  function resetDemo() {
    if (ws) { ws.close(); ws = null; }
    if (demoTimer) { clearInterval(demoTimer); demoTimer = null; }

    document.getElementById('scan-timeline').innerHTML = '';
    document.getElementById('tech-badges').innerHTML = '';
    document.getElementById('findings-list').innerHTML = '';
    document.getElementById('demo-status').textContent = 'Initializing scan...';
    document.getElementById('demo-timer').textContent = '0.0s';

    totalScans = 0;
    completedScans = 0;
    updateRadialProgress(0);

    const counter = document.getElementById('findings-counter');
    if (counter) counter.textContent = '';

    // Hide all phases, show selector
    document.querySelectorAll('.demo-phase').forEach((p) => p.classList.add('hidden'));
    document.getElementById('demo-selector').classList.remove('hidden');
  }

  function showPhase(id) {
    document.querySelectorAll('.demo-phase').forEach((p) => p.classList.add('hidden'));
    document.getElementById(id).classList.remove('hidden');
  }

  function updateTimer() {
    const elapsed = ((performance.now() - demoStartTime) / 1000).toFixed(1);
    document.getElementById('demo-timer').textContent = `${elapsed}s`;
  }

  function updateRadialProgress(percent) {
    const circumference = 2 * Math.PI * 52; // r=52
    const offset = circumference - (percent / 100) * circumference;
    const fill = document.getElementById('radial-fill');
    if (fill) fill.style.strokeDashoffset = offset;
    const label = document.getElementById('radial-percent');
    if (label) label.textContent = `${Math.round(percent)}%`;
  }

  // ---- Event handlers ----

  let findingsCount = 0;

  function handleDemoEvent(event) {
    switch (event.type) {
      case 'phase':
        document.getElementById('demo-status').textContent = event.message;
        break;

      case 'scan_start':
        if (event.total && event.total > totalScans) totalScans = event.total;
        addTimelineRow(event.scan_type, event.label, 'running');
        break;

      case 'scan_complete':
        completedScans++;
        if (totalScans > 0) {
          updateRadialProgress((completedScans / totalScans) * 100);
        }
        completeTimelineRow(event.scan_type, event.duration_ms);
        break;

      case 'tech_reveal':
        showPhase('demo-scanning');
        document.getElementById('demo-tech').classList.remove('hidden');
        renderTechBadges(event.tech_stack);
        break;

      case 'finding':
        document.getElementById('demo-findings').classList.remove('hidden');
        findingsCount = event.index || (findingsCount + 1);
        const counter = document.getElementById('findings-counter');
        if (counter) counter.textContent = `${findingsCount} of ${event.total || '?'}`;
        addFinding(event);
        break;

      case 'complete':
        if (demoTimer) { clearInterval(demoTimer); demoTimer = null; }
        updateRadialProgress(100);
        showComplete(event);
        findingsCount = 0;
        break;
    }
  }

  function addTimelineRow(scanType, label, state) {
    const timeline = document.getElementById('scan-timeline');
    const row = document.createElement('div');
    row.className = 'timeline-row';
    row.id = `tl-${scanType}`;
    row.innerHTML = `
      <div class="timeline-indicator ${state}"></div>
      <span class="timeline-label">${esc(label)}</span>
      <span class="timeline-duration" id="tl-dur-${scanType}"></span>`;
    timeline.appendChild(row);

    // Auto-scroll to latest
    row.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  function completeTimelineRow(scanType, durationMs) {
    const indicator = document.querySelector(`#tl-${scanType} .timeline-indicator`);
    if (indicator) {
      indicator.classList.remove('running');
      indicator.classList.add('done');
    }
    const dur = document.getElementById(`tl-dur-${scanType}`);
    if (dur) dur.textContent = `${durationMs}ms`;
  }

  function renderTechBadges(techStack) {
    const container = document.getElementById('tech-badges');
    techStack.forEach((tech, i) => {
      const badge = document.createElement('span');
      badge.className = 'tech-badge';
      badge.innerHTML = `<span class="tech-dot"></span>${esc(tech)}`;
      badge.style.animationDelay = `${i * 0.08}s`;
      container.appendChild(badge);
    });
  }

  function addFinding(event) {
    const list = document.getElementById('findings-list');
    const card = document.createElement('div');
    card.className = `finding-card severity-${event.severity}`;
    card.innerHTML = `
      <div class="finding-header">
        <span class="finding-severity ${event.severity}">${esc(event.severity)}</span>
        <span class="finding-desc">${esc(event.description)}</span>
      </div>
      <div class="finding-risk" id="risk-${event.index}"></div>`;
    list.appendChild(card);
    card.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

    // Typewriter effect for risk text
    typewrite(`risk-${event.index}`, event.risk);
  }

  function typewrite(elementId, text) {
    const el = document.getElementById(elementId);
    if (!el) return;
    el.classList.add('typing');
    let i = 0;
    const speed = 15; // ms per character
    function tick() {
      if (i < text.length) {
        el.textContent += text[i];
        i++;
        setTimeout(tick, speed);
      } else {
        el.classList.remove('typing');
      }
    }
    tick();
  }

  function showComplete(event) {
    // Keep findings visible, show summary below
    document.getElementById('demo-complete').classList.remove('hidden');
    document.getElementById('summary-domain').textContent = event.domain;

    const elapsed = ((performance.now() - demoStartTime) / 1000).toFixed(1);
    const count = event.findings_count;
    document.getElementById('summary-text').textContent =
      `Assessment complete. ${count} security finding${count !== 1 ? 's' : ''} identified in ${elapsed} seconds.`;

    document.getElementById('demo-restart').onclick = resetDemo;

    // Scroll to summary
    document.getElementById('demo-complete').scrollIntoView({ behavior: 'smooth' });
  }

  // ---- Utility ----

  function esc(str) {
    if (!str) return '';
    const d = document.createElement('div');
    d.textContent = str;
    return d.innerHTML;
  }

  // ---- PWA service worker ----

  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/static/sw.js').catch(() => {});
  }

  // ---- Initialise ----

  startMonitor();
})();
