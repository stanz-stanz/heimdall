---
name: fullstack-guy
description: >
  Build real-time fullstack applications with FastAPI WebSocket backends and lightweight JS frontends (Svelte or React) featuring polished CSS animations. Use this skill whenever the user wants to add WebSocket endpoints to an existing FastAPI app, build a real-time dashboard or live-updating UI, create a chat interface, implement server-sent events or push notifications, stream data from Python to a browser, connect a Svelte or React frontend to a FastAPI backend via WebSockets, animate UI state changes driven by live data, build multiplayer or collaborative features, or any project combining Python backend + JS frontend + real-time communication. Also trigger when the user mentions "FastAPI + WebSocket", "live data", "real-time updates", "streaming UI", "push to browser", or asks to add a reactive frontend to an existing Python API. If the user already has a FastAPI project and wants to bolt on a live frontend, this is the skill.
---

# Realtime Fullstack: FastAPI + WebSocket + JS Frontend + CSS Animations

Build production-grade real-time applications by wiring a FastAPI WebSocket backend to a Svelte or React frontend with fluid CSS animations driven by live data.

## When to read the reference files

This skill is organized in layers. Read only what you need:

| Situation | Read |
|---|---|
| Any realtime task (always start here) | This file — architecture, WebSocket patterns, connection lifecycle |
| User wants **Svelte** frontend | `references/svelte.md` |
| User wants **React** frontend | `references/react.md` |
| User wants polished animations on live data | `references/animations.md` |
| Unclear which frontend | Ask — but default to **Svelte** for new projects (smaller bundle, simpler reactivity model for real-time data). Use React if the user's project already uses it. |

Read the relevant reference files with the `view` tool before writing any code.

---

## Architecture overview

```
┌─────────────┐  WebSocket (ws:// or wss://) ┌──────────────────┐
│  FastAPI    │◄────────────────────────────►│  Svelte / React  │
│  backend    │   JSON messages, binary ok   │  SPA frontend    │
│             │                              │                  │
│  - REST API │  ── HTTP (fetch) ──────────► │  - Components    │
│  - WS routes│                              │  - Animations    │
│  - Pub/sub  │                              │  - State mgmt    │
└─────────────┘                              └──────────────────┘
```

The pattern is always: **FastAPI owns the data and business logic, the frontend owns the pixels.** WebSockets carry state diffs; the frontend applies them reactively and triggers CSS animations on change.

---

## Step 0: Understand the existing project

Before writing code, orient yourself:

1. **Find the FastAPI entrypoint** — typically `main.py`, `app.py`, or `app/main.py`. Look for `app = FastAPI(...)`.
2. **Check existing routers** — `app.include_router(...)` calls. New WebSocket routes should live in their own router file (e.g., `routers/ws.py` or `ws/router.py`).
3. **Identify the data source** — what data will flow over the socket? A database query on interval? An event bus? A subprocess stream? An external API poll?
4. **Check dependencies** — run `pip list | grep -i -E "fastapi|uvicorn|websockets|starlette"` to see what's already installed.

If there is no existing project, scaffold one (see "Greenfield scaffold" below).

---

## Step 1: FastAPI WebSocket endpoint

### Core pattern — the connection lifecycle

Every WebSocket endpoint follows this lifecycle. Deviating from it causes silent failures, leaked connections, or zombie tasks.

```python
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import asyncio
import json

router = APIRouter()

class ConnectionManager:
    """Manages active WebSocket connections and broadcasting."""

    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket):
        self.active.remove(ws)

    async def broadcast(self, message: dict):
        dead = []
        for conn in self.active:
            try:
                await conn.send_json(message)
            except Exception:
                dead.append(conn)
        for conn in dead:
            self.active.remove(conn)

manager = ConnectionManager()

@router.websocket("/ws/{channel}")
async def websocket_endpoint(ws: WebSocket, channel: str):
    await manager.connect(ws)
    try:
        while True:
            data = await ws.receive_json()
            # Process incoming message, then respond or broadcast
            response = await process_message(data, channel)
            await manager.broadcast(response)
    except WebSocketDisconnect:
        manager.disconnect(ws)
    except Exception as e:
        manager.disconnect(ws)
        # Log the error — don't let it vanish silently
        import logging
        logging.exception(f"WebSocket error on /{channel}: {e}")
```

### Key rules

- **Always wrap the receive loop in try/except WebSocketDisconnect.** A missing handler leaks the connection from your manager and causes broadcasts to throw.
- **Always remove dead connections.** The broadcast method above demonstrates defensive pruning.
- **Use `send_json` / `receive_json`** for structured data. Use `send_bytes` / `receive_bytes` for binary (audio, images).
- **Background push pattern** — when the server pushes without client requests (dashboards, tickers), spawn an `asyncio.Task` inside the endpoint and cancel it on disconnect:

```python
@router.websocket("/ws/live-feed")
async def live_feed(ws: WebSocket):
    await ws.accept()
    task = asyncio.create_task(push_loop(ws))
    try:
        while True:
            # Keep the connection alive by reading (even if we discard)
            await ws.receive_text()
    except WebSocketDisconnect:
        task.cancel()

async def push_loop(ws: WebSocket):
    while True:
        data = await fetch_latest_data()
        await ws.send_json(data)
        await asyncio.sleep(1)  # Adjust cadence to use case
```

