# Design System v1.1 Rollout — Design

**Date:** 2026-04-21
**Scope:** Operator Console frontend (`src/api/frontend/`)
**Authoritative spec:** `docs/design/design-system.md` v1.1
**Status:** Design approved 2026-04-21

---

## 1. Context

`docs/design/design-system.md` was updated to v1.1 on 2026-04-21. None of the v1.1 implementation has landed in CSS/Svelte:

- New tokens (`--red-soft`, `--red-muted`, `--red-outline`, `--bg-overlay`, `--shadow-overlay`, `--overlay-backdrop`) missing from `tokens.css`.
- 10 type utility classes (`.t-display` … `.t-mono-stat`) missing from `global.css`.
- 5 elevation utilities (`.overlay`, `.scrim`, `.modal`, `.dropdown`, `.toast`) missing from `global.css`.
- `.badge-medium` and `.badge-interpreted` still wear gold — violates v1.1 axiom "gold is brand-exclusive."
- `.badge-low` does not exist.
- `CampaignCard.svelte` stat label is 9px — below v1.1 minimum of 11px.
- 53 raw `font-size:` declarations across 10 files — v1.1 requires all text styling to use the type scale.

This design describes a three-wave rollout that brings the implementation fully in line with v1.1. Approach "A" (full migration) was selected — anything less leaves the axiom violations live in the console.

---

## 2. Wave Structure

Each wave gates the next. A wave may only start when the previous wave is merged and verified.

### Wave 1 — Foundations

**Agent count:** 1 (serial).
**Files touched:** `src/api/frontend/src/styles/tokens.css`, `src/api/frontend/src/styles/global.css`.
**Nature of change:** purely additive — no existing declarations removed or modified.

Deliverables:

