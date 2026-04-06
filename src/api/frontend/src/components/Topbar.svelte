<script>
  import { router } from '../lib/router.svelte.js';
  import { onMount } from 'svelte';

  let clock = $state('');

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
</script>

<header class="topbar">
  <h2 class="topbar-title">{router.title}</h2>
  <span class="topbar-clock">{clock}</span>
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
    font-size: 18px;
    font-weight: 600;
    color: var(--text);
  }

  .topbar-clock {
    font-family: var(--mono);
    font-size: 13px;
    color: var(--text-muted);
  }
</style>
