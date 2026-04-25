<script>
  import { t } from '$lib/i18n';
</script>

<svelte:head>
  <title>{t('nav.brand')} — {t('home.h1')}</title>
</svelte:head>

<section class="hero container">
  <h1>{t('home.h1')}</h1>
  <p class="lede">{t('home.subtitle')}</p>
  <div class="cta-row">
    <a class="btn" href="/pricing">{t('home.cta.primary')}</a>
    <a class="btn btn-outline" href="mailto:hello@digitalvagt.dk">
      {t('home.cta.secondary')}
    </a>
  </div>
</section>

<section class="container sections">
  <article>
    <h2>{t('home.section.howitworks.title')}</h2>
    <p>{t('home.section.howitworks.body')}</p>
  </article>
  <article>
    <h2>{t('home.section.whatwemonitor.title')}</h2>
    <p>{t('home.section.whatwemonitor.body')}</p>
  </article>
  <article>
    <h2>{t('home.section.pricing.title')}</h2>
    <p>{t('home.section.pricing.body')}</p>
    <a class="btn btn-outline" href="/pricing">{t('home.cta.primary')}</a>
  </article>
  <article>
    <h2>{t('home.section.faq.title')}</h2>
    <p>{t('home.section.faq.body')}</p>
  </article>
</section>

<style>
  .hero {
    padding-top: 4rem;
    padding-bottom: 2rem;
  }
  .lede {
    font-size: 1.15rem;
    color: var(--text-dim);
    max-width: 60ch;
  }
  .cta-row {
    display: flex;
    gap: 0.75rem;
    margin-top: 1.5rem;
    flex-wrap: wrap;
  }
  .sections {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
    gap: 2rem;
    padding-bottom: 3rem;
  }
</style>
