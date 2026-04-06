<script>
  import CampaignCard from '../components/CampaignCard.svelte';
  import { fetchCampaigns, sendCommand } from '../lib/api.js';
  import { navigate } from '../lib/router.svelte.js';
  import { setSelectedCampaign } from './prospects-state.svelte.js';
  import { onMount } from 'svelte';

  let campaigns = $state([]);
  let loaded = $state(false);

  onMount(async () => {
    try {
      campaigns = await fetchCampaigns();
    } catch (err) {
      console.error('Campaigns fetch failed:', err);
    }
    loaded = true;
  });

  function handleInterpret(campaign) {
    sendCommand('interpret', { campaign: campaign.campaign, limit: 10 }).catch(err => {
      console.error('Interpret command failed:', err);
    });
  }

  function handleViewProspects(campaign) {
    setSelectedCampaign(campaign.campaign);
    navigate('prospects', 'Prospects');
  }
</script>

<div class="section-header" style="margin-top: 0;">
  <span class="section-title">Active Campaigns</span>
  <button class="btn btn-primary" disabled>New Campaign</button>
</div>

{#if campaigns.length > 0}
  <div class="grid grid-2">
    {#each campaigns as c}
      <CampaignCard
        campaign={c}
        oninterpret={handleInterpret}
        onviewprospects={handleViewProspects}
      />
    {/each}
  </div>
{:else if loaded}
  <div class="empty-state">
    <span class="empty-state-text">No active campaigns</span>
  </div>
{/if}

<style>
  button:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }
</style>
