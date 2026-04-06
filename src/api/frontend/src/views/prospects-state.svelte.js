/** Shared state for the selected campaign between Campaigns and Prospects views. */

let selectedCampaign = $state('');

export function getSelectedCampaign() {
  return selectedCampaign;
}

export function setSelectedCampaign(campaign) {
  selectedCampaign = campaign;
}
