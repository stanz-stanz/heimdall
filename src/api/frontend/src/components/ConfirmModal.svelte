<!--
  Lightweight confirmation modal used by V6 retention-queue actions.

  Props:
    open          (bool, $bindable) — render the modal when true.
    title         (string) — modal heading.
    body          (string) — modal body text.
    confirmLabel  (string) — confirm button label. Default 'Confirm'.
    confirmStyle  ('default' | 'destructive') — confirm button colour.
                  'destructive' uses --red, default uses --gold.
    onConfirm     (() => void | Promise<void>) — called when confirmed.
    onCancel      (() => void) — called when dismissed (also fires on
                  esc / outside click). Default closes the modal.

  Behaviour:
    - Click on backdrop OR Escape key dismisses.
    - Confirm button is autofocused on open so keyboard "Enter" works.
    - Confirm button is disabled while onConfirm() is in-flight (catches
      double-clicks during the cron-tick latency window).
-->

<script>
  let {
    open = $bindable(false),
    title = '',
    body = '',
    confirmLabel = 'Confirm',
    confirmStyle = 'default',
    onConfirm = () => {},
    onCancel = null,
  } = $props();

  let busy = $state(false);
  let confirmBtn = $state(null);

  $effect(() => {
    if (open && confirmBtn) {
      // autofocus the confirm button — Enter triggers the action
      queueMicrotask(() => confirmBtn?.focus());
    }
    if (!open) busy = false;
  });

  function dismiss() {
    if (busy) return;
    open = false;
    if (onCancel) onCancel();
  }

  async function confirm() {
    if (busy) return;
    busy = true;
    try {
      await onConfirm();
      open = false;
    } finally {
      busy = false;
    }
  }

  function onKey(ev) {
    if (!open) return;
    if (ev.key === 'Escape') dismiss();
    if (ev.key === 'Enter' && document.activeElement?.tagName !== 'BUTTON') confirm();
  }
</script>

<svelte:window onkeydown={onKey} />

{#if open}
  <div
    class="modal-backdrop"
    role="presentation"
    onclick={dismiss}
    onkeydown={(ev) => { if (ev.key === 'Enter' || ev.key === ' ') dismiss(); }}
  >
    <div
      class="modal confirm-panel"
      role="dialog"
      tabindex="-1"
      aria-modal="true"
      aria-labelledby="confirm-title"
      onclick={(ev) => ev.stopPropagation()}
      onkeydown={(ev) => ev.stopPropagation()}
    >
      <h3 id="confirm-title" class="t-heading confirm-title">{title}</h3>
      <p class="t-body confirm-body">{body}</p>
      <div class="confirm-actions">
        <button class="btn btn-ghost btn-sm" onclick={dismiss} disabled={busy}>
          Cancel
        </button>
        <button
          bind:this={confirmBtn}
          class="btn btn-sm"
          class:btn-danger={confirmStyle === 'destructive'}
          class:btn-primary={confirmStyle !== 'destructive'}
          onclick={confirm}
          disabled={busy}
        >
          {busy ? 'Working…' : confirmLabel}
        </button>
      </div>
    </div>
  </div>
{/if}

<style>
  .modal-backdrop {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.55);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
    cursor: default;
  }
  .confirm-panel {
    min-width: 320px;
    max-width: min(90vw, 480px);
    padding: 20px 24px;
  }
  .confirm-title {
    margin: 0 0 8px 0;
  }
  .confirm-body {
    margin: 0 0 20px 0;
    color: var(--text-dim);
  }
  .confirm-actions {
    display: flex;
    gap: 8px;
    justify-content: flex-end;
  }
</style>
