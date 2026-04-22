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
  import { router } from './lib/router.svelte.js';
  import { connect, disconnect, wsState } from './lib/ws.svelte.js';
  import { fetchDashboard } from './lib/api.js';
  import { onMount } from 'svelte';

  let campaignCount = $state(0);
  let prospectCount = $state(0);
  let clientCount = $state(0);

  onMount(() => {
    connect();
    fetchDashboard().then(d => {
      prospectCount = d.prospects ?? 0;
      clientCount = d.clients ?? 0;
    }).catch(() => {});
    fetch('/console/campaigns').then(r => r.json()).then(c => {
      campaignCount = Array.isArray(c) ? c.length : 0;
    }).catch(() => {});
    return () => disconnect();
  });
</script>

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
</style>
