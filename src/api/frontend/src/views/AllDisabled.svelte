<script>
  // Spec §7.5 Option B — distinct component for the "all operators
  // disabled" state. Operationally distinct from the empty bootstrap
  // splash: the recovery path is "re-enable an operator" (runbook
  // §9.2 password-reset / re-enable lever), not "seed the bootstrap".
</script>

<div class="splash-shell">
  <div class="splash-card">
    <h1 class="splash-title t-heading">All operators disabled</h1>
    <p class="splash-body t-help">
      Every Heimdall operator is currently disabled. Contact the owner
      or follow the operator re-enable runbook to restore access.
    </p>
  </div>
</div>

<style>
  .splash-shell {
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 100vh;
    width: 100%;
    padding: 24px;
    background: var(--bg-deep);
  }

  .splash-card {
    width: 100%;
    max-width: 480px;
    padding: 36px 32px;
    border: 1px solid var(--border);
    border-radius: 12px;
    background: var(--bg-base);
    box-shadow: 0 24px 64px rgba(0, 0, 0, 0.32);
    text-align: center;
  }

  .splash-title {
    margin: 0 0 12px;
    color: var(--text);
  }

  .splash-body {
    margin: 0;
    color: var(--text-dim);
    line-height: 1.5;
  }
</style>
