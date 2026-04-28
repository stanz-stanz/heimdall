<script>
  import { router } from '../lib/router.svelte.js';
  import { auth, logout } from '../lib/auth.svelte.js';
  import { onMount } from 'svelte';
  import ThemeToggle from './ThemeToggle.svelte';

  let clock = $state('');
  let loggingOut = $state(false);

  function updateClock() {
    const now = new Date();
    const y = now.getFullYear();
    const mo = String(now.getMonth() + 1).padStart(2, '0');
    const d = String(now.getDate()).padStart(2, '0');
    const h = String(now.getHours()).padStart(2, '0');
    const mi = String(now.getMinutes()).padStart(2, '0');
    clock = `${y}-${mo}-${d} ${h}:${mi}`;
  }

  onMount(() => {
    updateClock();
    const interval = setInterval(updateClock, 60_000);
    return () => clearInterval(interval);
  });

  async function handleLogout() {
    if (loggingOut) return;
    loggingOut = true;
    try {
      await logout();
    } finally {
      loggingOut = false;
    }
  }

  let displayName = $derived(auth.operator?.display_name ?? auth.operator?.username ?? '');
</script>

<header class="topbar">
  <h2 class="topbar-title t-heading">{router.title}</h2>
  <div class="topbar-right">
    {#if displayName}
      <span class="topbar-operator t-mono-label" title="Signed in as {displayName}">
        {displayName}
      </span>
    {/if}
    <span class="topbar-clock t-mono-label">{clock}</span>
    <ThemeToggle />
    {#if auth.status === 'authenticated'}
      <button
        type="button"
        class="topbar-logout"
        onclick={handleLogout}
        disabled={loggingOut}
        title="Sign out"
      >
        {loggingOut ? 'Signing out…' : 'Log out'}
      </button>
    {/if}
  </div>
</header>

<style>
  .topbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 16px 28px;
    border-bottom: 1px solid var(--border-subtle);
    background: var(--bg-base);
  }

  .topbar-title {
    color: var(--text);
  }

  .topbar-right {
    display: flex;
    align-items: center;
    gap: 14px;
  }

  .topbar-operator {
    color: var(--text);
    padding: 4px 8px;
    border-radius: 6px;
    background: var(--bg-raised);
    border: 1px solid var(--border-subtle);
  }

  .topbar-clock {
    color: var(--text-dim);
  }

  .topbar-logout {
    padding: 6px 12px;
    border: 1px solid var(--border);
    border-radius: 6px;
    background: var(--bg-raised);
    color: var(--text);
    font: inherit;
    font-size: 0.92em;
    cursor: pointer;
    transition: background-color 120ms ease, border-color 120ms ease;
  }

  .topbar-logout:hover:not(:disabled) {
    background: var(--bg-hover);
    border-color: var(--gold);
  }

  .topbar-logout:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
</style>
