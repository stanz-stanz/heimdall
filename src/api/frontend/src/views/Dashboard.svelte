<script>
  import StatCard from '../components/StatCard.svelte';
  import FeedItem from '../components/FeedItem.svelte';
  import { fetchDashboard } from '../lib/api.js';
  import { wsState } from '../lib/ws.svelte.js';
  import { navigate } from '../lib/router.svelte.js';
  import { onMount, untrack } from 'svelte';

  let stats = $state({ prospects: 0, briefs: 0, clients: 0, critical: 0 });
  let displayStats = $state({ prospects: 0, briefs: 0, clients: 0, critical: 0 });
  let activity = $state([]);
  let queues = $state({ scan: 0, enrichment: 0, cache: 0 });
  let queueSubs = $state({ scan: 'idle', enrichment: 'idle', cache: '' });
  let timestamp = $state('');
  let loaded = $state(false);

  function animateCounter(key, target) {
    const duration = 600;
    const start = displayStats[key];
    const diff = target - start;
    if (diff === 0) return;
    const startTime = performance.now();

    function tick(now) {
      const elapsed = now - startTime;
      const progress = Math.min(elapsed / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      displayStats[key] = Math.round(start + diff * eased);
      if (progress < 1) requestAnimationFrame(tick);
    }

    requestAnimationFrame(tick);
  }

  function activityTarget(item) {
    const type = (item.type ?? item.source ?? '').toString();
    if (type.includes('pipeline')) return { view: 'pipeline', params: {} };
    if (type.includes('delivery')) return { view: 'clients', params: {} };
    if (type.includes('campaign')) return { view: 'campaigns', params: {} };
    if (type.includes('interpret')) return { view: 'logs', params: { source: 'delivery' } };
    return null;
  }

  function formatActivity(item) {
    const type = item.type ?? '';
    let color = 'var(--text-muted)';
    let text = item.text ?? item.message ?? JSON.stringify(item);
    let time = item.time ?? '';

    if (type === 'pipeline_complete' || type === 'scan_complete') {
      color = 'var(--green)';
      const dc = item.domain_count ?? item.payload?.domain_count ?? '';
      const fc = item.finding_count ?? item.payload?.finding_count ?? '';
      text = `Pipeline completed — ${dc.toLocaleString()} domains scanned, ${fc.toLocaleString()} findings`;
    } else if (type === 'campaign_promoted' || type.includes('campaign')) {
      color = 'var(--gold)';
    } else if (type === 'interpreted' || type.includes('interpret')) {
      color = 'var(--blue)';
    } else if (type === 'delivery' || type.includes('deliver') || type.includes('acknowledged')) {
      color = 'var(--green)';
    } else if (type.includes('error') || type.includes('fail')) {
      color = 'var(--red)';
    } else {
      color = 'var(--orange)';
    }

    return { color, text, time };
  }

  onMount(async () => {
    try {
      const data = await fetchDashboard();
      stats = {
        prospects: data.prospects ?? 0,
        briefs: data.briefs ?? 0,
        clients: data.clients ?? 0,
        critical: data.critical ?? 0,
      };
      activity = (data.activity ?? []).slice(0, 10);
      if (data.queues) {
        queues = {
          scan: data.queues.scan ?? 0,
          enrichment: data.queues.enrichment ?? 0,
          cache: data.queues.cache ?? 0,
        };
        queueSubs = {
          scan: data.queues.scan > 0 ? `${data.queues.scan} pending` : 'idle',
          enrichment: data.queues.enrichment > 0 ? `${data.queues.enrichment} pending` : 'idle',
          cache: data.queues.cache > 0 ? `${data.queues.cache} unique interpretations cached` : 'idle',
        };
      }
      timestamp = data.timestamp ?? '';
      loaded = true;

      // Animate counters from 0 to target
      for (const key of ['prospects', 'briefs', 'clients', 'critical']) {
        animateCounter(key, stats[key]);
      }
    } catch (err) {
      console.error('Dashboard fetch failed:', err);
      loaded = true;
    }
  });

  // Live-update from WebSocket
  $effect(() => {
    const msg = wsState.lastMessage;
    if (!msg) return;

    untrack(() => {
      if (msg.type === 'queue_status' && msg.payload) {
        const p = msg.payload;
        queues = {
          scan: p.scan ?? queues.scan,
          enrichment: p.enrichment ?? queues.enrichment,
          cache: p.cache ?? queues.cache,
        };
        queueSubs = {
          scan: queues.scan > 0 ? `${queues.scan} pending` : 'idle',
          enrichment: queues.enrichment > 0 ? `${queues.enrichment} pending` : 'idle',
          cache: queues.cache > 0 ? `${queues.cache} unique interpretations cached` : 'idle',
        };
      }

      if (msg.type === 'activity' && msg.payload) {
        activity = [msg.payload, ...activity].slice(0, 10);
      }
    });
  });
</script>

<div class="grid grid-4">
  <StatCard
    label="Prospects"
    value={displayStats.prospects.toLocaleString()}
    sub="across all campaigns"
    color="gold"
    icon="&#9733;"
    onclick={() => navigate('prospects')}
  />
  <StatCard
    label="Briefs"
    value={displayStats.briefs.toLocaleString()}
    sub={timestamp ? `last scan: ${timestamp}` : ''}
    color="blue"
    icon="&#9830;"
    onclick={() => navigate('prospects', { has_brief: '1' })}
  />
  <StatCard
    label="Clients"
    value={displayStats.clients.toLocaleString()}
    sub="all active"
    color="green"
    icon="&#9826;"
    onclick={() => navigate('clients')}
  />
  <StatCard
    label="Critical"
    value={displayStats.critical.toLocaleString()}
    sub="across all briefs"
    color="red"
    icon="&#9888;"
    onclick={() => navigate('prospects', { critical: '1' })}
  />
</div>

<div class="section-header" style="margin-top: 28px;">
  <span class="section-title">Recent Activity</span>
  <button class="btn btn-ghost btn-sm" onclick={() => navigate('logs')}>View all</button>
</div>

<div class="feed">
  {#each activity as item}
    {@const formatted = formatActivity(item)}
    {@const target = activityTarget(item)}
    {#if target}
      <button class="feed-link" onclick={() => navigate(target.view, target.params)}>
        <FeedItem color={formatted.color} text={formatted.text} time={formatted.time} />
      </button>
    {:else}
      <FeedItem color={formatted.color} text={formatted.text} time={formatted.time} />
    {/if}
  {/each}
  {#if activity.length === 0 && loaded}
    <div class="empty-state" style="padding: 30px;">
      <span class="empty-state-text">No recent activity</span>
    </div>
  {/if}
</div>

<div class="section-header" style="margin-top: 28px;">
  <span class="section-title">Queue Status</span>
</div>

<div class="grid grid-3">
  <button class="card card-button" onclick={() => navigate('logs', { source: 'worker' })}>
    <div class="card-label">Scan Queue</div>
    <div class="card-value" style="color: var(--text)">{queues.scan}</div>
    <div class="card-sub">{queueSubs.scan}</div>
  </button>
  <button class="card card-button" onclick={() => navigate('logs', { source: 'scheduler' })}>
    <div class="card-label">Enrichment</div>
    <div class="card-value" style="color: var(--text)">{queues.enrichment}</div>
    <div class="card-sub">{queueSubs.enrichment}</div>
  </button>
  <button class="card card-button" onclick={() => navigate('logs', { source: 'delivery' })}>
    <div class="card-label">Interpretation Cache</div>
    <div class="card-value" style="color: var(--text)">{queues.cache}</div>
    <div class="card-sub">{queueSubs.cache}</div>
  </button>
</div>

<style>
  .feed-link {
    display: block;
    width: 100%;
    background: transparent;
    border: none;
    padding: 0;
    margin: 0;
    text-align: left;
    cursor: pointer;
    color: inherit;
    border-radius: var(--radius-sm);
    transition: background var(--transition);
  }

  .feed-link:hover {
    background: var(--bg-hover);
  }

  .feed-link:focus-visible {
    outline: none;
    box-shadow: 0 0 0 2px var(--gold-glow);
  }

  .card-button {
    display: block;
    width: 100%;
    text-align: left;
    font: inherit;
    color: inherit;
    cursor: pointer;
    transition: border-color var(--transition), background var(--transition);
  }

  .card-button:hover {
    border-color: var(--gold);
    background: var(--bg-hover);
  }

  .card-button:focus-visible {
    outline: none;
    border-color: var(--gold);
    box-shadow: 0 0 0 2px var(--gold-glow);
  }
</style>
