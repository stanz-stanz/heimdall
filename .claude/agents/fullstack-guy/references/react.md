# React Frontend for Real-Time FastAPI Apps

This reference covers wiring a React frontend to a FastAPI WebSocket backend. Read `animations.md` alongside this file for CSS animation patterns.

---

## Project setup

```bash
npm create vite@latest frontend -- --template react-ts
cd frontend
npm install
```

Configure the Vite proxy in `vite.config.ts` as described in the main SKILL.md (the `/ws` proxy with `ws: true` is mandatory for dev).

---

## The WebSocket hook

A custom hook encapsulates connection lifecycle, reconnection, and message dispatch. Components consume it without touching raw WebSocket APIs.

```tsx
// src/hooks/useWebSocket.ts
import { useEffect, useRef, useState, useCallback } from 'react';

export type WSStatus = 'connecting' | 'open' | 'closed' | 'error';

export interface WSMessage {
  type: string;
  payload: Record<string, unknown>;
  ts: number;
}

interface UseWebSocketOptions {
  path: string;
  onMessage?: (msg: WSMessage) => void;
  maxHistory?: number;
}

export function useWebSocket({ path, onMessage, maxHistory = 500 }: UseWebSocketOptions) {
  const [status, setStatus] = useState<WSStatus>('closed');
  const [messages, setMessages] = useState<WSMessage[]>([]);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttempts = useRef(0);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout>>();
  const pingInterval = useRef<ReturnType<typeof setInterval>>();
  const onMessageRef = useRef(onMessage);

  // Keep callback ref fresh without re-triggering effect
  useEffect(() => { onMessageRef.current = onMessage; }, [onMessage]);

  const MAX_RECONNECT_DELAY = 30_000;

  const getBackoff = useCallback(() => {
    const base = Math.min(1000 * 2 ** reconnectAttempts.current, MAX_RECONNECT_DELAY);
    return base + Math.random() * base * 0.3;
  }, []);

  const cleanup = useCallback(() => {
    if (pingInterval.current) clearInterval(pingInterval.current);
    pingInterval.current = undefined;
  }, []);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const url = `${protocol}//${window.location.host}${path}`;

    setStatus('connecting');
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      setStatus('open');
      reconnectAttempts.current = 0;

      // Heartbeat
      pingInterval.current = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: 'ping' }));
        }
      }, 30_000);
    };

    ws.onmessage = (event) => {
      try {
        const msg: WSMessage = JSON.parse(event.data);
        if (msg.type === 'pong') return;
        setMessages(prev => [...prev.slice(-(maxHistory - 1)), msg]);
        onMessageRef.current?.(msg);
      } catch {
        console.warn('Non-JSON WebSocket message:', event.data);
      }
    };

    ws.onclose = () => {
      cleanup();
      setStatus('closed');
      const delay = getBackoff();
      reconnectAttempts.current++;
      reconnectTimer.current = setTimeout(connect, delay);
    };

    ws.onerror = () => {
      cleanup();
      setStatus('error');
    };
  }, [path, maxHistory, cleanup, getBackoff]);

  const disconnect = useCallback(() => {
    if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
    cleanup();
    wsRef.current?.close();
    wsRef.current = null;
    setStatus('closed');
  }, [cleanup]);

  const send = useCallback((type: string, payload: Record<string, unknown> = {}) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type, payload, ts: Date.now() / 1000 }));
    } else {
      console.warn('WebSocket not open — message dropped:', type);
    }
  }, []);

  // Connect on mount, disconnect on unmount
  useEffect(() => {
    connect();
    return disconnect;
  }, [connect, disconnect]);

  return { status, messages, send, disconnect };
}
```

### Usage in a component

```tsx
import { useWebSocket } from '../hooks/useWebSocket';

export function ChatRoom() {
  const { status, messages, send } = useWebSocket({ path: '/ws/chat' });
  const [input, setInput] = useState('');

  const handleSend = () => {
    if (!input.trim()) return;
    send('chat.message', { text: input });
    setInput('');
  };

  return (
    <div>
      <span className={`status-badge ${status === 'open' ? 'online' : 'offline'}`}>
        {status}
      </span>

      <ul className="message-list">
        {messages
          .filter(m => m.type === 'chat.message')
          .map((m, i) => (
            <li key={m.ts + '-' + i} className="message-item animate-slide-in">
              {String(m.payload.text)}
            </li>
          ))}
      </ul>

      <input
        value={input}
        onChange={e => setInput(e.target.value)}
        onKeyDown={e => e.key === 'Enter' && handleSend()}
      />
      <button onClick={handleSend} disabled={status !== 'open'}>Send</button>
    </div>
  );
}
```

---

## Patterns for real-time data

### Animated number counter

For dashboard metrics that update over the wire, animate the number transition:

```tsx
// src/components/AnimatedCounter.tsx
import { useEffect, useRef, useState } from 'react';

