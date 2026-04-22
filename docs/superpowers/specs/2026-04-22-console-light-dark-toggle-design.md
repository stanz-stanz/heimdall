# Console Light/Dark Mode Toggle — Design

**Date:** 2026-04-22
**Branch:** feat/console-overhaul-2026-04-22
**Owner:** Federico (decides); Claude (executes with ui-ux-pro-max for palette/contrast, frontend-design for implementation)
**Related design system doc:** `docs/design/design-system.md` (currently v1.2, dark-only)

---

## 1. Goal

Replace the console's dark-only visual system with a properly designed light-mode companion and a single-click toggle in the topbar. Every existing token name is preserved; only values swap per theme. Severity palette is re-tuned per theme so warm-only severity keeps AA contrast on light backgrounds.

## 2. Non-Goals

- No tri-state (System / Light / Dark) picker — a single topbar toggle binary-flips the resolved theme. OS preference seeds the first visit; after that, user choice wins.
- No per-view or per-user-role theme overrides.
- No visual identity change — the console remains the Heimdall console in both modes.
- No theme support on Telegram messages, PDFs, or any other surface outside the operator console.
- No refactor of unrelated console components.

## 3. Architecture

### 3.1 Source of truth

`data-theme` attribute on `<html>`, values `"dark"` or `"light"`. All theme-dependent CSS keys off this attribute.

### 3.2 Token structure

`src/api/frontend/src/styles/tokens.css` splits into two scoped blocks:

```css
:root[data-theme="dark"]  { /* current dark palette + re-tuned severity */ }
:root[data-theme="light"] { /* new light palette + re-tuned severity */ }
```

Every existing token name stays identical — components keep using `var(--bg-raised)`, `var(--red)`, etc. No component-level changes required for pure color lookups.

### 3.3 Theme store

New file `src/api/frontend/src/lib/theme.svelte.js`:

- Reactive state resolved to `'dark' | 'light'`.
- On init: read `localStorage['heimdall.theme']`. If absent, derive from `window.matchMedia('(prefers-color-scheme: light)')`.
- Listens to OS `prefers-color-scheme` changes **only while the user has not overridden** — once they click the toggle, their choice is persisted and subsequent OS changes are ignored.
- Writes on every change: `data-theme` attribute on `<html>`, `<meta name="color-scheme">` content, `localStorage['heimdall.theme']`.

### 3.4 No-FOUC bootstrap

Inline `<script>` in `src/api/frontend/index.html` runs **before** the Svelte bundle loads. It reads localStorage / matchMedia and sets `data-theme` on `<html>` synchronously. Users never see a flash of the wrong theme on hard reload.

### 3.5 Toggle component

New `src/api/frontend/src/components/ThemeToggle.svelte`:

- Icon button, placed in `Topbar.svelte` right cluster.
- Sun icon when `theme === 'dark'` (affordance reads "click to go light"); moon icon when `'light'`.
- `aria-label` toggles between `"Switch to light mode"` and `"Switch to dark mode"`.
- `aria-pressed` reflects state.
- 180ms `transition` on color properties, body-wide, guarded by `@media (prefers-reduced-motion: reduce)`.

## 4. Palette Strategy

Exact hex values are designed during implementation by `ui-ux-pro-max`, not frozen in this spec. The spec fixes structure and constraints; the expert picks numbers.

### 4.1 Tokens that get per-theme values

| Group | Dark role | Light role constraint |
|-------|-----------|-----------------------|
| Backgrounds (`--bg-deep` → `--bg-hover`) | 5-level dark depth scale | 5-level inverted scale: white / warm off-white / pale slate |
| Text (`--text`, `--text-dim`, `--text-muted`) | Light slate on dark | Dark slate on light; `--text` ≥ AA on `--bg-base` and `--bg-raised` |
| Borders (`--border`, `--border-subtle`) | Subtle dark blue-slate | Subtle warm-grey, visible on white without feeling heavy |
| Gold brand (`--gold`, `--gold-dim`, `--gold-glow`) | `#f59e0b` family | Darker amber variant (amber-600/700 range) so CTAs don't flare on white; lower-opacity glow |
| Severity — full intensity (`--red`, `--orange`) | `#ef4444`, `#f97316` | Darker, more saturated variants to pass contrast on light |
| Severity — tint variants (`--red-dim`, `--red-muted`, `--red-outline`, `--red-soft`, `--orange-dim`) | Translucent over dark | Re-tuned alpha and/or base color for equivalent presence on light |
| Non-severity semantic (`--green`, `--green-dim`, `--blue`, `--blue-dim`) | Current values | Re-tuned only if contrast fails; roles unchanged |
| Elevation (`--shadow`, `--shadow-overlay`) | Deep dark shadows | Softer conventional shadows — dark shadows vanish on light |
| Overlay backdrop (`--overlay-backdrop`) | `rgba(6, 13, 26, 0.72)` | Lighter semi-opaque value |
| Background effects (`global.css` `.gradient-mesh`) | Subtle dark radial glows | Re-tuned lighter stops, or disabled if visually noisy |

