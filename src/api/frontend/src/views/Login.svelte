<script>
  import { auth, login, tickRateLimit } from '../lib/auth.svelte.js';
  import { onDestroy } from 'svelte';

  let username = $state('');
  let password = $state('');
  let submitting = $state(false);
  let countdownTimer = null;

  $effect(() => {
    // Drive the rate-limit countdown when the auth state machine
    // says we're throttled. Effect re-fires when status changes.
    if (auth.status === 'rate-limited') {
      if (!countdownTimer) {
        countdownTimer = setInterval(() => {
          tickRateLimit();
        }, 1000);
      }
    } else if (countdownTimer) {
      clearInterval(countdownTimer);
      countdownTimer = null;
    }
  });

  onDestroy(() => {
    if (countdownTimer) clearInterval(countdownTimer);
    countdownTimer = null;
  });

  async function handleSubmit(event) {
    event.preventDefault();
    if (submitting || auth.status === 'rate-limited') return;
    if (!username || !password) {
      auth.error = 'invalid_credentials';
      return;
    }
    submitting = true;
    try {
      const ok = await login(username, password);
      if (ok) password = '';
    } finally {
      submitting = false;
    }
  }

  let errorMessage = $derived.by(() => {
    if (auth.status === 'rate-limited') {
      return `Too many failed attempts. Try again in ${auth.retryAfter}s.`;
    }
    switch (auth.error) {
      case 'invalid_credentials':
        return 'Invalid username or password.';
      case 'service_unavailable':
        return 'Server unavailable. Please try again.';
      case 'network':
        return 'Network error. Check your connection and retry.';
      case 'rate_limited':
        return null; // handled by the status branch above
      case null:
      case undefined:
        return null;
      default:
        return 'Login failed. Please try again.';
    }
  });

  let formDisabled = $derived(submitting || auth.status === 'rate-limited');
</script>

<div class="login-shell">
  <div class="login-card">
    <h1 class="login-title t-heading">Heimdall Console</h1>
    <p class="login-subtitle t-help">Sign in with your operator credentials.</p>

    <form class="login-form" onsubmit={handleSubmit} novalidate>
      <label class="field">
        <span class="field-label t-mono-label">Username</span>
        <input
          type="text"
          autocomplete="username"
          autocapitalize="none"
          spellcheck="false"
          bind:value={username}
          disabled={formDisabled}
          required
        />
      </label>

      <label class="field">
        <span class="field-label t-mono-label">Password</span>
        <input
          type="password"
          autocomplete="current-password"
          bind:value={password}
          disabled={formDisabled}
          required
        />
      </label>

      {#if errorMessage}
        <div class="login-error" role="alert">{errorMessage}</div>
      {/if}

      <button type="submit" class="login-submit" disabled={formDisabled}>
        {#if submitting}
          Signing in…
        {:else if auth.status === 'rate-limited'}
          Wait {auth.retryAfter}s
        {:else}
          Sign in
        {/if}
      </button>
    </form>
  </div>
</div>

<style>
  .login-shell {
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 100vh;
    width: 100%;
    padding: 24px;
    background: var(--bg-deep);
  }

  .login-card {
    width: 100%;
    max-width: 420px;
    padding: 36px 32px;
    border: 1px solid var(--border);
    border-radius: 12px;
    background: var(--bg-base);
    box-shadow: 0 24px 64px rgba(0, 0, 0, 0.32);
  }

  .login-title {
    margin: 0 0 6px;
    color: var(--text);
  }

  .login-subtitle {
    margin: 0 0 28px;
    color: var(--text-dim);
  }

  .login-form {
    display: flex;
    flex-direction: column;
    gap: 18px;
  }

  .field {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .field-label {
    color: var(--text-dim);
  }

  .field input {
    width: 100%;
    padding: 11px 14px;
    border: 1px solid var(--border);
    border-radius: 8px;
    background: var(--bg-raised);
    color: var(--text);
    font: inherit;
    transition: border-color 120ms ease, box-shadow 120ms ease;
  }

  .field input:focus {
    outline: none;
    border-color: var(--gold);
    box-shadow: 0 0 0 3px var(--gold-glow);
  }

  .field input:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  .login-error {
    padding: 10px 12px;
    border: 1px solid var(--red-outline);
    border-radius: 8px;
    background: var(--red-muted);
    color: var(--red-soft);
    font-size: 0.92em;
  }

  .login-submit {
    margin-top: 4px;
    padding: 12px 14px;
    border: 1px solid var(--gold);
    border-radius: 8px;
    background: var(--gold);
    color: #1a1206;
    font: inherit;
    font-weight: 600;
    cursor: pointer;
    transition: background-color 120ms ease, opacity 120ms ease;
  }

  .login-submit:hover:not(:disabled) {
    background: var(--gold-dim);
  }

  .login-submit:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
</style>
