<script>
  let { color = 'var(--text-muted)', text = '', time = '' } = $props();
</script>

<div class="feed-item">
  <span class="feed-dot" style="background: {color}"></span>
  <span class="feed-text">{text}</span>
  <span class="feed-time">{time}</span>
</div>
