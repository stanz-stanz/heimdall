# Console Logs View — Design Spec

## Context

The operator console has no visibility into container logs. Every debugging session requires SSH into the Pi and running `docker compose logs`. This view brings container logs into the console with filtering, eliminating the need for CLI log inspection during normal operations.

## Scope

New "Logs" sidebar item under Data (between Clients and Settings). Shows loguru logs from all containers (API, Worker x3, Delivery, Scheduler, CT Collector) with filtering by source, level, timeframe, and text search.

This is a **view layer** on top of existing container logging — not a replacement. Container stderr logging is unchanged. No log retention policy changes.

## Architecture

### Log flow

```
Container (loguru) → background thread → Redis pub/sub "console:logs"
                                              ↓
                              API process subscribes
                                              ↓
                              In-memory ring buffer (5,000 entries)
                                      ↓              ↓
                            REST endpoint        WebSocket push
                           (initial load)        (live stream)
                                      ↓              ↓
                                   Browser (5,000 entry cap)
```

### Redis sink (`src/logging/redis_sink.py`)

Shared module imported by each container entrypoint.

- Background daemon thread with a `queue.Queue(maxsize=1000)`
- Loguru sink function pushes serialized entries to the queue (non-blocking, drops if full)
- Daemon thread drains the queue and publishes to Redis `console:logs` channel
- Redis client: `socket_timeout=0.5`, `socket_connect_timeout=0.5`
- All Redis errors caught silently (print to stderr, never to loguru — avoids recursion)
- If Redis is down, entries are dropped — container logging to stderr is unaffected

Entry format (selected fields only, matching existing `_json_formatter` pattern):
```json
{
  "ts": 1712404800.123,
  "level": "ERROR",
  "source": "worker-1",
  "module": "src.worker.scan_job",
  "message": "http_error path=/console/campaigns duration_ms=5",
  "ctx": { "domain": "farylochan.dk", "job_id": "scan-001" }
}
```

Source identification: `socket.gethostname()` at import time.

### API ring buffer

- `collections.deque(maxlen=5000)` on `app.state`
- The existing `_listen_pubsub` coroutine in `console.py` subscribes to `console:logs` alongside the existing channels
- Appends happen on the event loop thread (poll in `asyncio.to_thread`, append in the coroutine) — avoids concurrent mutation during iteration

### REST endpoint

`GET /console/logs` with query parameters:
- `source` — filter by container name (optional, comma-separated)
- `level` — minimum level: DEBUG, INFO, WARNING, ERROR (optional, default INFO)
- `since` — Unix timestamp, entries after this time (optional)
- `q` — text search in message field (optional)
- `limit` — max entries returned (optional, default 200, max 5000)

Returns: `{ entries: [...], total: N }` where total is the ring buffer size before filtering.

### WebSocket

The existing `/console/ws` endpoint adds `console:logs` to its pub/sub subscription list. Log entries forwarded as:
```json
{ "type": "log", "payload": { "ts": ..., "level": ..., "source": ..., "module": ..., "message": ..., "ctx": {...} } }
```

**Batching:** During high-volume periods, buffer log entries and flush every 200ms instead of one message per log line. Prevents browser jank during pipeline runs.

### Container changes

Each container's entrypoint adds the Redis sink **after** `setup_logging()` (so `logger.remove()` doesn't wipe it):

```python
setup_logging(level="INFO", fmt="json")
from src.logging.redis_sink import add_redis_sink
add_redis_sink(redis_url=os.environ.get("REDIS_URL", ""))
```

Containers to modify:
- `src/api/main.py`
- `src/worker/main.py`
- `src/delivery/__main__.py`
- `src/scheduler/main.py`
- `src/ct_collector/__main__.py`

## Frontend

### Sidebar

New nav item "Logs" under Data section, between Clients and Settings. Icon: &#9776; (hamburger/list). No badge count.

### View layout

```
┌─────────────────────────────────────────────────────┐
│ Logs (header)                                       │
│ [Source chips] [Level chips] [Timeframe] [Search]   │
├─────────────────────────────────────────────────────┤
│ 13:45:02 api     ERROR  http_error path=/console/.. │
│ 13:45:01 worker  INFO   scan_complete domain=far..  │
│ 13:45:00 worker  INFO   scan_start domain=hopba..   │
│ 13:44:58 deliver WARNING redis_reconnect attempt=2  │
│ ...                                                 │
└─────────────────────────────────────────────────────┘
```

### Filters

- **Source chips:** All, API, Worker, Delivery, Scheduler, CT (multi-select, default All)
- **Level chips:** ERROR, WARNING, INFO, DEBUG (minimum level, default INFO — shows INFO and above)
- **Timeframe chips:** All, 1m, 5m, 10m, 30m (filters displayed entries by timestamp relative to now)
- **Text search:** Free text input, filters by message content (client-side filtering on the loaded entries)

All filtering is client-side on the 5,000 entries already in the browser. No server round-trips on filter change.

### Row format

Single-line rows in a monospace font:
```
HH:MM:SS  source   LEVEL  message [domain=X job_id=Y]
```

- Timestamp: `HH:MM:SS` (time only — date is implied by timeframe filter)
- Source: left-aligned, truncated to 10 chars, color-coded per container
- Level: color-coded (ERROR=red, WARNING=orange, INFO=dim text, DEBUG=muted)
- Message: the loguru message with key context fields (`domain`, `job_id`, `error`) appended inline
- No expand/collapse — everything visible at a glance

### Behavior

- On mount: `GET /console/logs?limit=200` for initial entries
- WebSocket streams new entries, prepended to the list
- Browser caps at 5,000 entries (drops oldest)
- Auto-scroll to newest entry; pauses when user scrolls up; "Jump to bottom" button appears
- Source color coding: API=blue, Worker=green, Delivery=gold, Scheduler=orange, CT=muted

## Files

### New
- `src/logging/__init__.py`
- `src/logging/redis_sink.py` — shared Redis log sink with background thread
- `src/api/frontend/src/views/Logs.svelte` — view component

### Modified
- `src/api/console.py` — add `GET /console/logs`, add `console:logs` to WS pub/sub subscription
- `src/api/app.py` — add ring buffer to `app.state`, subscribe to `console:logs` in lifespan
- `src/api/frontend/src/App.svelte` — import and render Logs view
- `src/api/frontend/src/components/Sidebar.svelte` — add Logs nav item
- `src/api/frontend/src/lib/api.js` — add `fetchLogs()` helper
- `src/api/main.py` — add Redis sink after setup_logging
- `src/worker/main.py` — add Redis sink after setup_logging
- `src/delivery/__main__.py` — add Redis sink after setup_logging
- `src/scheduler/main.py` — add Redis sink after setup_logging
- `src/ct_collector/__main__.py` — add Redis sink after setup_logging
