# Heimdall Design System

**Version:** 1.0
**Last updated:** 2026-04-07
**Scope:** Operator Console (`src/api/frontend/`)
**Stack:** Svelte 5 + vanilla CSS (no Tailwind, no preprocessors)
**Theme:** Dark-only

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
| `--text-muted` | `#4a5b78` | Hints, placeholders, timestamps |

#### Semantic Colors

Each semantic color has a full-intensity value and a dim/tinted background variant.

| Token | Hex | Meaning |
|-------|-----|---------|
| `--gold` | `#f59e0b` | Primary accent, CTAs, active states |
| `--gold-dim` | `#b47008` | Darker gold (pressed states) |
| `--gold-glow` | `rgba(245, 158, 11, 0.12)` | Gold background tint |
| `--red` | `#ef4444` | Critical severity, errors, destructive actions |
| `--red-dim` | `rgba(239, 68, 68, 0.15)` | Red background tint |
| `--orange` | `#f97316` | High severity, warnings |
| `--orange-dim` | `rgba(249, 115, 22, 0.15)` | Orange background tint |
| `--green` | `#22c55e` | Success, active/online status |
| `--green-dim` | `rgba(34, 197, 94, 0.15)` | Green background tint |
| `--blue` | `#3b82f6` | Informational, secondary actions |
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

#### Type Scale

| Role | Size | Weight | Font | Letter Spacing |
|------|------|--------|------|----------------|
| Brand title | 22px | 700 | Sans | — |
| Brand subtitle | 11px | 500 | Sans | 0.08em |
| Page title | 18px | 600 | Sans | — |
| Campaign name | 16px | 600 | Sans | — |
| Section header | 14px | 600 | Sans | — |
| Card value (stat) | 28px | 600 | Mono | — |
| Campaign stat value | 18px | 700 | Mono | — |
| Card label | 12px | 500 | Sans | — |
| Body text | 13px | 400 | Sans | — |
| Button text | 13px | 500 | Sans | — |
| Log row | 12px | 400 | Mono | — |
| Table header | 11px | 600 | Sans | 0.06em |
| Table body | 13px | 400 | Sans | — |
| Badge | 11px | 600 | Sans | 0.04em |
| Nav badge | 11px | 600 | Mono | — |
| Nav section label | 10px | 600 | Sans | 0.1em |
| Filter chip | 12px | 500 | Sans | — |
| Campaign stat label | 9px | 600 | Sans | 0.06em |

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

### 1.5 Shadows & Elevation

| Token | Value | Usage |
|-------|-------|-------|
| `--shadow` | `0 4px 24px rgba(0, 0, 0, 0.4)` | Rare; depth is primarily conveyed via background color layering |

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

### 2.4 Badges

| Class | Color | Usage |
|-------|-------|-------|
| `.badge` | Base style | Container with 2px 8px padding |
| `.badge-critical` | Red | Critical severity |
| `.badge-high` | Orange | High severity |
| `.badge-medium` | Gold | Medium severity |
| `.badge-new` | Blue | New status |
| `.badge-interpreted` | Gold | Interpreted status |
| `.badge-sent` | Green | Sent status |
| `.badge-bucket` | Surface + border | Non-semantic (bucket labels) |
| `.client-plan` | Varies | Watchman (trial), Sentinel |

**Usage:** `<span class="badge badge-critical">Critical</span>` (hyphenated modifier, not dot-chained).

**Sizing:** 11px font, 600 weight, 0.04em letter-spacing.

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

## 6. Severity Mapping

Consistent color-to-severity mapping used across badges, Telegram messages, and the interpreter.

| Severity | Color Token | Badge Class | Telegram Label |
|----------|-------------|-------------|----------------|
| Critical | `--red` | `.badge-critical` | `🔴 Critical:` |
| High | `--orange` | `.badge-high` | `🟠 High:` |
| Medium | `--gold` | `.badge-medium` | — |
| Low | `--blue` | — | — |

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

1. **Depth through color, not shadow.** The 5-level background scale (`deep` → `base` → `raised` → `surface` → `hover`) creates visual hierarchy without relying on drop shadows.

2. **Gold as accent.** Gold (`#f59e0b`) is the single primary accent color — used for CTAs, active navigation, focus rings, and progress indicators. This creates a distinctive, recognizable identity.

3. **Monospace for data.** Domain names, statistics, timestamps, and any numerical/code content use JetBrains Mono. This visually separates "data" from "UI chrome."

4. **Semantic color is functional.** Red = critical/error. Orange = high/warning. Green = success/active. Blue = info/secondary. These mappings are consistent across every surface (badges, cards, Telegram messages).

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

## 10. File Reference

| File | Role |
|------|------|
| `src/api/frontend/src/styles/tokens.css` | Source of truth for all design tokens |
| `src/api/frontend/src/styles/global.css` | Global component classes and utilities |
| `src/api/frontend/src/App.svelte` | App shell layout (sidebar + main) |
| `src/api/frontend/src/lib/StatCard.svelte` | Reusable stat card component |
| `src/api/frontend/src/views/*.svelte` | View-specific styles (scoped) |
