import { writable } from 'svelte/store';
import { browser } from '$app/environment';

const STORAGE_KEY = 'heimdall.theme';

function readInitial() {
  if (!browser) return 'dark';
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === 'dark' || stored === 'light') return stored;
    if (window.matchMedia('(prefers-color-scheme: light)').matches) return 'light';
  } catch (e) {
    // ignore
  }
  return 'dark';
}

export const theme = writable(readInitial());

export function setTheme(next) {
  if (next !== 'dark' && next !== 'light') return;
  theme.set(next);
  if (browser) {
    try {
      localStorage.setItem(STORAGE_KEY, next);
      document.documentElement.setAttribute('data-theme', next);
    } catch (e) {
      // ignore
    }
  }
}
