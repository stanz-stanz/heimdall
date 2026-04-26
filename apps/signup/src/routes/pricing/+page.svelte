<script>
  import { t } from '$lib/i18n';
  import pricing from '$lib/pricing.json';
</script>

<svelte:head>
  <title>{$t('pricing.h1')} — {$t('nav.brand')}</title>
</svelte:head>

<section class="container">
  <h1>{$t('pricing.h1')}</h1>
  <p class="lede">{$t('pricing.subtitle')}</p>

  <div class="cards">
    {#each pricing.plans as plan}
      <article class="card">
        <h2>{plan.name}</h2>
        <p class="price">
          <span class="amount">{plan.price_monthly}</span>
          <span class="unit">{pricing.currency} {$t('pricing.unit.per_month')}</span>
        </p>
        <p class="muted">{$t(plan.i18n.tagline)}</p>
        <ul class="features">
          {#each plan.i18n.features as featureKey}
            <li>{$t(featureKey)}</li>
          {/each}
        </ul>
        <a class="btn" href="mailto:hello@digitalvagt.dk?subject=Interested in {plan.name}">
          {$t('pricing.cta.email')}
        </a>
      </article>
    {/each}
  </div>
</section>

<style>
  .cards {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    gap: 1.5rem;
    margin-top: 2rem;
    padding-bottom: 3rem;
  }
  .card {
    padding: 1.5rem;
    background: var(--bg-raised);
    border: 1px solid var(--border);
    border-radius: 8px;
  }
  .price {
    display: flex;
    align-items: baseline;
    gap: 0.5rem;
    margin: 0.5rem 0 1rem;
  }
  .amount {
    font-size: 2.25rem;
    font-weight: 700;
    color: var(--gold);
  }
  .unit {
    color: var(--text-dim);
  }
  .features {
    list-style: none;
    padding: 0;
    margin: 0 0 1.5rem;
  }
  .features li {
    padding: 0.4rem 0;
    border-top: 1px solid var(--border-subtle);
  }
  .features li:first-child {
    border-top: 0;
  }
</style>
