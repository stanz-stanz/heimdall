/**
 * Login.svelte component tests.
 *
 * Stage A slice 3g.5 §4.1 (10 tests). Spec citation: slice 3g spec §2.3.
 * Pattern: @testing-library/svelte (Decision §7.2 Option A).
 *
 * Each test stubs the `login` import from `$lib/auth.svelte.js` so the
 * component renders against a mock — we're testing the form's UI and
 * wire to login(), not the state-machine itself (covered in auth.test.js).
 *
 * The countdown $effect is NOT tested here per Decision §7.4 (Option B —
 * `tickRateLimit()` unit-tested + browser QA covers the visible decrement).
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/svelte';

// Mock ws.svelte.js (auth.svelte.js depends on it).
vi.mock('$lib/ws.svelte.js', () => ({
  connect: vi.fn(),
  disconnect: vi.fn(),
}));

// Mock the login function — Login.svelte imports it from auth.svelte.js,
// so the mock factory must export every binding the component (and the
// auth module's other consumers) can reference.
vi.mock('$lib/auth.svelte.js', async () => {
  const { default: Svelte } = await import('svelte');
  // Hoisted reactive proxy — the component reads this directly via the
  // `auth` import. Using a plain object plus per-test resets is enough
  // for component-render assertions that don't depend on rune reactivity.
  const auth = {
    status: 'unauthenticated',
    operator: null,
    csrfToken: null,
    retryAfter: 0,
    error: null,
  };
  return {
    auth,
    login: vi.fn(async () => true),
    logout: vi.fn(),
    bootstrap: vi.fn(),
    getCsrfToken: vi.fn(() => null),
    tickRateLimit: vi.fn(() => false),
    handleSessionExpired: vi.fn(),
  };
});

import Login from '../src/views/Login.svelte';
import { auth, login } from '$lib/auth.svelte.js';


beforeEach(() => {
  vi.clearAllMocks();
  auth.status = 'unauthenticated';
  auth.operator = null;
  auth.csrfToken = null;
  auth.retryAfter = 0;
  auth.error = null;
  // login() defaults to returning true — individual tests override.
  login.mockImplementation(async () => true);
});

afterEach(() => {
  cleanup();
});


describe('Login.svelte', () => {
  it('test_login_renders_idle_form', () => {
    render(Login);
    expect(screen.getByLabelText(/username/i)).toBeTruthy();
    expect(screen.getByLabelText(/password/i)).toBeTruthy();
    const submit = screen.getByRole('button');
    expect(submit.textContent.trim()).toBe('Sign in');
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('test_login_disables_form_while_submitting', async () => {
    // login() never resolves — leaves the form in submitting state.
    let resolveLogin;
    login.mockImplementation(
      () => new Promise((resolve) => { resolveLogin = resolve; }),
    );
    render(Login);
    await fireEvent.input(screen.getByLabelText(/username/i), {
      target: { value: 'op' },
    });
    await fireEvent.input(screen.getByLabelText(/password/i), {
      target: { value: 'pw' },
    });
    await fireEvent.submit(screen.getByRole('button').closest('form'));
    const submit = screen.getByRole('button');
    expect(submit.textContent.trim()).toBe('Signing in…');
    expect(submit.disabled).toBe(true);
    expect(screen.getByLabelText(/username/i).disabled).toBe(true);
    expect(screen.getByLabelText(/password/i).disabled).toBe(true);
    // Release the promise so the test runner can clean up cleanly.
    resolveLogin?.(true);
  });

  it('test_login_renders_invalid_credentials_error', () => {
    auth.error = 'invalid_credentials';
    render(Login);
    const alert = screen.getByRole('alert');
    expect(alert.textContent).toContain('Invalid username or password.');
  });

  it('test_login_renders_service_unavailable_error', () => {
    auth.error = 'service_unavailable';
    render(Login);
    const alert = screen.getByRole('alert');
    expect(alert.textContent).toContain('Server unavailable. Please try again.');
  });

  it('test_login_renders_network_error', () => {
    auth.error = 'network';
    render(Login);
    const alert = screen.getByRole('alert');
    expect(alert.textContent).toContain('Network error. Check your connection and retry.');
  });

  it('test_login_renders_generic_error_for_unknown_code', () => {
    auth.error = 'http_500';
    render(Login);
    const alert = screen.getByRole('alert');
    expect(alert.textContent).toContain('Login failed. Please try again.');
  });

  it('test_login_renders_rate_limited_countdown', () => {
    auth.status = 'rate-limited';
    auth.error = 'rate_limited';
    auth.retryAfter = 42;
    render(Login);
    const submit = screen.getByRole('button');
    expect(submit.textContent.trim()).toBe('Wait 42s');
    expect(submit.disabled).toBe(true);
    const alert = screen.getByRole('alert');
    expect(alert.textContent).toContain('Too many failed attempts. Try again in 42s.');
  });

  it('test_login_calls_login_on_submit', async () => {
    render(Login);
    await fireEvent.input(screen.getByLabelText(/username/i), {
      target: { value: 'opname' },
    });
    await fireEvent.input(screen.getByLabelText(/password/i), {
      target: { value: 'secretpw' },
    });
    await fireEvent.submit(screen.getByRole('button').closest('form'));
    expect(login).toHaveBeenCalledTimes(1);
    expect(login).toHaveBeenCalledWith('opname', 'secretpw');
  });

  it('test_login_clears_password_on_success', async () => {
    login.mockImplementation(async () => true);
    render(Login);
    const usernameInput = screen.getByLabelText(/username/i);
    const passwordInput = screen.getByLabelText(/password/i);
    await fireEvent.input(usernameInput, { target: { value: 'op' } });
    await fireEvent.input(passwordInput, { target: { value: 'pw' } });
    await fireEvent.submit(screen.getByRole('button').closest('form'));
    // Wait one microtask for the post-submit clear to settle.
    await Promise.resolve();
    expect(passwordInput.value).toBe('');
  });

  it('test_login_blocks_submit_with_empty_fields', async () => {
    render(Login);
    await fireEvent.submit(screen.getByRole('button').closest('form'));
    expect(login).not.toHaveBeenCalled();
    expect(auth.error).toBe('invalid_credentials');
  });
});