- **Message protocol** — define a simple message envelope early. This prevents ad-hoc shape drift as the app grows:

```python
# Every message over the wire uses this shape
{
    "type": "event_name",     # e.g., "chat.message", "ticker.update", "presence.join"
    "payload": { ... },       # Typed per event
    "ts": 1711612800.123      # Server timestamp (float, Unix epoch)
}
```

### CORS and mounting the frontend

If the frontend is served separately (dev server on another port), add CORS:

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite / SvelteKit default
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

For production, serve the built frontend as static files:

```python
from fastapi.staticfiles import StaticFiles

# Mount AFTER all API/WS routes so they take precedence
app.mount("/", StaticFiles(directory="frontend/dist", html=True), name="frontend")
```

---

## Step 2: Frontend — see reference files

Read the appropriate reference file based on the user's framework:

- **Svelte** → `view` the file at `references/svelte.md`
- **React** → `view` the file at `references/react.md`

Both files cover: project setup, the WebSocket hook/store, reconnection logic, rendering live data, and integration with the animation patterns from `references/animations.md`.

---

## Step 3: Animations — see `references/animations.md`

Read `references/animations.md` for the CSS animation system. It covers:

- Animating elements as they enter from WebSocket data (fade, slide, scale)
- Number ticking / counter animations for live metrics
- Presence indicators (pulse, glow)
- List reordering with FLIP animations
- Skeleton → content transitions for loading states
- Performance rules (compositor-only transforms, `will-change`, `prefers-reduced-motion`)

---

## Greenfield scaffold

When there is no existing project, create this structure:

```
project-name/
├── backend/
│   ├── main.py              # FastAPI app + mount point
│   ├── routers/
│   │   └── ws.py            # WebSocket router
│   ├── services/            # Business logic the WS handlers call
│   ├── models/              # Pydantic models for message types
│   └── requirements.txt     # fastapi, uvicorn[standard], websockets
├── frontend/
│   ├── ... (Svelte or React project via Vite)
│   └── vite.config.ts       # Proxy /ws to backend in dev
├── docker-compose.yml        # Optional: backend + frontend + redis
└── README.md
```

### Vite dev proxy (critical for development)

Without this, the frontend dev server can't reach the backend WebSocket. Configure in `vite.config.ts`:

```ts
export default defineConfig({
  server: {
    proxy: {
      '/ws': {
        target: 'http://localhost:8000',
        ws: true,  // This line is essential — enables WebSocket proxying
      },
      '/api': {
        target: 'http://localhost:8000',
      },
    },
  },
});
```

### requirements.txt

```
fastapi>=0.115
uvicorn[standard]>=0.30
websockets>=13.0
pydantic>=2.0
```

### Running in development

```bash
# Terminal 1 — backend
cd backend && uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Terminal 2 — frontend
cd frontend && npm run dev
```

---

## Common pitfalls

| Pitfall | Fix |
|---|---|
| WebSocket silently drops after 60s idle | Send a `{"type": "ping"}` from client every 30s; respond with `{"type": "pong"}` from server |
| Frontend reconnects in a tight loop after error | Use exponential backoff: 1s → 2s → 4s → 8s → 30s cap, with jitter |
| JSON parse errors crash the receive loop | Wrap `receive_json()` in try/except `json.JSONDecodeError`; log and continue |
| Stale data on reconnect | On connect, server sends a `{"type": "snapshot"}` with full current state, then deltas |
| Animation jank on rapid updates | Batch updates with `requestAnimationFrame` or throttle to 16ms; see `references/animations.md` |
| CORS blocks WebSocket upgrade in dev | WebSocket upgrade isn't subject to CORS, but the *initial HTTP handshake* is — add the dev origin to `allow_origins` |
| Memory leak from abandoned connections | Always clean up in the `except WebSocketDisconnect` block; add a periodic health-check sweep to the manager |

---

## Testing WebSocket endpoints

```python
# test_ws.py — use FastAPI's built-in test client
import pytest
from fastapi.testclient import TestClient
from backend.main import app

def test_websocket_echo():
    client = TestClient(app)
    with client.websocket_connect("/ws/test") as ws:
        ws.send_json({"type": "echo", "payload": {"text": "hello"}})
        data = ws.receive_json()
        assert data["type"] == "echo"
        assert data["payload"]["text"] == "hello"

def test_websocket_disconnect():
    client = TestClient(app)
    with client.websocket_connect("/ws/test") as ws:
        pass  # Connection closes cleanly — no server crash
```

---

## Security checklist

- **Authenticate WebSocket connections.** WebSockets don't carry cookies by default in all setups. Pass a token as a query param (`/ws?token=...`) or in the first message, and validate before accepting.
- **Rate-limit incoming messages.** A malicious client can flood the server. Track message count per connection per second and disconnect abusers.
- **Validate all incoming JSON** against Pydantic models before processing.
- **Use `wss://` in production.** Never allow unencrypted WebSocket in production — terminate TLS at the reverse proxy (nginx, Caddy, Traefik).
- **Limit max connections** per IP in the ConnectionManager or at the reverse-proxy layer.