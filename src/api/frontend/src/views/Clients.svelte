<!--
  Clients view — tab host for three operator-console panes:

    Onboarded       (existing — active/onboarding clients)
    Trial expiring  (V1, read-only)
    Retention queue (V6, with force-run / cancel / retry actions)

  Tab state persists via router.params.tab (#/clients?tab=trial-expiring),
  so deep-links and refreshes preserve the operator's last view. Default
  tab is "onboarded" — opening the view from the sidebar lands on the
  same screen the previous Clients page used to show.

  Counts in tab labels come from each child view via an onCount
  callback prop. They render as small parenthesised badges and only
  appear once the child has loaded its data (null until then).
-->

<script>
  import { onMount } from 'svelte';
  import { router, navigate } from '../lib/router.svelte.js';
  import Onboarded from './clients/Onboarded.svelte';
  import TrialExpiring from './clients/TrialExpiring.svelte';
  import RetentionQueue from './clients/RetentionQueue.svelte';

  const TABS = [
    { id: 'onboarded', label: 'Onboarded' },
    { id: 'trial-expiring', label: 'Trial expiring' },
    { id: 'retention', label: 'Retention queue' },
  ];

  let trialCount = $state(null);
  let retentionCount = $state(null);

  let activeTab = $derived.by(() => {
    const t = router.params?.tab ?? 'onboarded';
    return TABS.some((tab) => tab.id === t) ? t : 'onboarded';
  });

  function selectTab(id) {
    navigate('clients', { tab: id === 'onboarded' ? '' : id });
  }
</script>

<div class="config-tabs" role="tablist">
  {#each TABS as tab}
    <button
      class="config-tab"
      class:active={activeTab === tab.id}
      role="tab"
      aria-selected={activeTab === tab.id}
      onclick={() => selectTab(tab.id)}
    >
      {tab.label}
      {#if tab.id === 'trial-expiring' && trialCount !== null && trialCount > 0}
        <span class="tab-count">({trialCount})</span>
      {/if}
      {#if tab.id === 'retention' && retentionCount !== null && retentionCount > 0}
        <span class="tab-count">({retentionCount})</span>
      {/if}
    </button>
  {/each}
</div>

<div class="tab-pane">
  {#if activeTab === 'onboarded'}
    <Onboarded />
  {:else if activeTab === 'trial-expiring'}
    <TrialExpiring onCount={(n) => (trialCount = n)} />
  {:else if activeTab === 'retention'}
    <RetentionQueue onCount={(n) => (retentionCount = n)} />
  {/if}
</div>

<style>
  .tab-pane {
    margin-top: 20px;
  }

  .tab-count {
    margin-left: 4px;
    color: var(--gold);
    font-weight: 500;
  }
</style>
