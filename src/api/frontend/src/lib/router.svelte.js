/** Client-side view router using Svelte 5 runes. */

let currentView = $state('dashboard');
let currentTitle = $state('Dashboard');

export function getView() {
  return currentView;
}

export function getTitle() {
  return currentTitle;
}

export function navigate(view, title) {
  currentView = view;
  currentTitle = title;
}
