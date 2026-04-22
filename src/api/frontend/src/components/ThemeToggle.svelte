<script>
  import { theme, toggleTheme } from '../lib/theme.svelte.js';

  let label = $derived(
    theme.mode === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'
  );
</script>

<button
  type="button"
  class="theme-toggle"
  aria-label={label}
  title={label}
  aria-pressed={theme.mode === 'light'}
  onclick={toggleTheme}
>
  {#if theme.mode === 'dark'}
    <!-- sun icon: in dark mode, click → light -->
    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" />
    </svg>
  {:else}
    <!-- moon icon: in light mode, click → dark -->
    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
      <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
    </svg>
  {/if}
</button>

<style>
  .theme-toggle {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 34px;
    height: 34px;
    padding: 0;
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-sm);
    background: transparent;
    color: var(--text-dim);
    cursor: pointer;
    transition:
      color var(--transition),
      background-color var(--transition),
      border-color var(--transition);
  }

  .theme-toggle:hover {
    color: var(--gold);
    border-color: var(--border);
    background: var(--bg-hover);
  }

  .theme-toggle:focus-visible {
    outline: 2px solid var(--gold);
    outline-offset: 2px;
  }
</style>
