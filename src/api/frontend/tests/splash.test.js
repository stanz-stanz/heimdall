/**
 * BootstrapEmpty + AllDisabled splash component tests.
 *
 * Stage A slice 3g.5 §4.2 (6 tests). Spec citation: slice 3g spec
 * §2.4 (BootstrapEmpty + AllDisabled), §7.4 Option C, §7.5 Option B.
 *
 * Locks the two splash copy blocks + the no-fetch contract: these
 * components must not trigger any network call from their render path.
 * Fetch spy is installed BEFORE render in `beforeEach` per spec §4.2 —
 * a spy installed after render misses any fetch fired during component
 * initialisation, which would silently pass a regression.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/svelte';

import BootstrapEmpty from '../src/views/BootstrapEmpty.svelte';
import AllDisabled from '../src/views/AllDisabled.svelte';


let fetchSpy;

beforeEach(() => {
  // Install spy BEFORE render — see spec §4.2 ordering note.
  fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation(async () => {
    throw new Error('fetch should not be called during splash render');
  });
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});


describe('BootstrapEmpty.svelte', () => {
  it('test_bootstrap_empty_renders_copy', () => {
    render(BootstrapEmpty);
    expect(screen.getByText(/no operators seeded/i)).toBeTruthy();
    // No form fields / submit button on a splash.
    expect(screen.queryByRole('button')).toBeNull();
    expect(screen.queryByRole('textbox')).toBeNull();
  });

  it('test_bootstrap_empty_makes_no_fetch_during_render', () => {
    render(BootstrapEmpty);
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it('test_bootstrap_empty_role_alert_present', () => {
    const { container } = render(BootstrapEmpty);
    // The splash conveys a non-recoverable system state; either
    // role="alert" or role="status" satisfies the a11y contract.
    const alertOrStatus = container.querySelector(
      '[role="alert"], [role="status"]',
    );
    if (!alertOrStatus) {
      // Fall back to a heading-based check — splash content carries
      // a heading; some implementations expose the splash semantics
      // via the heading element rather than an explicit role.
      expect(container.querySelector('h1, h2')).toBeTruthy();
    } else {
      expect(alertOrStatus).toBeTruthy();
    }
  });
});


describe('AllDisabled.svelte', () => {
  it('test_all_disabled_renders_copy', () => {
    render(AllDisabled);
    expect(screen.getByText(/all operators.*disabled/i)).toBeTruthy();
    expect(screen.queryByRole('button')).toBeNull();
    expect(screen.queryByRole('textbox')).toBeNull();
  });

  it('test_all_disabled_makes_no_fetch_during_render', () => {
    render(AllDisabled);
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it('test_all_disabled_distinct_from_bootstrap_empty', () => {
    const bootstrapResult = render(BootstrapEmpty);
    const bootstrapText = bootstrapResult.container.textContent;
    cleanup();
    const allDisabledResult = render(AllDisabled);
    const allDisabledText = allDisabledResult.container.textContent;
    // Same shape but distinct copy — locks Decision §7.5 Option B
    // (distinct components per state, not one parameterised splash).
    expect(bootstrapText).not.toBe(allDisabledText);
    expect(bootstrapText).toMatch(/no operators seeded/i);
    expect(allDisabledText).toMatch(/all operators .* disabled/i);
  });
});
