"""Console API router — monitor dashboard and Hollywood demo endpoints."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from .demo_orchestrator import (
    cleanup_demo_queue,
    generate_scan_id,
    get_demo_queue,
    run_demo_replay,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/console", tags=["console"])


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class DemoStartRequest(BaseModel):
    domain: str


class DemoStartResponse(BaseModel):
    scan_id: str
    domain: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _briefs_dir(request: Request) -> Path:
    """Resolve the briefs directory from app state or default."""
    path = getattr(request.app.state, "briefs_dir", None)
    if path:
        return Path(path)
    return Path("data/output/briefs")


def _load_brief(briefs_path: Path, domain: str) -> dict | None:
    """Load a brief JSON file, return None if missing or invalid."""
    brief_file = briefs_path / f"{domain}.json"
    if not brief_file.is_file():
        return None
    try:
        with open(brief_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


# ---------------------------------------------------------------------------
# Monitor endpoints
# ---------------------------------------------------------------------------

@router.get("/status")
async def console_status(request: Request):
    """Operator dashboard data — queue depths, recent scans, cache stats."""
    redis_conn = getattr(request.app.state, "redis", None)

    queues = {"scan": 0, "enrichment": 0, "wpscan": 0}
    enrichment = {"completed": 0, "total": 0}
    cache_keys = 0

    if redis_conn:
        try:
            pipe = redis_conn.pipeline(transaction=False)
            pipe.llen("queue:scan")
            pipe.llen("queue:enrichment")
            pipe.llen("queue:wpscan")
            pipe.get("enrichment:completed")
            pipe.get("enrichment:total")
            pipe.dbsize()
            results = await asyncio.to_thread(pipe.execute)

            queues["scan"] = results[0] or 0
            queues["enrichment"] = results[1] or 0
            queues["wpscan"] = results[2] or 0
            enrichment["completed"] = int(results[3] or 0)
            enrichment["total"] = int(results[4] or 0)
            cache_keys = results[5] or 0
        except Exception:
            log.warning("console_redis_error", exc_info=True)

    # Recent scans from ResultStore
    recent_scans = []
    result_store = getattr(request.app.state, "result_store", None)
    if result_store:
        try:
            domains, _ = await asyncio.to_thread(
                result_store.list_domains, "prospect", limit=10,
            )
            recent_scans = domains
        except Exception:
            log.warning("console_results_error", exc_info=True)

    return {
        "queues": queues,
        "enrichment": enrichment,
        "recent_scans": recent_scans,
        "cache_keys": cache_keys,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Demo endpoints
# ---------------------------------------------------------------------------

@router.get("/briefs")
async def list_briefs(request: Request):
    """List available prospect briefs for the demo selector."""
    briefs_path = _briefs_dir(request)
    if not briefs_path.is_dir():
        return []

    briefs = []
    for f in sorted(briefs_path.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            briefs.append({
                "domain": data.get("domain", f.stem),
                "company_name": data.get("company_name", ""),
                "bucket": data.get("bucket", ""),
                "findings_count": len(data.get("findings", [])),
            })
        except (json.JSONDecodeError, OSError):
            continue
    return briefs


@router.post("/demo/start", response_model=DemoStartResponse)
async def demo_start(body: DemoStartRequest, request: Request):
    """Start a demo scan replay for a prospect domain.

    The replay task is NOT started here — it launches when the
    WebSocket connects, avoiding the race where events publish
    before the client is listening.
    """
    briefs_path = _briefs_dir(request)
    brief = _load_brief(briefs_path, body.domain)
    if brief is None:
        raise HTTPException(404, detail=f"No brief found for {body.domain}")

    scan_id = generate_scan_id()

    # Store the brief for the WebSocket handler to launch the replay
    pending = getattr(request.app.state, "_pending_demos", {})
    pending[scan_id] = brief
    request.app.state._pending_demos = pending

    return DemoStartResponse(scan_id=scan_id, domain=body.domain)


@router.websocket("/demo/ws/{scan_id}")
async def demo_websocket(websocket: WebSocket, scan_id: str):
    """Stream demo events to the client via WebSocket.

    The replay task launches here (not in demo_start) so events
    never publish before the client is listening.
    """
    await websocket.accept()

    # Launch the replay now that the client is connected
    pending = getattr(websocket.app.state, "_pending_demos", {})
    brief = pending.pop(scan_id, None)
    if brief is None:
        await websocket.close(code=1008, reason="Unknown scan_id")
        return

    redis_conn = getattr(websocket.app.state, "redis", None)
    task = asyncio.create_task(run_demo_replay(scan_id, brief, redis_conn))
    queue = get_demo_queue(scan_id)

    try:
        while True:
            try:
                data = await asyncio.wait_for(queue.get(), timeout=30.0)
            except asyncio.TimeoutError:
                break

            await websocket.send_text(data)

            try:
                parsed = json.loads(data)
                if parsed.get("type") == "complete":
                    await asyncio.sleep(0.2)
                    break
            except (json.JSONDecodeError, TypeError):
                pass

    except WebSocketDisconnect:
        log.info("demo_ws_disconnected", extra={"context": {"scan_id": scan_id}})
    except Exception:
        log.warning("demo_ws_error", extra={"context": {"scan_id": scan_id}}, exc_info=True)
    finally:
        task.cancel()
        cleanup_demo_queue(scan_id)
