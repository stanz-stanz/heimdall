# CSS Animations for Real-Time UIs

Animations in real-time apps serve a specific purpose: they signal *change*. A new chat message sliding in, a metric ticking up, a user going offline — animations make these state transitions legible rather than jarring. This reference covers patterns that work well with WebSocket-driven data.

---

## Foundational rule: compositor-only properties

Real-time UIs can receive many updates per second. Animations MUST stick to properties the GPU compositor handles natively to avoid layout thrashing:

- **`transform`** — translate, scale, rotate (use for movement and size)
- **`opacity`** — fade in/out
- **`filter`** — blur, brightness (use sparingly)

Never animate `width`, `height`, `top`, `left`, `margin`, `padding`, `border-width`, or `font-size` — these trigger layout recalculation on every frame.

```css
/* Good — compositor only */
.slide-in { transform: translateX(-20px); opacity: 0; }

/* Bad — triggers layout */
.slide-in { margin-left: -20px; opacity: 0; }
```

---

## Entry animations (new data arriving)

These fire when a WebSocket message adds an element to the DOM.

### Slide + fade (the workhorse)

```css
@keyframes slide-in-left {
  from { opacity: 0; transform: translateX(-20px); }
  to   { opacity: 1; transform: translateX(0); }
}
@keyframes slide-in-up {
  from { opacity: 0; transform: translateY(12px); }
  to   { opacity: 1; transform: translateY(0); }
}
@keyframes slide-in-down {
  from { opacity: 0; transform: translateY(-12px); }
  to   { opacity: 1; transform: translateY(0); }
}

.animate-slide-in {
  animation: slide-in-left 0.4s cubic-bezier(0.22, 1, 0.36, 1) both;
}
.animate-slide-up {
  animation: slide-in-up 0.35s cubic-bezier(0.22, 1, 0.36, 1) both;
}
```

### Scale pop (notifications, toasts, badges)

```css
@keyframes scale-pop {
  from { opacity: 0; transform: scale(0.85); }
  60%  { transform: scale(1.03); }
  to   { opacity: 1; transform: scale(1); }
}
.animate-pop {
  animation: scale-pop 0.35s cubic-bezier(0.34, 1.56, 0.64, 1) both;
}
```

### Staggered entry (list items arriving in batch)

When the server sends a snapshot (e.g., on reconnect), stagger the entry of each item:

```css
.stagger-item {
  animation: slide-in-up 0.4s cubic-bezier(0.22, 1, 0.36, 1) both;
  /* Each item's delay is set inline via style="animation-delay: Xms" */
}
```

In JS, compute the delay per item:

```js
items.forEach((item, i) => {
  item.style.animationDelay = `${i * 60}ms`;
});
```

Cap the maximum total stagger at ~500ms (8-9 items) so it doesn't feel sluggish. For longer lists, group by batches or skip animation on items beyond the viewport.

---

## Value change animations (metrics, counters, statuses)

### Flash highlight on change

When a value updates, briefly highlight the container:

```css
@keyframes flash-highlight {
  0%   { background-color: var(--accent-dim, rgba(137, 180, 250, 0.15)); }
  100% { background-color: transparent; }
}
.flash-on-change {
  animation: flash-highlight 0.8s ease-out;
}
```

In JS, re-trigger the animation by removing and re-adding the class:

```js
function flashElement(el: HTMLElement) {
  el.classList.remove('flash-on-change');
  // Force reflow so the browser registers the removal
  void el.offsetWidth;
  el.classList.add('flash-on-change');
}
```

### Color-coded direction (up/down indicators)

```css
.delta-up   { color: var(--green, #a6e3a1); }
.delta-down { color: var(--red, #f38ba8); }

@keyframes bump-up {
  0%   { transform: translateY(0); }
  40%  { transform: translateY(-3px); }
  100% { transform: translateY(0); }
}
@keyframes bump-down {
  0%   { transform: translateY(0); }
  40%  { transform: translateY(3px); }
  100% { transform: translateY(0); }
}
.delta-up   { animation: bump-up 0.4s ease-out; }
.delta-down { animation: bump-down 0.4s ease-out; }
```

### Number ticking (CSS-only approach for simple cases)

For a pure-CSS counter animation, use `@property` (Chrome/Edge; Safari 15.4+):

```css
@property --num {
  syntax: "<integer>";
  initial-value: 0;
  inherits: false;
}
.ticker {
  transition: --num 0.6s cubic-bezier(0.22, 1, 0.36, 1);
  counter-reset: num var(--num);
  font-variant-numeric: tabular-nums;
}
.ticker::after {
  content: counter(num);
}
```

Set the value via inline style: `style="--num: 1234"`. This is great for simple counters but limited to integers. For formatted numbers or complex cases, use the JS-based `AnimatedCounter` from the React or Svelte reference files.

---

## Presence and status animations

### Pulse (online indicator)

