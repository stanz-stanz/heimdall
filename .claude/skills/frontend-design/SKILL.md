---
name: frontend-design
description: Create and review distinctive web frontends with both aesthetic intent AND web a11y / UX discipline. Use when building or reviewing web components, pages, applications, or HTML email / Telegram message templates. Combines creative direction (avoid generic AI aesthetics) with priority-ordered rules (accessibility CRITICAL, touch CRITICAL, performance HIGH, style HIGH, layout HIGH, typography MEDIUM, animation MEDIUM, forms MEDIUM, navigation HIGH). Stack: SvelteKit (signup site + Console), HTML email templates, Telegram message HTML.
---

# Frontend design — aesthetic + discipline

This skill guides creation and review of web frontend interfaces with two layers:
1. **Aesthetic direction** — distinctive, intentional, not "AI slop"
2. **Web discipline** — accessibility, performance, layout, animation, forms, navigation rules

Both layers apply. A pretty-but-inaccessible page is a bug; a compliant-but-generic page is also a bug.

---

## Layer 1 — Aesthetic direction

Before coding, commit to a clear aesthetic position:
- **Purpose:** What problem does this interface solve? Who uses it?
- **Tone:** Pick a clear direction — refined minimal, content-first editorial, calm professional, playful approachable, etc. Heimdall's audience is SMB owners (restaurant owners, physiotherapists, barbershops); default is **calm professional with personality** — not enterprise-cold, not brutalist-loud.
- **Constraints:** Stack (SvelteKit + Tailwind), performance, accessibility.
- **Differentiation:** What makes it memorable in one phrase?

**Execute the chosen direction with precision.** Refined minimalism and bold maximalism both work — intentionality matters more than intensity.

### Aesthetic guidelines

- **Typography:** Choose distinctive, characterful fonts. Avoid Inter / Arial / Roboto as defaults. Pair a display font with a refined body font. Vary across products — never converge on one default.
- **Color & theme:** Cohesive palette via CSS variables / Tailwind theme. Dominant color + sharp accents beats timid evenly-distributed schemes.
- **Motion:** Use animation for micro-interactions and high-impact moments (page-load reveals with `animation-delay` stagger). Prefer CSS for HTML; Svelte transitions or Motion library for components.
- **Spatial composition:** Asymmetry, overlap, generous negative space OR controlled density — but stay intentional.
- **Backgrounds & detail:** Atmosphere via gradient meshes, noise textures, subtle patterns, layered transparencies, dramatic shadows. Avoid flat solid-color filler.

**Aesthetic anti-patterns (always avoid):**
- Inter / Roboto / Arial as default fonts
- Purple gradients on white backgrounds
- Cookie-cutter SaaS hero (centered headline + CTA + 3-column features)
- Predictable card grids without rhythm
- Convergence on Space Grotesk / "default modern" across projects
- Decorative-only animation (motion without meaning)

---

## Layer 2 — Web discipline (priority-ordered)

Apply rules in priority order. CRITICAL > HIGH > MEDIUM > LOW.

### 1. Accessibility (CRITICAL)
- **Contrast:** ≥4.5:1 for body text against background; ≥3:1 for large text and UI glyphs.
- **Focus rings:** Visible 2–4px focus ring on every interactive element. Don't remove `:focus`.
- **Alt text:** Descriptive `alt` for meaningful images; `alt=""` for decorative.
- **ARIA labels:** `aria-label` on icon-only buttons.
- **Keyboard nav:** Tab order matches visual order; full keyboard support; visible focus.
- **Form labels:** `<label for="…">` for every input. No placeholder-only labels.
- **Color isn't the only signal:** Functional color (error red, success green) must include icon or text.
- **Reduced motion:** Respect `prefers-reduced-motion`; reduce or disable animations.
- **Heading hierarchy:** Sequential `h1 → h6`, no level skip.
- **Skip-to-main-content** link for keyboard users.

### 2. Touch & Interaction (CRITICAL)
- **Touch targets:** Minimum 44×44px. Extend hit area with padding if the icon is small.
- **Touch spacing:** ≥8px gap between targets.
- **No hover-only:** Don't rely on `:hover` for primary interactions — touch devices have no hover.
- **Loading buttons:** Disable + show spinner during async. Never let a user double-click submit.
- **Press feedback:** Visual response within 100ms of tap.
- **Cursor:** `cursor: pointer` on every clickable element.

