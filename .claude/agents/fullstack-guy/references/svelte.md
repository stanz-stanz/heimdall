# Svelte Frontend for Real-Time FastAPI Apps

This reference covers wiring a Svelte frontend to a FastAPI WebSocket backend. Read `animations.md` alongside this file for CSS animation patterns.

---

## Project setup

```bash
npm create vite@latest frontend -- --template svelte-ts
cd frontend
npm install
```

Configure the Vite proxy in `vite.config.ts` as described in the main SKILL.md (the `/ws` proxy with `ws: true` is mandatory for dev).

---

## The WebSocket store

Svelte's reactive stores are a natural fit for WebSocket state. Create a single, reusable store that handles connection, reconnection, and message routing.

```ts
// src/lib/ws.ts
import { writable, derived, get } from 'svelte/store';

export type WSStatus = 'connecting' | 'open' | 'closed' | 'error';

interface WSMessage {
  type: string;
  payload: Record<string, unknown>;
  ts: number;
}

function createWebSocketStore(path: string) {
  const status = writable<WSStatus>('closed');
  const lastMessage = writable<WSMessage | null>(null);
  const messages = writable<WSMessage[]>([]);

  let ws: WebSocket | null = null;
  let reconnectAttempts = 0;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  let pingInterval: ReturnType<typeof setInterval> | null = null;

  const MAX_RECONNECT_DELAY = 30_000;

  function getBackoff(): number {
    const base = Math.min(1000 * 2 ** reconnectAttempts, MAX_RECONNECT_DELAY);
    const jitter = Math.random() * base * 0.3;
    return base + jitter;
  }

  function connect() {
    if (ws?.readyState === WebSocket.OPEN) return;

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const url = `${protocol}//${window.location.host}${path}`;

    status.set('connecting');
    ws = new WebSocket(url);

    ws.onopen = () => {
      status.set('open');
      reconnectAttempts = 0;

      // Heartbeat — keeps the connection alive past proxy timeouts
      pingInterval = setInterval(() => {
        if (ws?.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: 'ping' }));
        }
      }, 30_000);
    };

    ws.onmessage = (event) => {
      try {
        const msg: WSMessage = JSON.parse(event.data);
        if (msg.type === 'pong') return; // Swallow heartbeat responses
        lastMessage.set(msg);
        messages.update(arr => [...arr.slice(-499), msg]); // Cap history at 500
      } catch {
        console.warn('Non-JSON WebSocket message:', event.data);
      }
    };

    ws.onclose = () => {
      cleanup();
      status.set('closed');
      scheduleReconnect();
    };

    ws.onerror = () => {
      cleanup();
      status.set('error');
      // onclose fires after onerror — reconnect happens there
    };
  }

  function cleanup() {
    if (pingInterval) clearInterval(pingInterval);
    pingInterval = null;
  }

  function scheduleReconnect() {
    const delay = getBackoff();
    reconnectAttempts++;
    reconnectTimer = setTimeout(connect, delay);
  }

  function send(type: string, payload: Record<string, unknown> = {}) {
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type, payload, ts: Date.now() / 1000 }));
    } else {
      console.warn('WebSocket not open — message dropped:', type);
    }
  }

  function disconnect() {
    if (reconnectTimer) clearTimeout(reconnectTimer);
    cleanup();
    ws?.close();
    ws = null;
    status.set('closed');
  }

  // Derived: filter messages by type
  function messagesOfType(type: string) {
    return derived(messages, $msgs => $msgs.filter(m => m.type === type));
  }

  return { status, lastMessage, messages, connect, disconnect, send, messagesOfType };
}

// Export a singleton for the main channel — create additional stores for other channels
export const ws = createWebSocketStore('/ws/main');
```

### Usage in a component

```svelte
<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { ws } from '$lib/ws';

  const { status, lastMessage, connect, disconnect, send } = ws;

  onMount(connect);
  onDestroy(disconnect);

  let input = '';

  function handleSend() {
    send('chat.message', { text: input });
    input = '';
  }
</script>

<div class="status-badge" class:online={$status === 'open'} class:offline={$status !== 'open'}>
  {$status}
</div>

