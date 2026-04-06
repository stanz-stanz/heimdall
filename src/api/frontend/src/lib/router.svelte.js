/** Client-side view router using Svelte 5 runes. */

export const router = $state({ view: 'dashboard', title: 'Dashboard' });

export function navigate(view, title) {
  router.view = view;
  router.title = title;
}