### 4.2 Constraints

- Every text-on-background pair passes **WCAG AA**: 4.5:1 for body text, 3:1 for large text (≥18pt or ≥14pt bold).
- Warm-only severity rule from design system v1.1 holds in both themes — severity badges must be unmistakably red/orange family.
- Gold is brand-exclusive in both themes — no severity or status use.
- `--green` and `--blue` retain their non-severity roles (operational health, informational UI).

## 5. Components Needing More Than a Token Swap

Pure color-lookup components work automatically. The following need audit and possibly per-theme CSS beyond token values:

- `Topbar.svelte` — add `ThemeToggle`; verify any blur/glass styling on light background.
- `Sidebar.svelte` — active-nav gold chip contrast on light.
- `Badge.svelte` — highest-risk: severity badges must feel correct in both modes.
- `StatCard.svelte`, `CampaignCard.svelte` — elevation affordance (shadows tuned for dark vanish on light).
- `DataTable.svelte` — alternating row backgrounds, hover states, sticky header.
- `ProgressBar.svelte` — gold fill on light track.
- `global.css` — `.gradient-mesh`, body background, scrollbar styles, focus rings.

## 6. Testing

### 6.1 Contrast verification

`scripts/verify_theme_contrast.mjs`:
- Parses `tokens.css`, extracts both theme blocks.
- Computes WCAG contrast ratios for every documented text-on-background pairing.
- Fails with non-zero exit if any pair regresses below AA thresholds.
- Committed and runnable in CI (added to frontend lint/test pipeline).

### 6.2 Visual regression

Playwright snapshot tests — every console view (Dashboard, Pipeline, Campaigns, Prospects, Briefs, Clients, Logs, Settings) captured in both themes. Baselines committed to repo.

### 6.3 Unit tests

`src/api/frontend/src/lib/theme.svelte.js`:
- Reads OS preference when localStorage empty.
- Persists override to localStorage on toggle.
- Once overridden, ignores subsequent OS `prefers-color-scheme` changes.
- Clearing localStorage re-enables OS preference tracking.

### 6.4 Manual smoke

- Toggle on every view; no layout shift, no illegible text.
- Hard reload in each mode; no FOUC.
- Reload with OS preference flipped; first visit honors OS, persisted visit honors override.
- `prefers-reduced-motion: reduce` — theme swap is instant, no 180ms transition.

## 7. Design System Doc — v1.3

`docs/design/design-system.md` rollup:

- Header: `Theme: Dark-only` → `Theme: Light + Dark`
- §1.1 Color Palette split into dark and light subsections, each with full hex tables.
- §1.5 Elevation — per-theme shadow token values.
- New §12: Theming — store, `data-theme` attribute, toggle UX, FOUC prevention, reduced-motion, localStorage key.
- Reviewer checklist (§11.7) gains: "new tokens defined in both themes; no hardcoded hex in components."

## 8. File Touch List

New:
- `src/api/frontend/src/lib/theme.svelte.js`
- `src/api/frontend/src/components/ThemeToggle.svelte`
- `scripts/verify_theme_contrast.mjs`
- Playwright snapshot baselines

Modified:
- `src/api/frontend/src/styles/tokens.css` — split into two theme blocks
- `src/api/frontend/src/styles/global.css` — theme-scoped effects where needed
- `src/api/frontend/index.html` — inline no-FOUC bootstrap
- `src/api/frontend/src/components/Topbar.svelte` — mount `ThemeToggle`
- Audit list from §5 — per-theme CSS as needed
- `docs/design/design-system.md` — v1.3 rewrite
- Frontend CI config — add contrast verification step

## 9. Out of Scope

- Printing / PDF rendering — print styles out of scope; if any are added later, they'll be designed then.
- Theme persistence across devices (server-side preference) — localStorage only.
- Theme for authenticated client surfaces (none exist today).

## 10. Open Questions

None at spec approval time — palette hex values are intentionally deferred to ui-ux-pro-max during implementation.