{#if $lastMessage}
  <p>Latest: {$lastMessage.type} — {JSON.stringify($lastMessage.payload)}</p>
{/if}

<input bind:value={input} on:keydown={(e) => e.key === 'Enter' && handleSend()} />
<button on:click={handleSend} disabled={$status !== 'open'}>Send</button>
```

---

## Patterns for real-time data

### Live list with animated entry

```svelte
<script lang="ts">
  import { ws } from '$lib/ws';
  import { flip } from 'svelte/animate';
  import { fly, fade } from 'svelte/transition';

  const items = ws.messagesOfType('item.new');
</script>

<ul class="live-list">
  {#each $items as item (item.ts)}
    <li
      animate:flip={{ duration: 300 }}
      in:fly={{ y: -20, duration: 400, easing: cubicOut }}
      out:fade={{ duration: 200 }}
      class="live-item"
    >
      {JSON.stringify(item.payload)}
    </li>
  {/each}
</ul>

<style>
  .live-list {
    list-style: none;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }
  .live-item {
    padding: 0.75rem 1rem;
    border-radius: 8px;
    background: var(--surface, #1e1e2e);
    border-left: 3px solid var(--accent, #89b4fa);
  }
</style>
```

### Dashboard metric card with number animation

```svelte
<script lang="ts">
  import { tweened } from 'svelte/motion';
  import { cubicOut } from 'svelte/easing';
  import { ws } from '$lib/ws';

  const value = tweened(0, { duration: 600, easing: cubicOut });

  // React to incoming metric updates
  const metrics = ws.messagesOfType('metric.update');
  $: latestMetric = $metrics[$metrics.length - 1];
  $: if (latestMetric) value.set(latestMetric.payload.value as number);
</script>

<div class="metric-card">
  <span class="metric-label">Active Users</span>
  <span class="metric-value">{Math.round($value).toLocaleString()}</span>
</div>

<style>
  .metric-card {
    display: flex;
    flex-direction: column;
    padding: 1.5rem;
    border-radius: 12px;
    background: var(--surface, #1e1e2e);
    box-shadow: 0 2px 12px rgba(0, 0, 0, 0.15);
    transition: box-shadow 0.3s ease;
  }
  .metric-card:hover {
    box-shadow: 0 4px 24px rgba(0, 0, 0, 0.25);
  }
  .metric-label {
    font-size: 0.85rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    opacity: 0.6;
  }
  .metric-value {
    font-size: 2.5rem;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
  }
</style>
```

### Presence indicator

```svelte
<script lang="ts">
  export let online = false;
</script>

<span class="presence" class:online />

<style>
  .presence {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    background: var(--muted, #6c7086);
    display: inline-block;
    transition: background 0.3s ease;
  }
  .presence.online {
    background: var(--green, #a6e3a1);
    box-shadow: 0 0 0 0 rgba(166, 227, 161, 0.5);
    animation: pulse 2s ease-in-out infinite;
  }
  @keyframes pulse {
    0%, 100% { box-shadow: 0 0 0 0 rgba(166, 227, 161, 0.5); }
    50% { box-shadow: 0 0 0 6px rgba(166, 227, 161, 0); }
  }
</style>
```

---

## Svelte 5 runes — critical patterns

### DANGER: Getter functions break reactivity

In `.svelte.js` modules, **never export getter functions** to expose `$state`. Svelte 5 tracks reactivity through property access on `$state` objects — calling a function that returns the value breaks the tracking chain. The template renders once and never updates.

```js
// BAD — template won't react to changes
let count = $state(0);
export function getCount() { return count; }  // ← breaks reactivity

// GOOD — direct property access is tracked
export const state = $state({ count: 0 });     // ← reactive in templates
```

In `.svelte` templates:
```svelte
<!-- BAD: {getCount()} — renders once, never updates -->
<!-- GOOD: {state.count} — Svelte tracks the property read -->
```

### DANGER: Writing `$state` inside `$effect` causes infinite loops

`$effect` re-runs when any `$state` it reads changes. If the effect body also *writes* to `$state`, Svelte detects a circular dependency and throws `effect_update_depth_exceeded`, freezing the entire app.

Fix: wrap the writes in `untrack()` so Svelte doesn't track the reads inside the write block.

```js
import { untrack } from 'svelte';

// BAD — infinite loop: reads wsState.lastMessage, writes to localState
$effect(() => {
  const msg = wsState.lastMessage;
  if (msg) localState = processMessage(msg);  // ← writes $state → re-triggers effect
});

// GOOD — only wsState.lastMessage triggers the effect, writes are untracked
$effect(() => {
  const msg = wsState.lastMessage;
  if (!msg) return;
  untrack(() => {
    localState = processMessage(msg);  // ← write doesn't re-trigger
  });
});
```

This pattern is essential for any WebSocket → local state update flow.

---

## Svelte-specific tips

- **Svelte's built-in `transition:` and `animate:` directives** are first-class. Prefer them over raw CSS animations for list entry/exit/reorder — they handle DOM lifecycle correctly.
- **`tweened` and `spring`** from `svelte/motion` are purpose-built for animating numeric values driven by live data. Use `tweened` for metrics, `spring` for drag/positional changes.
- **Keep the WS store in `src/lib/`** so SvelteKit can import it from `$lib/ws` in any route or layout.
- **For SvelteKit SSR**, guard the WebSocket connection with `if (browser)` from `$app/environment` — WebSocket is browser-only.

```ts
import { browser } from '$app/environment';
import { onMount } from 'svelte';

onMount(() => {
  if (browser) ws.connect();
});
```