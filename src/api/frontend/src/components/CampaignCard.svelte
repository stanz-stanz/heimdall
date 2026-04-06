<script>
  let { campaign = {}, oninterpret = null, onviewprospects = null } = $props();

  let total = $derived((campaign.total ?? 0) || 1);
  let newCount = $derived(campaign.new_count ?? 0);
  let interpreted = $derived(campaign.interpreted_count ?? 0);
  let sent = $derived(campaign.sent_count ?? 0);
  let failed = $derived(campaign.failed_count ?? 0);

  let newPct = $derived((newCount / total) * 100);
  let interpPct = $derived((interpreted / total) * 100);
  let sentPct = $derived((sent / total) * 100);

  let hasUninterpreted = $derived(newCount > 0);
</script>

<div class="campaign-card">
  <div class="campaign-name">{campaign.campaign ?? 'Untitled'}</div>
  <div class="campaign-desc">{campaign.total ?? 0} prospects</div>

  <div class="campaign-stats">
    <div class="campaign-stat">
      <div class="campaign-stat-value" style="color: var(--text-dim)">{newCount}</div>
      <div class="campaign-stat-label">New</div>
    </div>
    <div class="campaign-stat">
      <div class="campaign-stat-value" style="color: var(--blue)">{interpreted}</div>
      <div class="campaign-stat-label">Interpreted</div>
    </div>
    <div class="campaign-stat">
      <div class="campaign-stat-value" style="color: var(--gold)">{sent}</div>
      <div class="campaign-stat-label">Sent</div>
    </div>
    <div class="campaign-stat">
      <div class="campaign-stat-value" style="color: var(--red)">{failed}</div>
      <div class="campaign-stat-label">Failed</div>
    </div>
  </div>

  <div class="campaign-bar">
    <div class="campaign-bar-segments" style="display:flex; height:100%;">
      {#if newPct > 0}
        <div style="width: {newPct}%; background: var(--bg-hover); height: 100%;"></div>
      {/if}
      {#if interpPct > 0}
        <div style="width: {interpPct}%; background: var(--blue); height: 100%;"></div>
      {/if}
      {#if sentPct > 0}
        <div style="width: {sentPct}%; background: var(--gold); height: 100%;"></div>
      {/if}
    </div>
  </div>

  <div class="campaign-actions">
    {#if oninterpret}
      <button
        class="btn btn-sm"
        class:btn-primary={hasUninterpreted}
        class:btn-ghost={!hasUninterpreted}
        onclick={() => oninterpret(campaign)}
      >
        {hasUninterpreted ? 'Interpret Next 10' : 'All Interpreted'}
      </button>
    {/if}
    {#if onviewprospects}
      <button class="btn btn-ghost btn-sm" onclick={() => onviewprospects(campaign)}>
        View Prospects
      </button>
    {/if}
  </div>
</div>

<style>
  .campaign-desc {
    font-size: 12px;
    color: var(--text-muted);
    margin-top: 2px;
  }

  .campaign-stats {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 8px;
    margin-top: 14px;
  }

  .campaign-stat {
    text-align: center;
  }

  .campaign-stat-value {
    font-family: var(--mono);
    font-size: 18px;
    font-weight: 700;
    line-height: 1;
  }

  .campaign-stat-label {
    font-size: 9px;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: var(--text-muted);
    margin-top: 4px;
  }

  .campaign-actions {
    margin-top: 14px;
    display: flex;
    gap: 8px;
  }
</style>
