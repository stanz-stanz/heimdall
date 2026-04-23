# Heimdall Design System

**Version:** 1.3 (rider)
**Last updated:** 2026-04-22

**v1.3 rider — what actually shipped (PR #42):**
- Operator console is now **dual-theme** (light + dark). Token names are identical across themes; values swap via `data-theme="dark"|"light"` on `<html>`.
- `tokens.css` split into two `:root[data-theme="…"]` blocks. Dark values below are authoritative; light values are defined in `src/api/frontend/src/styles/tokens.css` and tuned for WCAG AA by inspection (no automated contrast CI yet).
- Theme toggle lives in the Topbar (`ThemeToggle.svelte`). Seeds from `prefers-color-scheme`, persists in `localStorage['heimdall.theme']`, stops tracking the OS once the user overrides.
- Warm-only severity rule from v1.1 holds in both themes — light mode darkens the red/orange hues to keep contrast. Brand gold darkens to amber-700 range in light mode.

**v1.3 deferred — spec called for, not shipped:**
- A `scripts/verify_theme_contrast.mjs` AA-ratio CI guard (all text-on-bg pairs, both themes).
- Playwright visual-regression snapshots of every view in both themes.
- Unit tests for the theme store (OS-read, override persistence, clear-override semantics).
- A formal per-theme token-table rewrite of §1.1 (this rider documents both themes by reference to `tokens.css` rather than duplicating the table).

See `docs/superpowers/specs/2026-04-22-console-light-dark-toggle-design.md` for the original design; what actually shipped is annotated at the top of that spec.

**v1.2 changes:**
- New `.t-help` utility class for explanatory prose — bundles size, weight, colour, and the §11.4 max-width cap into one role (§1.2, §11.2, §11.4)
- §11.2 tightened — muted-on-text violations are a reviewer-checklist failure, with `.t-help` as the prescribed fix for help copy
- §11.7 reviewer checklist gains an explicit line for explanatory prose

**v1.1 changes:**
- Severity palette rebuilt warm-only — findings never wear blue or green (§1.1, §2.4, §6)
- Gold is brand-exclusive — no longer used for severity or status (§1.1, §8.2)
- Added elevation tokens for detached surfaces (§1.5)
- Type scale consolidated from 18 roles to 10 utility classes (§1.2)
- 9px campaign stat label raised to 11px (readability fix)
- New §11: Readability rules

**Scope:** Operator Console (`src/api/frontend/`)
**Stack:** Svelte 5 + vanilla CSS (no Tailwind, no preprocessors)
**Theme:** Light + Dark (toggle in Topbar, defaults to OS preference)

---

## 1. Design Tokens

All tokens are defined in `src/api/frontend/src/styles/tokens.css` as CSS custom properties on `:root`.

### 1.1 Color Palette

#### Backgrounds (depth hierarchy, darkest → lightest)

| Token | Hex | Usage |
|-------|-----|-------|
| `--bg-deep` | `#060d1a` | Full-page background |
| `--bg-base` | `#0b1120` | Sidebar background |
| `--bg-raised` | `#111b2e` | Cards, panels |
| `--bg-surface` | `#162037` | Table headers, input backgrounds |
| `--bg-hover` | `#1c2a45` | Interactive hover states |

Visual depth is created through background layering, not shadows. The 5-level scale provides clear visual hierarchy without elevation complexity.

#### Text

| Token | Hex | Usage |
|-------|-----|-------|
| `--text` | `#e2e8f0` | Primary body text |
| `--text-dim` | `#7a8ba8` | Secondary text, labels |
| `--text-muted` | `#4a5b78` | Decorative / non-essential only — fails AA contrast. See §11.2 |

#### Semantic Colors

Each semantic color has a full-intensity value and a dim/tinted background variant.

| Token | Hex | Meaning |
|-------|-----|---------|
| `--gold` | `#f59e0b` | **Brand only** — CTAs, active nav, focus, progress. Never severity or status. |
| `--gold-dim` | `#b47008` | Darker gold (pressed states) |
| `--gold-glow` | `rgba(245, 158, 11, 0.12)` | Gold background tint |
| `--red` | `#ef4444` | Critical severity, errors, destructive actions |
| `--red-dim` | `rgba(239, 68, 68, 0.15)` | Critical badge background |
| `--red-muted` | `rgba(239, 68, 68, 0.07)` | **v1.1** · Medium/low badge background |
| `--red-outline` | `rgba(239, 68, 68, 0.38)` | **v1.1** · Medium/low badge border |
| `--red-soft` | `#f87171` | **v1.1** · Medium badge text |
| `--orange` | `#f97316` | High severity, warnings |
| `--orange-dim` | `rgba(249, 115, 22, 0.15)` | Orange background tint |
| `--green` | `#22c55e` | Operational health, online status, operator action succeeded. **Never a vulnerability severity.** |
| `--green-dim` | `rgba(34, 197, 94, 0.15)` | Green background tint |
| `--blue` | `#3b82f6` | Informational UI, un-triaged metadata, Logs timeframe. **Never a vulnerability severity.** |
| `--blue-dim` | `rgba(59, 130, 246, 0.12)` | Blue background tint |

#### Borders

| Token | Hex | Usage |
|-------|-----|-------|
| `--border` | `#1e2d4a` | Standard borders, dividers |
| `--border-subtle` | `#152238` | Card borders, subtle dividers |

#### Background Effects (global.css)

The page background has subtle radial gradient overlays to add depth:
- Blue tint: `rgba(59, 130, 246, 0.04)`
- Gold tint: `rgba(245, 158, 11, 0.03)`

### 1.2 Typography

#### Font Families

| Token | Value | Usage |
|-------|-------|-------|
| `--sans` | `'DM Sans', sans-serif` | All UI text (headings, labels, body) |
| `--mono` | `'JetBrains Mono', monospace` | Code, numbers, domain names, data values |

Both fonts are loaded via Google Fonts.

#### Type Scale (v1.1)

10 utility classes replace all raw `font-size` / `font-weight` declarations. Defined in `global.css`.

| Class | Size | Weight | Font | Transform | Usage |
|-------|------|--------|------|-----------|-------|
| `.t-display` | 28 | 600 | Mono | — | Dashboard stat values |
| `.t-title` | 22 | 700 | Sans | — | Brand title only |
| `.t-heading` | 18 | 600 | Sans | — | Page titles, card titles |
| `.t-subheading` | 16 | 600 | Sans | — | Campaign names, modal titles |
| `.t-section` | 14 | 600 | Sans | upper · 0.06em | All section headers |
| `.t-body` | 13 | 400 | Sans | — | Default body, table rows |
| `.t-body-strong` | 13 | 500 | Sans | — | Buttons, emphasized body |
| `.t-label` | 12 | 500 | Sans | — | Form labels, chips, card meta |
| `.t-caption` | 11 | 600 | Sans | upper · 0.06em | Badges, table heads, nav labels |
| `.t-mono-label` | 12 | 500 | Mono | — | Log rows, inline data, timestamps |
| `.t-mono-stat` | 18 | 700 | Mono | — | Campaign stat values |
| `.t-help` | 13 | 400 | Sans | — | **Explanatory prose** — card subtitles, form descriptions, empty states, hints. Bundles `color: var(--text-dim)` + `max-width: 60ch`. See §11.2, §11.4. |

**Rules:** No font-size below 11px. One tracking value (`0.06em`) for all uppercase captions. See §11 for enforcement.

#### Line Heights

| Context | Value |
|---------|-------|
| Card values | 1.1 |
| Feed items | 1.4 |
| Log rows | 1.6 |
| Default | 1.5 |

### 1.3 Spacing

The system uses a base-4 spacing scale. Common values:

| Value | Usage |
|-------|-------|
| 4px | Tight inner gaps (icon-to-text) |
| 6px | Component flex gaps |
| 8px | Filter bar gaps, small padding |
| 10px | Table cell padding (vertical), feed gaps |
| 12px | Filter chip padding (horizontal), log padding |
| 14px | Table cell padding (horizontal) |
| 16px | Grid gap (universal), form group gap, button horizontal padding |
| 20px | Card padding, sidebar horizontal padding, nav section gap |
| 24px | Sidebar top padding, form section margin |
| 28px | Main content area padding, topbar horizontal padding |

### 1.4 Border Radius

| Token | Value | Usage |
|-------|-------|-------|
| `--radius` | 10px | Cards, panels, modals |
| `--radius-sm` | 6px | Buttons, inputs |
| `--radius-xs` | 4px | Checkboxes, small elements |
| 20px | Filter chips (pill shape) |

### 1.5 Shadows & Elevation (v1.1)

Hierarchy is conveyed through the background ramp. Shadow is reserved exclusively for **detached surfaces** — modals, dropdowns, popovers, toasts.

| Token | Value | Usage |
|-------|-------|-------|
| `--bg-overlay` | `#1e2c48` | Detached-surface background |
| `--shadow-overlay` | 3-layer drop + 1px gold rim | Detached-surface shadow |
| `--overlay-backdrop` | `rgba(6, 13, 26, 0.72)` | Modal scrim |
| `--shadow` | `0 4px 24px rgba(0, 0, 0, 0.4)` | Legacy · prefer `--shadow-overlay` |

**Utility classes:** `.overlay`, `.scrim`, `.modal`, `.dropdown`, `.toast` (in `global.css`).

### 1.6 Transitions

| Token | Value | Usage |
|-------|-------|-------|
| `--transition` | `180ms ease` | All interactive state changes (hover, focus, active) |

Special cases:
- Progress bar fill: `0.4s ease`
- Feed item entrance: `0.3s ease`

---

## 2. Components

All global component classes are defined in `src/api/frontend/src/styles/global.css`. Component-specific styles live in `<style>` blocks within `.svelte` files.

### 2.1 Buttons

| Class | Appearance | Usage |
|-------|------------|-------|
| `.btn` | Surface background, border | Default/secondary action |
| `.btn-primary` | Gold background, dark text | Primary CTA |
| `.btn-ghost` | Transparent, no border | Tertiary/inline actions |
| `.btn-sm` | Smaller (4px 10px, 12px font) | Compact contexts |
| `.btn-danger` | Red text, red hover bg | Destructive actions |

**States:** Hover brightens border/background. Disabled uses 0.4–0.5 opacity.

**Standard padding:** 8px 16px (default), 4px 10px (small).

### 2.2 Cards

| Class | Usage |
|-------|-------|
| `.card` | Standard container — raised bg, subtle border |
| `.card-header` | Flex row (space-between), 8px bottom margin |
| `.stat-gold`, `.stat-green`, `.stat-red`, `.stat-blue` | Stat card color variants |

**Structure:** `.card-header` → `.card-label` (12px, dim text) → `.card-value` (28px, mono, colored) → `.card-sub` (secondary info) → `.card-icon` (top-right positioned).

Built as `StatCard.svelte` component with `label`, `value`, `sub`, `icon`, `color` props.

### 2.3 Section Headers

```
.section-header         → flex row, space-between, bottom margin
  .section-title        → 14px/600, primary text, uppercase
```

Used in nearly every view to introduce content sections (e.g. "Active Campaigns", "Queue Status").

### 2.4 Badges (v1.1)

Severity is warm-only. **Findings never wear blue or green** — see §6.

| Class | Treatment | Meaning |
|-------|-----------|---------|
| `.badge-critical` | `--red` on `--red-dim` | Critical severity |
| `.badge-high` | `--orange` on `--orange-dim` | High severity |
| `.badge-medium` | `--red-soft` on `--red-muted`, red outline | Medium severity |
| `.badge-low` | `--text-dim` on `--red-muted`, red outline | Low severity |
| `.badge-new` | `--blue` on `--blue-dim` | Status: un-triaged |
| `.badge-interpreted` | Neutral outline | Status: processed |
| `.badge-sent` | `--green` on `--green-dim` | Status: dispatch succeeded |
| `.badge-bucket` | `--text-dim` on `--bg-surface` | Non-semantic |

**Usage:** `<span class="badge badge-critical">Critical</span>`. Sizing: `.t-caption` (11px, 600, 0.06em uppercase).

### 2.5 Tables

```
.table-wrap         → overflow container
  table             → full-width, border-collapse
    thead           → surface background
      th            → 11px uppercase, muted text, 0.06em tracking
    tbody
      td            → 13px, dim text
      td.domain     → bright text, monospace
```

**Cell padding:** 10px 14px. Rows highlight on hover.

### 2.6 Filter Chips

| Class | State | Appearance |
|-------|-------|------------|
| `.filter-chip` | Default | Rounded (20px radius), border, 12px text |
| `.filter-chip.active` | Active | Gold background glow, gold border |

**Padding:** 6px 12px. Arranged in flex row with 8px gap.

**Override:** In the Logs view, timeframe filter chips use blue (`--blue-dim` / `--blue`) instead of gold for the active state, visually distinguishing time filters from category filters.

### 2.7 Progress Bar

```
.progress-strip         → card-like container
  .progress-bar-track   → surface bg, 6px height
    .progress-bar-fill  → gold fill, width transition 0.4s
  .progress-label       → gold, monospace, 13px
  .progress-msg         → dim text
```

### 2.8 Feed / Activity

```
.feed
  .feed-item            → flex row, slide-in-up animation
    .feed-dot           → 8x8px colored circle
    .feed-text          → primary text
    .feed-time          → monospace timestamp
```

### 2.9 Campaign Cards

```
.campaign-card          → card variant for campaign summaries
  .campaign-name        → 16px/600 campaign title
  .campaign-stats       → 4-column grid, 8px gap
    .campaign-stat      → stacked stat block
      value             → 18px/700 mono
      label             → 9px/600 uppercase, 0.06em tracking
  .campaign-bar         → stacked color-segmented progress bar
    segments            → inline-width percentages (new=blue, interpreted=gold, sent=green)
  action buttons        → row of .btn-sm at bottom
```

Built as `CampaignCard.svelte` with campaign data props.

### 2.10 Form Controls (Settings)

| Control | Specification |
|---------|---------------|
| Text input | Surface bg, 8px 12px padding, gold border on focus, max-width 400px |
| Checkbox | 20x20px custom, gold bg when checked, `--radius-xs` corners |
| Toggle | 44x24px, 12px border-radius, gold when active, animated thumb |
| Range slider | 4px track, 16x16px gold thumb |
| Select | Same styling as text inputs |

### 2.11 Empty States

```
.empty-state            → centered container
  .empty-state-icon     → large muted icon
  .empty-state-text     → dim descriptive text
```

### 2.12 Config Editor (tabs)

```
.config-editor          → card container
  .config-tabs          → horizontal tab bar
    .config-tab         → tab item
    .config-tab.active  → gold underline (2px)
  .config-body          → 20px padding content area
```

---

## 3. Layout

### 3.1 App Shell

```
┌──────────────────────────────────────┐
│ body (flex row, full viewport)       │
├────────────┬─────────────────────────┤
│ Sidebar    │ Main (flex column)      │
│ 220px      │ ┌─────────────────────┐ │
│ fixed      │ │ Topbar              │ │
│            │ │ 16px vert, 28px hz  │ │
│            │ ├─────────────────────┤ │
│            │ │ Content (flex: 1)   │ │
│            │ │ overflow-y: auto    │ │
│            │ │ padding: 28px       │ │
│            │ └─────────────────────┘ │
└────────────┴─────────────────────────┘
```

### 3.2 Grid System

| Class | Columns | Usage |
|-------|---------|-------|
| `.grid` | — | Base: `display: grid; gap: 16px` |
| `.grid-4` | 4 | Dashboard stat cards |
| `.grid-3` | 3 | Queue status cards |
| `.grid-2` | 2 | Campaign cards, prospect grids |

All grids use 16px gap consistently.

### 3.3 Sidebar Navigation

- **Width:** 220px fixed
- **Brand:** 22px/700 title + 11px/500 subtitle (0.08em tracking)
- **Section labels:** 10px/600 uppercase, 0.1em letter-spacing
- **Nav items:** Icon + label, flex row, 10px gap
- **Nav badges:** Mono 11px/600, surface bg, 1px 6px padding (item counts)
- **Active state:** 3px gold left border + gold background glow
- **Status dot:** 8px circle, pulsing green when online (`pulse-dot` animation)

### 3.4 Topbar

- **Padding:** 16px vertical, 28px horizontal
- **Background:** `var(--bg-base)` (same depth as sidebar)
- **Layout:** flex space-between (page title | clock)
- **Border:** bottom border using `--border-subtle`

### 3.5 Scrollbars

Custom webkit scrollbars in `.content`:
- Width: 6px
- Thumb: `--border` color, brightens to `--text-muted` on hover

---

## 4. Animation

### 4.1 Keyframes

```css
@keyframes slide-in-up {
  from { opacity: 0; transform: translateY(12px); }
  to   { opacity: 1; transform: translateY(0); }
}

@keyframes pulse-dot {
  0%, 100% { opacity: 1; }
  50%      { opacity: 0.5; }
}
```

| Animation | Duration | Easing | Usage |
|-----------|----------|--------|-------|
| `slide-in-up` | 0.3s | ease | Feed items entering |
| `pulse-dot` | 2s infinite | ease-in-out | Online status indicator |

### 4.2 Counter Animation (Dashboard)

Stat card values animate from 0 to their target value on mount using a JS-driven counter with cubic easing (`1 - Math.pow(1 - progress, 3)`) over 600ms. Implemented in `Dashboard.svelte`.

### 4.3 Transition Standard

All interactive elements use `var(--transition)` (180ms ease) for:
- Background color changes
- Border color changes
- Opacity changes

**Exception:** Progress bar fill uses 400ms ease for smoother visual feedback.

### 4.4 Reduced Motion

The system respects `@media (prefers-reduced-motion: reduce)` — animations are reduced or disabled.

---

## 5. Icons

**System:** Unicode characters (no icon library).

| View | Character | Name |
|------|-----------|------|
| Dashboard | `■` (U+25A0) | Square |
| Pipeline | `▶` (U+25B6) | Play |
| Campaigns | `★` (U+2605) | Star |
| Prospects | `●` (U+25CF) | Circle |
| Clients | `♢` (U+2662) | Diamond |
| Logs | `≡` (U+2261) | Bars |
| Settings | `⚙` (U+2699) | Gear |
| Demo | `⚡` (U+26A1) | Lightning |

Stat card icons are passed as props (also Unicode).

**Note:** This is a pragmatic choice for an internal operator tool. If the console becomes client-facing, consider migrating to Lucide or Heroicons (SVG).

---

## 6. Severity Mapping (v1.1)

**Axiom:** A security finding is never good news. The severity ramp stays in the red family end-to-end. **Blue and green never represent a vulnerability.**

| Severity | Tokens | Badge Class | Telegram Label |
|----------|--------|-------------|----------------|
| Critical | `--red` on `--red-dim` | `.badge-critical` | `🔴 Critical:` |
| High | `--orange` on `--orange-dim` | `.badge-high` | `🟠 High:` |
| Medium | `--red-soft` on `--red-muted`, red outline | `.badge-medium` | `🔴 Medium:` |
| Low | `--text-dim` on `--red-muted`, red outline | `.badge-low` | `🔴 Low:` |

Status badges (`new` / `interpreted` / `sent`) are a **separate axis** from severity — pipeline state, not urgency. Green on `.badge-sent` means *the dispatch action succeeded*, not *the finding is good*.

---

## 7. CSS Architecture

### File Structure

```
src/api/frontend/src/styles/
├── tokens.css    ← Design tokens (CSS variables only)
└── global.css    ← Global classes (~615 lines)

src/api/frontend/src/lib/
├── Badge.svelte          ← Severity/status badge
├── CampaignCard.svelte   ← Campaign summary card with stats + progress
├── DataTable.svelte      ← Generic table (columns, rows, renderCell props)
├── FeedItem.svelte       ← Activity feed entry
├── FilterChips.svelte    ← Filter chip bar (options, active, onSelect props)
├── ProgressBar.svelte    ← Progress strip with label
└── StatCard.svelte       ← Stat card (label, value, sub, icon, color props)
```

### Conventions

1. **Tokens first:** All colors, radii, fonts, shadows, and transitions are CSS variables. Never use raw hex values in components.
2. **Global classes for reuse:** `.card`, `.btn`, `.badge`, `.grid-*`, `.filter-chip`, `.table-wrap` etc. are in `global.css`.
3. **Scoped styles for specifics:** Component-level layout and structure live in Svelte `<style>` blocks.
4. **No preprocessors:** Vanilla CSS only. No SCSS, LESS, or PostCSS transforms.
5. **No utility framework:** No Tailwind. Semantic class names throughout.
6. **BEM-lite naming:** Flat class names with hyphenated modifiers (`.btn-primary`, `.badge-critical`, `.stat-gold`).

---

## 8. Design Principles

1. **Depth through color for hierarchy, shadow for detachment.** The 5-level `deep → base → raised → surface → hover` ramp conveys position in the document. The `--bg-overlay` + `--shadow-overlay` pair conveys *detachment from the document* — reserved exclusively for modals, menus, popovers, and toasts.

2. **Gold is brand-exclusive.** Gold (`#f59e0b`) is used for CTAs, active navigation, focus rings, and progress indicators — *never* for severity or status. Seeing gold means "attention / action," full stop.

3. **Monospace for data.** Domain names, statistics, timestamps, and any numerical/code content use JetBrains Mono. This visually separates "data" from "UI chrome."

4. **Findings never wear positive or neutral colors.** The severity ramp lives inside the red family end-to-end. Blue and green have legitimate meanings elsewhere (informational UI, operational health, operator action succeeded) but can never represent a vulnerability.

5. **Operator-first.** This is an internal tool — optimize for information density and keyboard efficiency over visual polish. No decorative elements.

6. **Dark-only.** The security/ops context and always-on monitoring use case make dark theme the only mode. No light variant is planned.

---

## 9. Accessibility Notes

This is an internal single-operator tool, but these standards are maintained:

- **Contrast:** Primary text (`#e2e8f0`) on raised background (`#111b2e`) achieves ~9.5:1 ratio (exceeds WCAG AAA).
- **Focus states:** Interactive elements use gold border on focus.
- **Reduced motion:** `prefers-reduced-motion` media query is respected.
- **Keyboard navigation:** Tab order follows visual order. All interactive elements are keyboard-accessible.
- **Color + text:** Severity is conveyed through both color and text labels (not color alone).

---

## 10. Readability Rules

Readability is a first-class constraint, not a nice-to-have. Every rule below is enforceable in PR review.

### 11.1 Minimum sizes

- **No font-size below 11px, ever.** 9px stat labels (previously on `CampaignCard`) are forbidden.
- **Mono at 12px is the floor** for inline data, log rows, timestamps.

### 11.2 Contrast

All text must meet WCAG ratios against its actual background:

| Role | Minimum ratio | Standard |
|------|---------------|----------|
| Body text | 4.5:1 | AA |
| Large text (≥18px or ≥14px bold) | 3:1 | AA Large |
| Caption / label text | 4.5:1 | AA |
| Decorative / non-essential only | 3:1 | — |

**Known-good pairings:**

| Text color | On background | Ratio |
|------------|---------------|-------|
| `--text` (`#e2e8f0`) | `--bg-raised` (`#111b2e`) | ~9.5:1 ✓ AAA |
| `--text-dim` (`#7a8ba8`) | `--bg-raised` | ~6.8:1 ✓ AA |
| `--text-muted` (`#4a5b78`) | `--bg-raised` | ~3.2:1 ✗ fails AA |

**Rule:** `--text-muted` is reserved for **non-essential decoration only** — elements that could disappear without loss of meaning (e.g. subtle separators, `--` placeholders, decorative borders). Never use it for information an operator must read.

**Fix pattern for help copy:** explanatory prose (card subtitles, form descriptions, empty states, tooltips, hints) must use `.t-help` — which bundles `var(--text-dim)` at 13/400 with the §11.4 max-width cap. If you find `--text-muted` on text an operator reads, that is a §11.2 violation and the fix is to apply `.t-help` (prose) or swap the colour to `var(--text-dim)` (short categorical labels).

### 11.3 Uppercase + tracking

Uppercase at small sizes with letter-spacing destroys word shapes, letter shapes, and pair recognition simultaneously. It is acceptable *only* when all three of these hold:

1. The string is ≤ 2 words
2. The size is ≥ 11px
3. It's a categorical label, not reading material

Any uppercase-cap text longer than 2 words is a readability bug — use sentence case instead.

### 11.4 Line length

Explanatory prose (empty states, help text, modal bodies, tooltips) must cap at **`max-width: 60ch`**. Dense tabular / data layouts are exempt — those are scanned, not read.

`.t-help` applies this cap automatically alongside the correct size and colour. Prefer applying the class to adding a one-off `max-width: 60ch`.

### 11.5 Gold on gold-glow

Gold text (`--gold`) on `--gold-glow` backgrounds is a borderline contrast pair (~3.9:1 on `--bg-raised`). It's acceptable on **small surfaces only** — active filter chips, active nav items. Never use this combo for body-sized text.

### 11.6 Findings never disappear

Per §6, vulnerability findings never wear blue or green. This is a readability rule too — an operator's eye should not slide past a finding because its color reads as "fine."

### 11.7 Reviewer checklist

A PR introducing text styling must be rejected if any of these are true:

- [ ] Raw `font-size:` outside the type scale (§1.2)
- [ ] Any size below 11px
- [ ] `--text-muted` on information the operator must read
- [ ] Explanatory prose that does not use `.t-help` (covers §11.2 and §11.4 together)
- [ ] Uppercase + tracking on strings > 2 words
- [ ] Explanatory paragraph without a `max-width` cap
- [ ] Gold text on gold-glow at body size
- [ ] Blue or green on a vulnerability finding

---

## 12. File Reference

| File | Role |
|------|------|
| `src/api/frontend/src/styles/tokens.css` | Source of truth for all design tokens |
| `src/api/frontend/src/styles/global.css` | Global component classes and utilities |
| `src/api/frontend/src/App.svelte` | App shell layout (sidebar + main) |
| `src/api/frontend/src/lib/StatCard.svelte` | Reusable stat card component |
| `src/api/frontend/src/views/*.svelte` | View-specific styles (scoped) |