```css
@keyframes pulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(166, 227, 161, 0.5); }
  50%      { box-shadow: 0 0 0 6px rgba(166, 227, 161, 0); }
}
.presence-online {
  background: var(--green, #a6e3a1);
  animation: pulse 2s ease-in-out infinite;
}
```

### Breathing glow (loading / syncing)

```css
@keyframes breathe {
  0%, 100% { opacity: 0.4; }
  50%      { opacity: 1; }
}
.syncing {
  animation: breathe 1.5s ease-in-out infinite;
}
```

### Connection status bar

```css
.connection-bar {
  height: 3px;
  width: 100%;
  position: fixed;
  top: 0;
  left: 0;
  z-index: 9999;
  transition: background-color 0.4s ease, opacity 0.4s ease;
}
.connection-bar.open     { background: var(--green, #a6e3a1); opacity: 0; }
.connection-bar.connecting { background: var(--yellow, #f9e2af); opacity: 1; animation: breathe 1s ease-in-out infinite; }
.connection-bar.closed   { background: var(--red, #f38ba8); opacity: 1; }
.connection-bar.error    { background: var(--red, #f38ba8); opacity: 1; }
```

---

## FLIP animations (list reordering)

When WebSocket data reorders a list (leaderboards, priority queues), use the FLIP technique (First, Last, Invert, Play) for smooth positional transitions.

Svelte handles this natively with `animate:flip`. For React, here's the manual approach:

```ts
function flipAnimate(container: HTMLElement) {
  const children = Array.from(container.children) as HTMLElement[];

  // FIRST: Record current positions
  const firstRects = new Map<string, DOMRect>();
  children.forEach(child => {
    firstRects.set(child.dataset.id!, child.getBoundingClientRect());
  });

  // LAST: After DOM update, read new positions (call this after React commit)
  requestAnimationFrame(() => {
    children.forEach(child => {
      const id = child.dataset.id!;
      const first = firstRects.get(id);
      if (!first) return;

      const last = child.getBoundingClientRect();
      const deltaX = first.left - last.left;
      const deltaY = first.top - last.top;

      if (deltaX === 0 && deltaY === 0) return;

      // INVERT
      child.style.transform = `translate(${deltaX}px, ${deltaY}px)`;
      child.style.transition = 'none';

      // PLAY
      requestAnimationFrame(() => {
        child.style.transition = 'transform 0.35s cubic-bezier(0.22, 1, 0.36, 1)';
        child.style.transform = '';
      });
    });
  });
}
```

---

## Skeleton → content transition

Show skeleton placeholders while waiting for the initial WebSocket snapshot, then crossfade to real content:

```css
@keyframes shimmer {
  0%   { background-position: -200% 0; }
  100% { background-position: 200% 0; }
}
.skeleton {
  background: linear-gradient(
    90deg,
    var(--skeleton-base, #2a2a3c) 25%,
    var(--skeleton-highlight, #3a3a4c) 50%,
    var(--skeleton-base, #2a2a3c) 75%
  );
  background-size: 200% 100%;
  animation: shimmer 1.5s ease-in-out infinite;
  border-radius: 6px;
}
.skeleton-to-content {
  animation: fade-in 0.4s ease-out both;
}
@keyframes fade-in {
  from { opacity: 0; }
  to   { opacity: 1; }
}
```

---

## Performance rules

1. **`will-change` sparingly.** Only add `will-change: transform, opacity` to elements that are *currently* animating or *about to* animate. Never leave it on permanently — it forces the browser to maintain a compositor layer, burning GPU memory.

2. **`prefers-reduced-motion`.** Always respect the user's OS-level setting:
```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
}
```

3. **Throttle high-frequency updates.** If the WebSocket sends >10 updates/second, batch them before rendering. Use `requestAnimationFrame` to coalesce:
```js
let pendingUpdate: any = null;
let rafId: number | null = null;

function onWSMessage(data: any) {
  pendingUpdate = data; // Keep only the latest
  if (!rafId) {
    rafId = requestAnimationFrame(() => {
      applyUpdate(pendingUpdate);
      rafId = null;
    });
  }
}
```

4. **Avoid animating more than ~20 elements simultaneously.** For large lists, only animate items in the viewport. Use `IntersectionObserver` to detect visibility.

5. **`font-variant-numeric: tabular-nums`** on any animated number — prevents layout shift as digits change width (e.g., "1" vs "4").

---

## Easing reference

| Easing | CSS value | Best for |
|---|---|---|
| Smooth decelerate | `cubic-bezier(0.22, 1, 0.36, 1)` | Entries, slides (the default workhorse) |
| Overshoot / bounce | `cubic-bezier(0.34, 1.56, 0.64, 1)` | Pop-in effects, toasts, badges |
| Snappy | `cubic-bezier(0.16, 1, 0.3, 1)` | Quick UI responses, hover states |
| Gentle ease-in-out | `ease-in-out` | Looping animations (pulse, breathe) |
| Linear | `linear` | Progress bars, continuous motion |