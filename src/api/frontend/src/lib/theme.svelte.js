const STORAGE_KEY = 'heimdall.theme';

function readStored() {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    return v === 'dark' || v === 'light' ? v : null;
  } catch {
    return null;
  }
}

function osPreference() {
  if (typeof window === 'undefined' || !window.matchMedia) return 'dark';
  return window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
}

function apply(mode) {
  document.documentElement.setAttribute('data-theme', mode);
  let meta = document.querySelector('meta[name="color-scheme"]');
  if (!meta) {
    meta = document.createElement('meta');
    meta.name = 'color-scheme';
    document.head.appendChild(meta);
  }
  meta.content = mode;
}

function initialMode() {
  return readStored() ?? osPreference();
}

export const theme = $state({
  mode: initialMode(),
  overridden: readStored() !== null,
});

export function setTheme(mode) {
  if (mode !== 'dark' && mode !== 'light') return;
  theme.mode = mode;
  theme.overridden = true;
  try {
    localStorage.setItem(STORAGE_KEY, mode);
  } catch {}
  apply(mode);
}

export function toggleTheme() {
  setTheme(theme.mode === 'dark' ? 'light' : 'dark');
}

export function clearOverride() {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {}
  theme.overridden = false;
  theme.mode = osPreference();
  apply(theme.mode);
}

if (typeof window !== 'undefined') {
  apply(theme.mode);

  if (window.matchMedia) {
    const mq = window.matchMedia('(prefers-color-scheme: light)');
    const listener = (e) => {
      if (theme.overridden) return;
      const next = e.matches ? 'light' : 'dark';
      theme.mode = next;
      apply(next);
    };
    if (mq.addEventListener) mq.addEventListener('change', listener);
    else if (mq.addListener) mq.addListener(listener);
  }
}
