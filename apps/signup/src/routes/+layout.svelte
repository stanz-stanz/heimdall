<script>
  import '../app.css';
  import { t } from '$lib/i18n';
</script>

<nav class="nav">
  <a class="brand" href="/">{t('nav.brand')}</a>
  <ul class="nav-links">
    <li><a href="/pricing">{t('nav.pricing')}</a></li>
  </ul>
</nav>

<main>
  <slot />
</main>

<footer class="footer">
  <p class="muted">{t('footer.copyright')}</p>
  <ul class="legal-links">
    <li><a href="/legal/privacy">{t('footer.legal.privacy')}</a></li>
    <li><a href="/legal/terms">{t('footer.legal.terms')}</a></li>
    <li><a href="/legal/dpa">{t('footer.legal.dpa')}</a></li>
  </ul>
</footer>

<style>
  .nav {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 1rem 1.5rem;
    border-bottom: 1px solid var(--border);
    max-width: 960px;
    margin: 0 auto;
  }
  .brand {
    font-weight: 700;
    color: var(--gold);
    font-size: 1.1rem;
  }
  .nav-links,
  .legal-links {
    display: flex;
    gap: 1.25rem;
    margin: 0;
    padding: 0;
    list-style: none;
  }
  .footer {
    max-width: 960px;
    margin: 4rem auto 2rem;
    padding: 1.5rem;
    border-top: 1px solid var(--border-subtle);
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    flex-wrap: wrap;
  }
</style>
