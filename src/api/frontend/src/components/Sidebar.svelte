<script>
  import { router, navigate } from '../lib/router.svelte.js';
  import { wsState } from '../lib/ws.svelte.js';

  let { campaignCount = 0, prospectCount = 0, clientCount = 0 } = $props();

  const navSections = [
    {
      label: 'Operations',
      items: [
        { id: 'dashboard', title: 'Dashboard', icon: '\u25A0' },
        { id: 'pipeline', title: 'Pipeline', icon: '\u25B6' },
        { id: 'campaigns', title: 'Campaigns', icon: '\u2605' },
        { id: 'prospects', title: 'Prospects', icon: '\u25CF' },
      ],
    },
    {
      label: 'Data',
      items: [
        { id: 'clients', title: 'Clients', icon: '\u2662' },
        { id: 'logs', title: 'Logs', icon: '\u2261' },
      ],
    },
    {
      label: 'System',
      items: [
        { id: 'demo', title: 'Live Demo', icon: '\u26A1', external: '/static/index.html' },
        { id: 'settings', title: 'Settings', icon: '\u2699' },
      ],
    },
  ];

  function getBadge(id) {
    if (id === 'campaigns' && campaignCount > 0) return campaignCount;
    if (id === 'prospects' && prospectCount > 0) return prospectCount;
    if (id === 'clients' && clientCount > 0) return clientCount;
    return null;
  }
</script>

<aside class="sidebar">
  <div class="brand">
    <h1 class="brand-title">Heimdall<span class="brand-dot">.</span></h1>
    <span class="brand-sub">Operator Console</span>
  </div>

  <nav class="nav">
    {#each navSections as section}
      <div class="nav-section">
        <span class="nav-section-label">{section.label}</span>
        {#each section.items as item}
          {@const active = router.view === item.id}
          <button
            class="nav-item"
            class:active
            onclick={() => item.external ? window.open(item.external, '_blank') : navigate(item.id, item.title)}
          >
            <span class="nav-icon">{item.icon}</span>
            <span class="nav-label">{item.title}</span>
            {#if getBadge(item.id) !== null}
              <span class="nav-badge">{getBadge(item.id)}</span>
            {/if}
          </button>
        {/each}
      </div>
    {/each}
  </nav>

  <div class="sidebar-footer">
    <span class="status-dot" class:online={wsState.connected}></span>
    <span class="status-text">
      {#if wsState.connected}
        Pi5 &middot; 3 workers &middot; Redis OK
      {:else}
        Disconnected
      {/if}
    </span>
  </div>
</aside>

<style>
  .sidebar {
    width: 220px;
    min-width: 220px;
    height: 100vh;
    background: var(--bg-base);
    border-right: 1px solid var(--border-subtle);
    display: flex;
    flex-direction: column;
    overflow-y: auto;
  }

  .brand {
    padding: 24px 20px 20px;
  }

  .brand-title {
    font-size: 22px;
    font-weight: 700;
    letter-spacing: -0.02em;
    color: var(--text);
  }

  .brand-dot {
    color: var(--gold);
  }

  .brand-sub {
    display: block;
    font-size: 11px;
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--text-muted);
    margin-top: 2px;
  }

  .nav {
    flex: 1;
    padding: 0 12px;
  }

  .nav-section {
    margin-bottom: 20px;
  }

  .nav-section-label {
    display: block;
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--text-muted);
    padding: 0 8px;
    margin-bottom: 6px;
  }

  .nav-item {
    display: flex;
    align-items: center;
    gap: 10px;
    width: 100%;
    padding: 8px 12px;
    border: none;
    border-radius: var(--radius-sm);
    background: transparent;
    color: var(--text-dim);
    font-family: var(--sans);
    font-size: 13px;
    font-weight: 500;
    cursor: pointer;
    transition: all var(--transition);
    position: relative;
    text-align: left;
  }

  .nav-item:hover {
    background: var(--bg-hover);
    color: var(--text);
  }

  .nav-item.active {
    background: var(--gold-glow);
    color: var(--gold);
  }

  .nav-item.active::before {
    content: '';
    position: absolute;
    left: 0;
    top: 6px;
    bottom: 6px;
    width: 3px;
    background: var(--gold);
    border-radius: 0 2px 2px 0;
  }

  .nav-icon {
    font-size: 14px;
    width: 18px;
    text-align: center;
    flex-shrink: 0;
  }

  .nav-label {
    flex: 1;
  }

  .nav-badge {
    font-family: var(--mono);
    font-size: 11px;
    font-weight: 600;
    background: var(--bg-surface);
    color: var(--text-dim);
    padding: 1px 6px;
    border-radius: var(--radius-xs);
  }

  .sidebar-footer {
    padding: 16px 20px;
    border-top: 1px solid var(--border-subtle);
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .status-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--red);
    flex-shrink: 0;
  }

  .status-dot.online {
    background: var(--green);
    animation: pulse-dot 2s ease-in-out infinite;
  }

  .status-text {
    font-size: 11px;
    color: var(--text-muted);
    font-family: var(--mono);
  }
</style>
