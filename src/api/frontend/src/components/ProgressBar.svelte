<script>
  let { pct = 0, label = '', message = '' } = $props();
</script>

<div class="progress-strip">
  <div class="progress-label">{label}</div>
  <div class="progress-bar-track">
    <div class="progress-bar-fill" style="width: {Math.min(Math.max(pct, 0), 100)}%"></div>
  </div>
  {#if message}
    <div class="progress-msg">{message}</div>
  {/if}
</div>
