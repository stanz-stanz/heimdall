import { describe, it, expect, beforeEach } from 'vitest';
import { get } from 'svelte/store';
import {
  t,
  locale,
  setLocale,
  initLocale,
  DEFAULT_LOCALE,
  SUPPORTED_LOCALES,
} from '$lib/i18n';

const STORAGE_KEY = 'heimdall_signup_locale';

// Vitest's jsdom env returns an empty {} for window.localStorage instead of a
// real Storage instance. Replace it with a working in-memory shim per test so
// setLocale/initLocale can call setItem/getItem/removeItem.
function installMemStorage() {
  let store = {};
  const shim = {
    getItem: (k) => (Object.prototype.hasOwnProperty.call(store, k) ? store[k] : null),
    setItem: (k, v) => { store[k] = String(v); },
    removeItem: (k) => { delete store[k]; },
    clear: () => { store = {}; },
    key: (i) => Object.keys(store)[i] ?? null,
    get length() { return Object.keys(store).length; },
  };
  Object.defineProperty(window, 'localStorage', {
    value: shim,
    writable: true,
    configurable: true,
  });
  return shim;
}

describe('i18n', () => {
  beforeEach(() => {
    installMemStorage();
    window.history.replaceState({}, '', '/');
    setLocale('en', { persist: false, syncUrl: false });
  });

  describe('t() reactive translator', () => {
    it('returns the EN string for a known key', () => {
      expect(get(t)('nav.brand')).toBe('Digital Vagt');
    });

    it('returns the DA string when locale is da', () => {
      setLocale('da', { persist: false, syncUrl: false });
      expect(get(t)('nav.pricing')).toBe('Priser');
    });

    it('returns the key itself when neither locale has it', () => {
      expect(get(t)('nonexistent.key')).toBe('nonexistent.key');
    });

    it('exposes SUPPORTED_LOCALES and includes en + da', () => {
      expect(SUPPORTED_LOCALES).toContain('en');
      expect(SUPPORTED_LOCALES).toContain('da');
    });
  });

  describe('setLocale', () => {
    it('updates the locale store', () => {
      setLocale('da', { syncUrl: false });
      expect(get(locale)).toBe('da');
      setLocale('en', { syncUrl: false });
      expect(get(locale)).toBe('en');
    });

    it('ignores unsupported locale codes', () => {
      setLocale('en', { syncUrl: false });
      setLocale('zz', { syncUrl: false });
      expect(get(locale)).toBe('en');
    });

    it('persists to localStorage by default', () => {
      setLocale('da', { syncUrl: false });
      expect(window.localStorage.getItem(STORAGE_KEY)).toBe('da');
    });

    it('skips localStorage when persist=false', () => {
      setLocale('da', { persist: false, syncUrl: false });
      expect(window.localStorage.getItem(STORAGE_KEY)).toBeNull();
    });

    it('writes ?lang=da to URL when syncing for non-default locale', () => {
      window.history.replaceState({}, '', '/pricing');
      setLocale('da');
      expect(new URL(window.location.href).searchParams.get('lang')).toBe('da');
    });

    it('removes ?lang from URL when switching back to default (en)', () => {
      window.history.replaceState({}, '', '/pricing?lang=da');
      setLocale('en');
      expect(new URL(window.location.href).searchParams.get('lang')).toBeNull();
    });

    it('preserves other URL params when syncing', () => {
      window.history.replaceState({}, '', '/signup/start?t=abc123');
      setLocale('da');
      const url = new URL(window.location.href);
      expect(url.searchParams.get('t')).toBe('abc123');
      expect(url.searchParams.get('lang')).toBe('da');
    });
  });

  describe('initLocale', () => {
    it('reads ?lang=da from URL, sets locale, and persists for next visit', () => {
      window.history.replaceState({}, '', '/pricing?lang=da');
      initLocale();
      expect(get(locale)).toBe('da');
      expect(window.localStorage.getItem(STORAGE_KEY)).toBe('da');
    });

    it('falls back to localStorage when no URL param', () => {
      window.localStorage.setItem(STORAGE_KEY, 'da');
      initLocale();
      expect(get(locale)).toBe('da');
    });

    it('defaults to EN when neither URL nor localStorage has a locale', () => {
      initLocale();
      expect(get(locale)).toBe(DEFAULT_LOCALE);
      expect(get(locale)).toBe('en');
    });

    it('does not strip ?lang from URL on init (link stays shareable)', () => {
      window.history.replaceState({}, '', '/pricing?lang=da');
      initLocale();
      expect(new URL(window.location.href).searchParams.get('lang')).toBe('da');
    });

    it('ignores unsupported URL locale codes and falls back', () => {
      window.history.replaceState({}, '', '/?lang=zz');
      initLocale();
      expect(get(locale)).toBe('en');
    });

    it('URL choice wins over localStorage', () => {
      window.localStorage.setItem(STORAGE_KEY, 'en');
      window.history.replaceState({}, '', '/?lang=da');
      initLocale();
      expect(get(locale)).toBe('da');
    });
  });
});
