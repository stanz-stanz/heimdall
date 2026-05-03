---
paths:
  - "requirements*.txt"
  - "src/api/main.py"
  - "src/**/uvicorn*"
  - "src/**/*websocket*"
---

# Python runtime rules

## Uvicorn + WebSocket dependency

Uvicorn silently rejects WebSocket connections if `websockets` (or `wsproto`) is not installed — returns 404 with no obvious error. The error appears only in debug-level logs.

When adding any FastAPI WebSocket endpoint:
1. Verify `websockets` is in `requirements*.txt`.
2. Verify it's installed locally (`pip show websockets`) before testing.

**Why:** Spent debugging time on a "race condition" that turned out to be the missing dependency.
