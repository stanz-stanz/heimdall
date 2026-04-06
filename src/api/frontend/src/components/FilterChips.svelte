<script>
  let { options = [], active = '', onSelect = () => {} } = $props();
</script>

<div class="filters">
  {#each options as opt}
    <button
      class="filter-chip"
      class:active={active === opt.value}
      onclick={() => onSelect(opt.value)}
    >
      {opt.label}
      {#if opt.count !== undefined}
        <span class="filter-count">{opt.count}</span>
      {/if}
    </button>
  {/each}
</div>

<style>
  .filter-count {
    font-family: var(--mono);
    font-size: 11px;
    opacity: 0.7;
  }
</style>