- `tokens.css` — append six tokens exactly as specified in §1.1 / §1.5 of `design-system.md`:
  - `--red-soft: #f87171`
  - `--red-muted: rgba(239, 68, 68, 0.07)`
  - `--red-outline: rgba(239, 68, 68, 0.38)`
  - `--bg-overlay: #1e2c48`
  - `--shadow-overlay:` three-layer drop + 1px gold rim (exact value per agent's interpretation of spec §1.5 + accessibility preview)
  - `--overlay-backdrop: rgba(6, 13, 26, 0.72)`
- `global.css` — append the 10 type utility classes per §1.2. Values, weights, fonts, transforms exactly as tabulated.
- `global.css` — append five elevation utility classes per §1.5 (`.overlay`, `.scrim`, `.modal`, `.dropdown`, `.toast`).

**Verification:**

- `npm run build` succeeds.
- Grep confirms the six new tokens and the 15 new class selectors exist.
- Existing console renders identically (nothing consumed the new classes yet).

**Blocks:** Waves 2 and 3.

### Wave 2 — Semantic fixes

**Agent count:** 2 fullstack-guy instances running in parallel.
**File-disjoint by construction** — 2A and 2B never touch the same file.

#### Wave 2A — Badge rewrite

Files: `src/api/frontend/src/styles/global.css` (badge block only), `src/api/frontend/src/components/Badge.svelte`.

- `.badge-medium` → `color: var(--red-soft); background: var(--red-muted); border: 1px solid var(--red-outline);`
- `.badge-low` (new) → `color: var(--text-dim); background: var(--red-muted); border: 1px solid var(--red-outline);`
- `.badge-interpreted` → neutral outline: `color: var(--text-dim); background: transparent; border: 1px solid var(--border);` (gold fully removed)
- `Badge.svelte` — confirm a `low` severity prop route exists and points to `.badge-low`. Add if missing.
- Apply `.t-caption` sizing to the base `.badge` class (replacing any raw `font-size` on badges).

#### Wave 2B — CampaignCard conformance

Files: `src/api/frontend/src/components/CampaignCard.svelte` only.

- Stat label 9px → 11px via `.t-caption`.
- Migrate all three raw `font-size` usages in this file to the type scale (`.t-mono-stat` for value, `.t-caption` for label, `.t-subheading` for campaign name).

**Verification (for both 2A and 2B):**

- `npm run build` succeeds for each sub-wave independently.
- Console loads; medium/low/interpreted badges visually match spec (no gold on severity, red outline visible on medium/low).
- CampaignCard stat label is legible (≥11px).
- Reviewer checklist §11.7: no raw `font-size`, no size <11px, no gold on severity, no uppercase+tracking >2 words.

**Blocks:** Wave 3.

### Wave 3 — View migration

**Agent count:** 1 (serial).
**Files:** all remaining files with raw `font-size` declarations.

Scope — migrate every remaining raw `font-size:` to the type scale introduced in Wave 1. Baseline grep on 2026-04-21 showed 53 occurrences across these files (CampaignCard's 3 are handled by Wave 2B):

| File | Raw font-size count (baseline) |
|------|------|
| `src/api/frontend/src/styles/global.css` | 21 (minus those W2A converts in the badge block) |
| `src/api/frontend/src/components/Sidebar.svelte` | 7 |
| `src/api/frontend/src/components/Topbar.svelte` | 2 |
| `src/api/frontend/src/components/FilterChips.svelte` | 1 |
| `src/api/frontend/src/views/Settings.svelte` | 8 |
| `src/api/frontend/src/views/Logs.svelte` | 5 |
| `src/api/frontend/src/views/Pipeline.svelte` | 2 |
| `src/api/frontend/src/views/Prospects.svelte` | 3 |
| `src/api/frontend/src/views/Clients.svelte` | 1 |

Files with **zero baseline hits** (`Dashboard.svelte`, `Campaigns.svelte`, `DataTable.svelte`, `FeedItem.svelte`, `ProgressBar.svelte`, `StatCard.svelte`, `Badge.svelte`) are auto-pass for font-size migration but still subject to the visual verification pass in §4.

Per-declaration decision matrix (agent chooses the closest type-class match):

| Original pattern | Target class |
|------------------|--------------|
| Headings 28/600 mono | `.t-display` |
| Headings 22/700 sans | `.t-title` |
| Headings 18/600 sans | `.t-heading` |
| Subheadings 16/600 sans | `.t-subheading` |
| Section headers (uppercase) | `.t-section` |
| Body 13/400 | `.t-body` |
| Body 13/500 | `.t-body-strong` |
| Labels 12/500 | `.t-label` |
| Badges/nav caption 11/600 upper | `.t-caption` |
| Mono data 12/500 | `.t-mono-label` |
| Mono stat 18/700 | `.t-mono-stat` |

If a raw declaration does not fit any class cleanly, the agent must stop and ask — do not invent new sizes.

**Verification:**

- `grep -rE 'font-size:\s*\d+px' src/api/frontend/src` returns zero results.
- `npm run build` succeeds.
- Every view renders without visible regression (operator walks through all 8 views: Dashboard, Pipeline, Campaigns, Prospects, Clients, Logs, Settings, Demo).
- Reviewer checklist §11.7 passes on the full diff.

---

## 3. File Ownership Map (collision-free)

| Wave | Agent | Files |
|------|-------|-------|
| 1 | W1 | `tokens.css`, `global.css` |
| 2A | W2A | `global.css` (badge block only), `Badge.svelte` |
| 2B | W2B | `CampaignCard.svelte` |
| 3 | W3 | all remaining Svelte files + `global.css` residual |

No file appears in two concurrent agents' lists. Wave 2A and 2B both touch `global.css` only because 2A touches a fixed, bounded region (the badge block); in practice we serialise 2A → 2B if the agent is unsure of block boundaries, but they are file-disjoint in spirit.

To keep this safe: Wave 2A restricts edits to the single `/* Badges */` comment block in `global.css`. The coordinating session will verify the diff before merging.

---

## 4. Verification Strategy

Each wave ends with:

1. `npm run build` green.
2. Visual browser check at `http://localhost:8001/app` (dev console port).
3. Reviewer-checklist walkthrough from `design-system.md` §11.7:
   - No raw `font-size:` outside the type scale
   - No size below 11px
   - No `--text-muted` on operator-essential information
   - No uppercase + tracking on strings > 2 words
   - No explanatory paragraph without `max-width` cap
   - No gold text on gold-glow at body size
   - No blue or green on a vulnerability finding

The checklist is the gate. A wave is not considered landed until every checklist item passes on its diff.

---

## 5. Out of Scope

- Component library additions beyond what v1.1 requires (no new reusable components).
- Accessibility audits beyond v1.1's explicit rules (§9, §11).
- Tests/screenshots beyond existing `npm run build` + visual operator check — Svelte component tests are not currently part of the repo's CI and this rollout does not introduce them.
- Backporting v1.1 tokens to any Telegram message composer or server-side HTML.
- Light theme (out of scope per §8 principle 6).

---

## 6. Risks

- **Silent regressions in views.** Wave 3 is a mechanical refactor, but a wrong type-class mapping could change perceived hierarchy. Mitigation: the decision matrix above is tight, and the final reviewer-checklist walkthrough is a per-view visual check.
- **`global.css` contention between W2A and W3.** W2A edits the badge block; W3 edits the residual raw font-sizes elsewhere in the file. Because W2 must land before W3 starts, there is no actual concurrency on `global.css` — sequencing prevents the collision.
- **Spec ambiguity on `--shadow-overlay`.** §1.5 describes "3-layer drop + 1px gold rim" without exact pixel values. Wave 1 agent will propose a concrete value in the PR and confirm before merge.

---

## 7. Acceptance

This rollout is complete when:

- All three waves are merged to `main`.
- `grep -rE 'font-size:\s*\d+px' src/api/frontend/src` returns zero matches.
- `grep -E '(--red-soft|--red-muted|--red-outline|--bg-overlay|--shadow-overlay|--overlay-backdrop)' src/api/frontend/src/styles/tokens.css` returns all six tokens.
- Badges `medium` and `low` render in the warm-family treatment; `.badge-interpreted` has no gold.
- CampaignCard stat label renders at 11px.
- The reviewer-checklist (§11.7) passes on the full rolled-up diff against pre-rollout `main`.