### 3. Performance (HIGH)
- **Images:** WebP/AVIF, responsive `srcset/sizes`, declare `width/height` or `aspect-ratio` to prevent CLS.
- **Lazy load:** `loading="lazy"` for below-the-fold images and heavy media.
- **Fonts:** `font-display: swap`. Preload only critical fonts.
- **Bundles:** Code-split by route (SvelteKit route-based splitting is automatic — don't fight it).
- **Third-party scripts:** `async` / `defer`. Audit and remove unused.
- **CLS:** Reserve space for async content. Never let layout jump.
- **Input latency:** ≤100ms for taps and scrolls.
- **Virtualize lists** with 50+ items.

### 4. Style Selection & Iconography (HIGH)
- **No emoji as structural icons:** Use SVG icons (Lucide, Heroicons, or a chosen set). Emojis are font-dependent and inconsistent across platforms.
- **Vector-only:** SVG > PNG. Scales cleanly, themes properly.
- **One icon family** per surface. Consistent stroke width (1.5px or 2px), consistent corner radius.
- **Filled vs outline:** Pick one per hierarchy level. Don't mix.
- **Icon sizes** as design tokens (`icon-sm`, `icon-md`, `icon-lg` = e.g. 16/24/32px). No arbitrary values.
- **State clarity:** Hover, pressed, focused, disabled — visually distinct, all on-style.
- **Elevation scale:** Consistent shadow/elevation values for cards, sheets, modals. No random shadow stacks.
- **Primary action:** ONE primary CTA per screen. Secondary actions visually subordinate.
- **Dark-mode pairing:** Design light + dark together. Don't invert; use desaturated tonal variants. Test contrast independently.

### 5. Layout & Responsive (HIGH)
- **Mobile-first:** Design at 375px first, scale up.
- **Breakpoints:** Systematic (375 / 768 / 1024 / 1440). Tailwind defaults are fine.
- **Viewport meta:** `width=device-width, initial-scale=1`. Never disable zoom.
- **No horizontal scroll** on mobile.
- **Spacing rhythm:** 4/8px scale. Vertical hierarchy tiers (16/24/32/48).
- **Container width:** Consistent `max-w` on desktop.
- **z-index scale:** 0 / 10 / 20 / 40 / 100 / 1000. Never `z-[9999]`.
- **Fixed elements:** Reserve safe padding on underlying scroll content.
- **Visual hierarchy:** Size, spacing, contrast — not color alone.

### 6. Typography & Color (MEDIUM)
- **Body size:** ≥16px on mobile (avoids iOS auto-zoom).
- **Line height:** 1.5–1.75 for body text.
- **Line length:** 35–60 chars on mobile, 60–75 on desktop.
- **Font scale:** Consistent (12 / 14 / 16 / 18 / 24 / 32).
- **Weight hierarchy:** Bold headings (600–700), regular body (400), medium labels (500).
- **Semantic color tokens:** `--primary`, `--secondary`, `--error`, `--surface`, `--on-surface`. No raw hex in components.
- **Tabular figures** for data columns, prices, timers (`font-variant-numeric: tabular-nums`).
- **Truncation:** Prefer wrapping. When truncating, use ellipsis + tooltip / expand for full text.

### 7. Animation (MEDIUM)
- **Duration:** 150–300ms for micro-interactions; ≤400ms for complex transitions; never >500ms.
- **Animate `transform` / `opacity` only.** Never `width`, `height`, `top`, `left` (forces layout).
- **Easing:** `ease-out` for entering, `ease-in` for exiting. Avoid `linear` for UI.
- **Motion meaning:** Every animation expresses cause-effect. No decorative-only motion.
- **Exit faster than enter** (~60–70% of enter duration).
- **Stagger** list/grid items by 30–50ms; not all-at-once, not too-slow.
- **Interruptible:** User input cancels in-progress animation immediately.
- **No layout reflow:** Use `transform`, never trigger CLS.
- **Reduced-motion:** Always respect `prefers-reduced-motion: reduce`.

### 8. Forms & Feedback (MEDIUM)
- **Visible label** per input, not placeholder-only.
- **Error placement:** Below the related field, not in a top summary.
- **Inline validation:** On `blur`, not on every keystroke.
- **Required indicators:** Asterisk + `aria-required`.
- **Submit feedback:** Button → loading → success/error.
- **Empty states:** Helpful message + action when no content.
- **Error clarity:** State cause + how to fix. Not "Invalid input."
- **Focus management:** Auto-focus first invalid field after submit error.
- **Toast accessibility:** `aria-live="polite"`. Don't steal focus.
- **Autocomplete:** Use semantic `autocomplete` attributes (`email`, `current-password`, etc.) so browsers can autofill.
- **Destructive emphasis:** Danger color (red) for destructive actions, visually separated from primary.
- **Touch-friendly inputs:** Min height 44px on mobile.

### 9. Navigation Patterns (HIGH)
- **Predictable back:** Browser back must restore scroll, filter, input state.
- **Deep linking:** Every key screen reachable via URL.
- **Active state:** Current location visually highlighted in nav.
- **Modal escape:** Clear close affordance + ESC key. Confirm before dismissing with unsaved changes.
- **No mixed patterns:** Don't use Tab + Sidebar + Bottom Nav at the same hierarchy level.
- **Breadcrumbs** for 3+ level deep hierarchies.
- **Persistent nav:** Don't hide core navigation in sub-flows.
- **Modals are not navigation.** Don't use a modal as a primary navigation step.

### 10. Light/Dark mode
- **Token-driven:** Map all surfaces, text, icons, borders to semantic tokens per theme.
- **Both themes tested:** Don't ship one and infer the other.
- **Modal scrim:** 40–60% black opacity to isolate foreground.
- **State parity:** Pressed / focused / disabled equally distinguishable in both themes.

---

## Heimdall surfaces

Apply this skill to:
- **Signup site** (`apps/signup/`) — SvelteKit. Public-facing; first impression for SMB owners.
- **Console** (`src/console/` + Briefs view per `project_brief_clickthrough_post_a5`) — internal operator UI; correctness > flair.
- **HTML email templates** — limited CSS subset; inline styles required by most clients; `tabular-nums` for prices.
- **Telegram messages** — minimal HTML (`<b>`, `<a>`, line breaks). No CSS, no images >5MB, character limits apply (per `project_telegram_rules` + `project_telegram_buttons`).

Out of scope:
- Charts / data viz (no client-facing charts in Heimdall yet).
- Native iOS / Android / React Native (Heimdall is web only).

---

## Pre-Delivery Checklist (web)

Before shipping any frontend change:

### Visual quality
- [ ] No emojis as structural icons (SVG only).
- [ ] All icons from one consistent family.
- [ ] Pressed states don't shift layout.
- [ ] Semantic theme tokens, no ad-hoc per-component hex.

### Interaction
- [ ] Tap/click feedback within 100ms.
- [ ] Touch targets ≥44×44px.
- [ ] Disabled states visually clear and `disabled` attribute set.
- [ ] No hover-only critical interactions.
- [ ] Keyboard tab order matches visual order.

### Light/dark
- [ ] Body text contrast ≥4.5:1 in both modes.
- [ ] Focus rings visible in both modes.
- [ ] Borders/dividers visible in both modes.

### Layout
- [ ] Tested at 375px AND 1024px+.
- [ ] No horizontal scroll on mobile.
- [ ] 4/8px spacing rhythm maintained.
- [ ] Long-form text doesn't go edge-to-edge on tablet/desktop.

### Accessibility
- [ ] Every meaningful image has `alt`. Decorative images have `alt=""`.
- [ ] Forms have visible labels, helper text, error placement.
- [ ] Color is not the only signal anywhere.
- [ ] `prefers-reduced-motion` honored.
- [ ] Skip-to-main-content link present.

### Performance
- [ ] Images are WebP/AVIF with declared dimensions.
- [ ] Below-fold images use `loading="lazy"`.
- [ ] No CLS from late-loading content.
- [ ] No third-party blocking scripts.
