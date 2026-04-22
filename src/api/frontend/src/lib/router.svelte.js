/** Hash-based view router. Persists across refresh via location.hash. */

const VALID_VIEWS = new Set([
  'dashboard',
  'pipeline',
  'campaigns',
  'prospects',
  'briefs',
  'clients',
  'logs',
  'settings',
]);

const TITLES = {
  dashboard: 'Dashboard',
  pipeline: 'Pipeline',
  campaigns: 'Campaigns',
  prospects: 'Prospects',
  briefs: 'Briefs',
  clients: 'Clients',
  logs: 'Logs',
  settings: 'Settings',
};

function parseHash() {
  const raw = (typeof window !== 'undefined' ? window.location.hash : '') || '#/dashboard';
  const stripped = raw.startsWith('#') ? raw.slice(1) : raw;
  const body = stripped.startsWith('/') ? stripped.slice(1) : stripped;
  const [path, query = ''] = body.split('?', 2);
  const view = VALID_VIEWS.has(path) ? path : 'dashboard';
  const params = {};
  if (query) {
    for (const part of query.split('&')) {
      if (!part) continue;
      const eq = part.indexOf('=');
      const k = eq === -1 ? part : part.slice(0, eq);
      const v = eq === -1 ? '' : part.slice(eq + 1);
      if (k) params[decodeURIComponent(k)] = decodeURIComponent(v);
    }
  }
  return { view, title: TITLES[view] ?? 'Heimdall', params };
}

function toHash(view, params) {
  let h = `#/${view}`;
  const entries = Object.entries(params ?? {}).filter(
    ([, v]) => v !== undefined && v !== null && v !== '',
  );
  if (entries.length) {
    const qs = entries
      .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`)
      .join('&');
    h += `?${qs}`;
  }
  return h;
}

export const router = $state(parseHash());

export function navigate(view, titleOrParams, maybeParams) {
  let title;
  let params;
  if (typeof titleOrParams === 'string') {
    title = titleOrParams;
    params = maybeParams ?? {};
  } else {
    params = titleOrParams ?? {};
    title = TITLES[view] ?? view;
  }
  if (!VALID_VIEWS.has(view)) return;
  const nextHash = toHash(view, params);
  if (typeof window !== 'undefined' && window.location.hash !== nextHash) {
    window.location.hash = nextHash;
  }
  router.view = view;
  router.title = title;
  router.params = params;
}

if (typeof window !== 'undefined') {
  window.addEventListener('hashchange', () => {
    const parsed = parseHash();
    router.view = parsed.view;
    router.title = parsed.title;
    router.params = parsed.params;
  });
  if (!window.location.hash) {
    window.location.replace(`${window.location.pathname}${window.location.search}#/dashboard`);
  }
}
