<script>
  import { onMount } from 'svelte';
  import QRCode from 'qrcode';
  import { post } from '$lib/api';
  import { t } from '$lib/i18n';

  let state = $state('checking');
  let botUsername = $state('');
  let token = $state('');
  let qrDataUrl = $state('');

  onMount(async () => {
    const url = new URL(window.location.href);
    token = url.searchParams.get('t') || '';

    if (!token) {
      state = 'invalid';
      replaceUrlWithoutToken();
      return;
    }

    const result = await post('/api/signup/validate', { token });

    if (!result.ok) {
      state = 'error';
      replaceUrlWithoutToken();
      return;
    }

    const data = result.data;
    if (data.ok === true) {
      botUsername = data.bot_username;
      state = 'ok';
      try {
        qrDataUrl = await QRCode.toDataURL(telegramDeepLink(), {
          width: 240,
          margin: 1,
          color: { dark: '#0b1120', light: '#f8fafc' },
        });
      } catch (e) {
        qrDataUrl = '';
      }
    } else if (data.reason === 'used') {
      state = 'used';
    } else if (data.reason === 'expired') {
      state = 'expired';
    } else {
      state = 'invalid';
    }

    replaceUrlWithoutToken();
  });

  function replaceUrlWithoutToken() {
    try {
      // Preserve SvelteKit's history state so router back/forward
      // navigation continues to receive the expected state keys.
      history.replaceState(history.state, '', '/signup/start');
    } catch (e) {
      // ignore
    }
  }

  function telegramDeepLink() {
    return `https://t.me/${encodeURIComponent(botUsername)}?start=${encodeURIComponent(token)}`;
  }

  const titles = {
    checking: 'signup.start.checking',
    ok: 'signup.start.ok.title',
    used: 'signup.start.used.title',
    expired: 'signup.start.expired.title',
    invalid: 'signup.start.invalid.title',
    error: 'signup.start.error.title',
  };
</script>

<svelte:head>
  <title>{$t(titles[state] || 'signup.start.checking')} — {$t('nav.brand')}</title>
</svelte:head>

<section class="container start-page">
  {#if state === 'checking'}
    <p class="muted">{$t('signup.start.checking')}</p>
  {:else if state === 'ok'}
    <h1>{$t('signup.start.ok.title')}</h1>
    <p>{$t('signup.start.ok.body')}</p>
    <a class="btn" href={telegramDeepLink()} rel="noopener noreferrer">
      {$t('signup.start.ok.cta')}
    </a>
    {#if qrDataUrl}
      <div class="qr">
        <img src={qrDataUrl} alt={$t('signup.start.ok.qr.alt')} width="240" height="240" />
      </div>
    {/if}
    <p class="muted fallback">{$t('signup.start.ok.fallback')}</p>
  {:else if state === 'used'}
    <h1>{$t('signup.start.used.title')}</h1>
    <p>{$t('signup.start.used.body')}</p>
    <a class="btn btn-outline" href="mailto:hello@digitalvagt.dk">
      {$t('home.cta.secondary')}
    </a>
  {:else if state === 'expired'}
    <h1>{$t('signup.start.expired.title')}</h1>
    <p>{$t('signup.start.expired.body')}</p>
    <a class="btn btn-outline" href="mailto:hello@digitalvagt.dk">
      {$t('home.cta.secondary')}
    </a>
  {:else if state === 'invalid'}
    <h1>{$t('signup.start.invalid.title')}</h1>
    <p>{$t('signup.start.invalid.body')}</p>
    <a class="btn btn-outline" href="mailto:hello@digitalvagt.dk">
      {$t('home.cta.secondary')}
    </a>
  {:else}
    <h1>{$t('signup.start.error.title')}</h1>
    <p>{$t('signup.start.error.body')}</p>
    <a class="btn btn-outline" href="mailto:hello@digitalvagt.dk">
      {$t('home.cta.secondary')}
    </a>
  {/if}
</section>

<style>
  .start-page {
    padding-top: 4rem;
    padding-bottom: 4rem;
    text-align: center;
  }
  .start-page p {
    margin-left: auto;
    margin-right: auto;
  }
  .qr {
    margin: 1.5rem auto 0;
    display: inline-block;
    padding: 0.5rem;
    background: var(--bg-raised);
    border: 1px solid var(--border);
    border-radius: 8px;
  }
  .fallback {
    margin-top: 2rem;
  }
</style>
