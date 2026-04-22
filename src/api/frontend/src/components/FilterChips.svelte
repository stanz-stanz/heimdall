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
        <span class="filter-count t-mono-label">{opt.count}</span>
      {/if}
    </button>
  {/each}
</div>

<style>
  .filter-count {
    opacity: 0.7;
  }
</style>