interface Props {
  value: number;
  duration?: number;
  formatFn?: (n: number) => string;
}

export function AnimatedCounter({ value, duration = 600, formatFn }: Props) {
  const [display, setDisplay] = useState(value);
  const prevRef = useRef(value);
  const frameRef = useRef<number>();

  useEffect(() => {
    const from = prevRef.current;
    const to = value;
    prevRef.current = value;

    if (from === to) return;

    const start = performance.now();
    const tick = (now: number) => {
      const elapsed = now - start;
      const progress = Math.min(elapsed / duration, 1);
      // Cubic ease-out
      const eased = 1 - (1 - progress) ** 3;
      setDisplay(from + (to - from) * eased);
      if (progress < 1) {
        frameRef.current = requestAnimationFrame(tick);
      }
    };
    frameRef.current = requestAnimationFrame(tick);

    return () => { if (frameRef.current) cancelAnimationFrame(frameRef.current); };
  }, [value, duration]);

  const formatted = formatFn ? formatFn(display) : Math.round(display).toLocaleString();

  return <span className="animated-counter">{formatted}</span>;
}
```

Usage with the WebSocket hook:

```tsx
function Dashboard() {
  const [activeUsers, setActiveUsers] = useState(0);

  const { status } = useWebSocket({
    path: '/ws/metrics',
    onMessage: (msg) => {
      if (msg.type === 'metric.update' && msg.payload.key === 'active_users') {
        setActiveUsers(msg.payload.value as number);
      }
    },
  });

  return (
    <div className="metric-card">
      <span className="metric-label">Active Users</span>
      <AnimatedCounter value={activeUsers} />
    </div>
  );
}
```

### Live list with CSS animation on entry

```tsx
function LiveFeed() {
  const { messages } = useWebSocket({ path: '/ws/feed' });
  const items = messages.filter(m => m.type === 'item.new');

  return (
    <ul className="live-list">
      {items.map((item, i) => (
        <li
          key={item.ts + '-' + i}
          className="live-item"
          style={{ animationDelay: `${i * 50}ms` }}
        >
          {JSON.stringify(item.payload)}
        </li>
      ))}
    </ul>
  );
}
```

Pair with CSS from `animations.md`:

```css
.live-item {
  animation: slide-in-left 0.4s cubic-bezier(0.22, 1, 0.36, 1) both;
}
```

### Presence dot

```tsx
function PresenceDot({ online }: { online: boolean }) {
  return <span className={`presence ${online ? 'online' : ''}`} />;
}
```

CSS:

```css
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
  animation: pulse 2s ease-in-out infinite;
}
@keyframes pulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(166, 227, 161, 0.5); }
  50% { box-shadow: 0 0 0 6px rgba(166, 227, 161, 0); }
}
```

---

## React-specific tips

- **`useRef` for the WebSocket instance** — never store a WebSocket in state. State changes trigger re-renders; refs don't. The hook above demonstrates this correctly.
- **`onMessage` callback via ref** — the hook stores the callback in a ref (`onMessageRef`) so the WebSocket's `onmessage` handler always sees the latest callback without needing to close and reopen the connection every time the parent re-renders.
- **Avoid re-renders on every message.** If you're displaying a high-frequency feed (>10 msg/s), buffer messages with `useRef` and flush to state on a `requestAnimationFrame` cadence:

```tsx
const bufferRef = useRef<WSMessage[]>([]);
const rafRef = useRef<number>();

const onMessage = useCallback((msg: WSMessage) => {
  bufferRef.current.push(msg);
  if (!rafRef.current) {
    rafRef.current = requestAnimationFrame(() => {
      setMessages(prev => [...prev, ...bufferRef.current].slice(-500));
      bufferRef.current = [];
      rafRef.current = undefined;
    });
  }
}, []);
```

- **Key stability for animations.** Use `msg.ts` (or a server-assigned ID in the payload) as the React key — not the array index. Index-based keys break entry animations when the list shifts.
- **`useReducer` over `useState` for complex state.** If the WebSocket drives multiple pieces of state (messages, presence, metrics), a reducer keeps updates atomic and debuggable.

```tsx
type Action =
  | { type: 'chat.message'; payload: { text: string; user: string } }
  | { type: 'presence.update'; payload: { users: string[] } }
  | { type: 'metric.update'; payload: { key: string; value: number } };

function appReducer(state: AppState, action: Action): AppState {
  switch (action.type) {
    case 'chat.message':
      return { ...state, messages: [...state.messages, action.payload] };
    case 'presence.update':
      return { ...state, onlineUsers: action.payload.users };
    case 'metric.update':
      return { ...state, metrics: { ...state.metrics, [action.payload.key]: action.payload.value } };
    default:
      return state;
  }
}
```