<script>
  import Sidebar from './components/Sidebar.svelte';
  import Topbar from './components/Topbar.svelte';
  import Dashboard from './views/Dashboard.svelte';
  import Pipeline from './views/Pipeline.svelte';
  import Campaigns from './views/Campaigns.svelte';
  import Prospects from './views/Prospects.svelte';
  import Briefs from './views/Briefs.svelte';
  import Clients from './views/Clients.svelte';
  import Logs from './views/Logs.svelte';
  import LiveDemo from './views/LiveDemo.svelte';
  import Settings from './views/Settings.svelte';
  import Login from './views/Login.svelte';
  import BootstrapEmpty from './views/BootstrapEmpty.svelte';
  import AllDisabled from './views/AllDisabled.svelte';
  import { router } from './lib/router.svelte.js';
  import { connect, disconnect } from './lib/ws.svelte.js';
  import { fetchDashboard, fetchCampaigns } from './lib/api.js';
  import { auth, bootstrap } from './lib/auth.svelte.js';
  import { onMount } from 'svelte';

  let campaignCount = $state(0);
  let prospectCount = $state(0);
  let clientCount = $state(0);
  let shellInitialised = $state(false);

  async function initialiseShell() {
    shellInitialised = true;
    connect();
    try {
      const d = await fetchDashboard();
      prospectCount = d.prospects ?? 0;
      clientCount = d.clients ?? 0;
    } catch {
      // fetchDashboard throws on 401, which lib/api.js has already
      // turned into a session-expired probe; the auth state machine
      // will route the SPA back to the login view on the next tick.
    }
    try {
      const c = await fetchCampaigns();
      campaignCount = Array.isArray(c) ? c.length : 0;
    } catch {
      // Same 401 treatment as fetchDashboard — go through lib/api.js
      // so a session-expired campaigns probe can't silently strand
      // the shell in a half-authenticated state.
    }
  }

  onMount(() => {
    bootstrap();
    return () => disconnect();
  });

  // Spec §2.5 — when auth bootstraps to (or transitions into)
  // 'authenticated', wire up the WebSocket + initial fetches. When
  // status leaves 'authenticated' (logout, mid-session 401, operator
  // disabled mid-session, all-disabled state probed), tear down the
  // WS so an already-open /console/ws doesn't keep streaming behind
  // the login screen, and reset shell counters so the next login
  // doesn't render the prior session's snapshot.
  $effect(() => {
    if (auth.status === 'authenticated' && !shellInitialised) {
      initialiseShell();
    } else if (auth.status !== 'authenticated' && shellInitialised) {
      shellInitialised = false;
      disconnect();
      campaignCount = 0;
      prospectCount = 0;
      clientCount = 0;
    }
  });
</script>

{#if auth.status === 'loading'}
  <div class="boot-shell" aria-busy="true"></div>
{:else if auth.status === 'bootstrap-empty'}
  <BootstrapEmpty />
{:else if auth.status === 'all-disabled'}
  <AllDisabled />
{:else if auth.status === 'authenticated'}
  <Sidebar {campaignCount} {prospectCount} {clientCount} />
  <main class="main">
    <Topbar />
    <div class="content">
      {#if router.view === 'dashboard'}
        <Dashboard />
      {:else if router.view === 'pipeline'}
        <Pipeline />
      {:else if router.view === 'campaigns'}
        <Campaigns />
      {:else if router.view === 'prospects'}
        <Prospects />
      {:else if router.view === 'briefs'}
        <Briefs />
      {:else if router.view === 'clients'}
        <Clients />
      {:else if router.view === 'logs'}
        <Logs />
      {:else if router.view === 'demo'}
        <LiveDemo />
      {:else if router.view === 'settings'}
        <Settings />
      {/if}
    </div>
  </main>
{:else}
  <Login />
{/if}

<style>
  .main {
    flex: 1;
    display: flex;
    flex-direction: column;
    min-width: 0;
    height: 100vh;
  }

  .content {
    flex: 1;
    overflow-y: auto;
    padding: 28px;
  }

  .boot-shell {
    width: 100%;
    min-height: 100vh;
    background: var(--bg-deep);
  }
</style>
