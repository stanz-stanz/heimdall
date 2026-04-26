import { writable, derived, get } from 'svelte/store';
import en from '../messages/en.json';
import da from '../messages/da.json';

const dicts = { en, da };

export const SUPPORTED_LOCALES = ['en', 'da'];
export const DEFAULT_LOCALE = 'en';

const STORAGE_KEY = 'heimdall_signup_locale';
const URL_PARAM = 'lang';

export const locale = writable(DEFAULT_LOCALE);

function isSupported(code) {
  return typeof code === 'string' && Object.prototype.hasOwnProperty.call(dicts, code);
}

function lookup(key, active) {
  const dict = dicts[active] || {};
  if (Object.prototype.hasOwnProperty.call(dict, key)) {
    return dict[key];
  }
  if (Object.prototype.hasOwnProperty.call(dicts.en, key)) {
    return dicts.en[key];
  }
  return key;
}

export function setLocale(next, { persist = true, syncUrl = true } = {}) {
  if (!isSupported(next)) return;
  locale.set(next);
  if (typeof window === 'undefined') return;
  if (persist) {
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {}
  }
  if (syncUrl) {
    try {
      const url = new URL(window.location.href);
      if (next === DEFAULT_LOCALE) {
        url.searchParams.delete(URL_PARAM);
      } else {
        url.searchParams.set(URL_PARAM, next);
      }
      window.history.replaceState(window.history.state, '', url);
    } catch {}
  }
}

export function initLocale() {
  if (typeof window === 'undefined') return;

  let urlChoice = null;
  try {
    const url = new URL(window.location.href);
    const param = url.searchParams.get(URL_PARAM);
    if (isSupported(param)) urlChoice = param;
  } catch {}

  let stored = null;
  try {
    const value = window.localStorage.getItem(STORAGE_KEY);
    if (isSupported(value)) stored = value;
  } catch {}

  // URL wins; persists for next visit. Otherwise fall back to localStorage, then default.
  // Never sync URL on init — incoming URL is left intact so it stays shareable.
  if (urlChoice) {
    setLocale(urlChoice, { persist: true, syncUrl: false });
  } else if (stored) {
    setLocale(stored, { persist: false, syncUrl: false });
  } else {
    setLocale(DEFAULT_LOCALE, { persist: false, syncUrl: false });
  }
}

// Reactive translator. Components must use `$t('key')` so they re-render
// when the locale store changes. For non-reactive callers, `get(t)('key')`.
export const t = derived(locale, ($locale) => (key) => lookup(key, $locale));
