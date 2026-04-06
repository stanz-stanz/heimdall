<script>
  let { label = '', value = '', sub = '', color = 'gold', icon = '' } = $props();
</script>

<div class="card stat-{color}">
  <div class="card-header">
    <span class="card-label">{label}</span>
    {#if icon}
      <span class="card-icon">{icon}</span>
    {/if}
  </div>
  <span class="card-value">{value}</span>
  {#if sub}
    <span class="card-sub">{sub}</span>
  {/if}
</div>
