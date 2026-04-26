<script>
  import { locale, setLocale, SUPPORTED_LOCALES } from '$lib/i18n';

  const labels = { en: 'EN', da: 'DA' };
</script>

<div class="locale-toggle" role="group" aria-label="Language">
  {#each SUPPORTED_LOCALES as code, i}
    {#if i > 0}<span class="sep" aria-hidden="true">|</span>{/if}
    <button
      type="button"
      class:active={$locale === code}
      aria-pressed={$locale === code}
      onclick={() => setLocale(code)}
    >{labels[code]}</button>
  {/each}
</div>

<style>
  .locale-toggle {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    font-size: 0.85rem;
  }
  .locale-toggle button {
    background: none;
    border: 0;
    padding: 0.2rem 0.45rem;
    color: var(--text-dim);
    font: inherit;
    cursor: pointer;
    border-radius: 4px;
  }
  .locale-toggle button:hover {
    color: var(--text);
  }
  .locale-toggle button.active {
    color: var(--text);
    font-weight: 700;
  }
  .sep {
    color: var(--text-dim);
    opacity: 0.5;
  }
</style>
