<script>
  let {
    label = '',
    value = '',
    sub = '',
    color = 'gold',
    icon = '',
    onclick = null,
  } = $props();

  const clickable = typeof onclick === 'function';

  function handleKeydown(event) {
    if (!clickable) return;
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      onclick(event);
    }
  }
</script>

<div
  class="card stat-{color}"
  class:clickable
  role={clickable ? 'button' : null}
  tabindex={clickable ? 0 : null}
  onclick={clickable ? onclick : null}
  onkeydown={clickable ? handleKeydown : null}
>
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

<style>
  .card.clickable {
    cursor: pointer;
    transition: border-color var(--transition), background var(--transition);
  }

  .card.clickable:hover {
    border-color: var(--gold);
    background: var(--bg-hover);
  }

  .card.clickable:focus-visible {
    outline: none;
    border-color: var(--gold);
    box-shadow: 0 0 0 2px var(--gold-glow);
  }
</style>
