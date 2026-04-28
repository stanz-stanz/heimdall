<script>
  // Spec §7.4 Option C — distinct splash, copy only, no runbook link.
  // Operationally this state appears when console.db has zero
  // operators. The administrator runs the operator-zero seed step
  // (see runbook §2.2) to escape it.
</script>

<div class="splash-shell">
  <div class="splash-card">
    <h1 class="splash-title t-heading">No operators seeded</h1>
    <p class="splash-body t-help">
      This Heimdall console has no operators yet. Run the seed step
      from the deployment runbook, or contact your administrator to
      provision an account.
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
