"""Console API router — monitor dashboard, operator console, and Hollywood demo endpoints."""

from __future__ import annotations

import asyncio
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger
from fastapi import APIRouter, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

import sqlite3

from .demo_orchestrator import (
    cleanup_demo_queue,
    generate_scan_id,
    get_demo_queue,
    run_demo_live,
    run_demo_replay,
)

router = APIRouter(prefix="/console", tags=["console"])


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class DemoStartRequest(BaseModel):
    domain: str
    mode: str = "replay"  # "replay" or "live"


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

    queues = {"scan": 0, "enrichment": 0}
    enrichment = {"completed": 0, "total": 0}
    cache_keys = 0

    if redis_conn:
        try:
            pipe = redis_conn.pipeline(transaction=False)
            pipe.llen("queue:scan")
            pipe.llen("queue:enrichment")
            pipe.get("enrichment:completed")
            pipe.get("enrichment:total")
            pipe.dbsize()
            results = await asyncio.to_thread(pipe.execute)

            queues["scan"] = results[0] or 0
            queues["enrichment"] = results[1] or 0
            enrichment["completed"] = int(results[2] or 0)
            enrichment["total"] = int(results[3] or 0)
            cache_keys = results[4] or 0
        except Exception:
            logger.opt(exception=True).warning("console_redis_error")

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
            logger.opt(exception=True).warning("console_results_error")

    return {
        "queues": queues,
        "enrichment": enrichment,
        "recent_scans": recent_scans,
        "cache_keys": cache_keys,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Operator console endpoints
# ---------------------------------------------------------------------------

# Whitelists for input validation
_VALID_SETTINGS = frozenset(("filters", "interpreter", "delivery"))
_VALID_COMMANDS = frozenset(("run-pipeline", "interpret", "send"))


@router.get("/dashboard")
async def console_dashboard(request: Request):
    """Dashboard stats — prospect/brief/client/critical counts, queues, activity."""
    db_path = getattr(request.app.state, "db_path", "data/clients/clients.db")
    redis_conn = getattr(request.app.state, "redis", None)

    def _query():
        conn = sqlite3.connect(db_path, timeout=5)
        conn.row_factory = sqlite3.Row
        try:
            prospects = conn.execute("SELECT COUNT(*) FROM prospects").fetchone()[0]
            briefs = conn.execute("SELECT COUNT(*) FROM v_current_briefs").fetchone()[0]
            clients = conn.execute(
                "SELECT COUNT(*) FROM clients WHERE status IN ('active','onboarding')"
            ).fetchone()[0]
            critical = conn.execute(
                "SELECT COALESCE(SUM(critical_count),0) FROM v_current_briefs"
            ).fetchone()[0]

            # Recent activity from pipeline_runs + delivery_log
            activity: list[dict] = []
            for row in conn.execute(
                "SELECT 'pipeline' AS source, run_id AS id, status, run_date AS ts,"
                "       domain_count, finding_count"
                " FROM pipeline_runs ORDER BY completed_at DESC LIMIT 5"
            ).fetchall():
                activity.append(dict(row))
            for row in conn.execute(
                "SELECT 'delivery' AS source, id, domain, status, created_at AS ts"
                " FROM delivery_log ORDER BY created_at DESC LIMIT 5"
            ).fetchall():
                activity.append(dict(row))
            activity.sort(key=lambda x: x.get("ts", ""), reverse=True)

            return {
                "prospects": prospects,
                "briefs": briefs,
                "clients": clients,
                "critical": critical,
                "activity": activity[:10],
            }
        finally:
            conn.close()

    data = await asyncio.to_thread(_query)

    # Queue depths from Redis
    queues = {"scan": 0, "enrichment": 0}
    if redis_conn:
        try:
            pipe = redis_conn.pipeline(transaction=False)
            pipe.llen("queue:scan")
            pipe.llen("queue:enrichment")
            results = await asyncio.to_thread(pipe.execute)
            queues["scan"] = results[0] or 0
            queues["enrichment"] = results[1] or 0
        except Exception:
            pass

    data["queues"] = queues
    data["timestamp"] = datetime.now(timezone.utc).isoformat()
    return data


@router.get("/pipeline/last")
async def console_pipeline_last(request: Request):
    """Last completed pipeline run from v_latest_run."""
    db_path = getattr(request.app.state, "db_path", "data/clients/clients.db")

    def _query():
        conn = sqlite3.connect(db_path, timeout=5)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute("SELECT * FROM v_latest_run").fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    result = await asyncio.to_thread(_query)
    if result is None:
        return {"status": "no_runs"}
    return result


@router.get("/campaigns")
async def console_campaigns(request: Request):
    """Campaign list with status counts from v_campaign_summary."""
    db_path = getattr(request.app.state, "db_path", "data/clients/clients.db")

    def _query():
        conn = sqlite3.connect(db_path, timeout=5)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute("SELECT * FROM v_campaign_summary").fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    return await asyncio.to_thread(_query)


@router.get("/campaigns/{campaign}/prospects")
async def console_campaign_prospects(
    campaign: str,
    request: Request,
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """Prospects filtered by campaign and optional outreach status."""
    db_path = getattr(request.app.state, "db_path", "data/clients/clients.db")

    def _query():
        conn = sqlite3.connect(db_path, timeout=5)
        conn.row_factory = sqlite3.Row
        try:
            sql = (
                "SELECT domain, company_name, campaign, bucket, finding_count,"
                "       critical_count, high_count, outreach_status, created_at"
                " FROM prospects WHERE campaign = ?"
            )
            params: list = [campaign]
            if status is not None:
                sql += " AND outreach_status = ?"
                params.append(status)
            sql += " ORDER BY critical_count DESC, finding_count DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    return await asyncio.to_thread(_query)


@router.get("/clients/list")
async def console_clients_list(request: Request):
    """Onboarded clients with domain, latest scan, open findings, last delivery."""
    db_path = getattr(request.app.state, "db_path", "data/clients/clients.db")

    def _query():
        conn = sqlite3.connect(db_path, timeout=5)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT c.cvr, c.company_name, c.plan, c.status,"
                "       cd.domain,"
                "       (SELECT MAX(scan_date) FROM brief_snapshots bs"
                "            WHERE bs.cvr = c.cvr) AS last_scan,"
                "       (SELECT COUNT(*) FROM finding_occurrences fo"
                "            WHERE fo.cvr = c.cvr AND fo.status NOT IN ('resolved'))"
                "            AS open_findings,"
                "       (SELECT MAX(created_at) FROM delivery_log dl"
                "            WHERE dl.cvr = c.cvr) AS last_delivery"
                " FROM clients c"
                " LEFT JOIN client_domains cd ON c.cvr = cd.cvr AND cd.is_primary = 1"
                " WHERE c.status IN ('active', 'onboarding')"
                " ORDER BY c.company_name"
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    return await asyncio.to_thread(_query)


@router.get("/settings")
async def console_settings():
    """Read all 3 config files (filters, interpreter, delivery)."""
    config_dir = Path("config")
    result = {}
    for name in ("filters", "interpreter", "delivery"):
        path = config_dir / f"{name}.json"
        if path.is_file():
            result[name] = json.loads(path.read_text(encoding="utf-8"))
        else:
            result[name] = {}
    return result


@router.put("/settings/{name}")
async def console_settings_update(name: str, request: Request):
    """Write a config file atomically. Whitelist: filters, interpreter, delivery."""
    if name not in _VALID_SETTINGS:
        raise HTTPException(400, detail=f"Invalid config name: {name!r}")

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, detail="Request body must be valid JSON")

    if not isinstance(body, dict):
        raise HTTPException(400, detail="Config must be a JSON object")

    config_path = Path("config") / f"{name}.json"

    # Merge with existing config to avoid losing keys the UI doesn't manage
    existing = {}
    if config_path.is_file():
        try:
            existing = json.loads(config_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    merged = {**existing, **body}
    content = json.dumps(merged, indent=2, ensure_ascii=False) + "\n"

    # Atomic write: write to temp file in same dir, then rename
    config_path.parent.mkdir(parents=True, exist_ok=True)
    fd = tempfile.NamedTemporaryFile(
        mode="w",
        dir=str(config_path.parent),
        suffix=".tmp",
        delete=False,
        encoding="utf-8",
    )
    try:
        fd.write(content)
        fd.flush()
        fd.close()
        Path(fd.name).rename(config_path)
    except Exception:
        # Clean up temp file on failure
        try:
            Path(fd.name).unlink(missing_ok=True)
        except Exception:
            pass
        raise

    logger.info("config_saved name={}", name)
    return {"status": "saved", "name": name}


@router.post("/commands/{command}")
async def console_command(command: str, request: Request):
    """Push an operator command to Redis queue:operator-commands."""
    if command not in _VALID_COMMANDS:
        raise HTTPException(400, detail=f"Invalid command: {command!r}")

    redis_conn = getattr(request.app.state, "redis", None)
    if redis_conn is None:
        raise HTTPException(503, detail="Redis not available")

    try:
        body = await request.json()
    except Exception:
        body = {}

    cmd_json = json.dumps({
        "command": command,
        "payload": body,
        "ts": datetime.now(timezone.utc).isoformat(),
    })

    await asyncio.to_thread(redis_conn.lpush, "queue:operator-commands", cmd_json)
    logger.info("command_queued command={}", command)
    return {"status": "queued", "command": command}


_LEVEL_ORDER = {"DEBUG": 0, "INFO": 1, "WARNING": 2, "ERROR": 3, "CRITICAL": 4}


@router.get("/logs")
async def console_logs(
    request: Request,
    source: str | None = Query(default=None),
    level: str | None = Query(default=None),
    since: float | None = Query(default=None),
    q: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=5000),
):
    """Return filtered log entries from the in-memory ring buffer."""
    log_buffer = getattr(request.app.state, "log_buffer", None)
    if log_buffer is None:
        return {"entries": [], "total": 0}

    min_level = _LEVEL_ORDER.get((level or "DEBUG").upper(), 0)
    sources = set(s.strip() for s in source.split(",")) if source else None
    q_lower = q.lower() if q else None

    entries = []
    for entry in reversed(log_buffer):  # newest first
        if sources and entry.get("source", "") not in sources:
            continue
        if _LEVEL_ORDER.get(entry.get("level", ""), 0) < min_level:
            continue
        if since and entry.get("ts", 0) < since:
            continue
        if q_lower and q_lower not in entry.get("message", "").lower():
            continue
        entries.append(entry)
        if len(entries) >= limit:
            break

    return {"entries": entries, "total": len(log_buffer)}


@router.websocket("/ws")
async def console_ws(websocket: WebSocket):
    """WebSocket for live console updates — queue polling + Redis pub/sub forwarding."""
    await websocket.accept()
    redis_conn = getattr(websocket.app.state, "redis", None)

    async def _push_queue_status():
        """Poll queue depths every 5s and push to client."""
        while True:
            try:
                if redis_conn:
                    pipe = redis_conn.pipeline(transaction=False)
                    pipe.llen("queue:scan")
                    pipe.llen("queue:enrichment")
                    results = await asyncio.to_thread(pipe.execute)
                    await websocket.send_json({
                        "type": "queue_status",
                        "payload": {"scan": results[0] or 0, "enrichment": results[1] or 0},
                        "ts": datetime.now(timezone.utc).timestamp(),
                    })
            except Exception:
                pass
            await asyncio.sleep(5)

    async def _listen_pubsub():
        """Forward Redis pub/sub messages to WebSocket."""
        if not redis_conn:
            return
        channels = ["console:pipeline-progress", "console:activity", "console:command-results"]
        pubsub = redis_conn.pubsub()
        try:
            await asyncio.to_thread(pubsub.subscribe, *channels)
            while True:
                msg = await asyncio.to_thread(
                    pubsub.get_message, ignore_subscribe_messages=True, timeout=1.0,
                )
                if msg and msg["type"] == "message":
                    try:
                        data = json.loads(msg["data"])
                        await websocket.send_json(data)
                    except (json.JSONDecodeError, TypeError):
                        pass
                await asyncio.sleep(0.1)
        except Exception:
            pass
        finally:
            try:
                pubsub.unsubscribe(*channels)
                pubsub.close()
            except Exception:
                pass

    # Log forwarding — subscribe to console:logs, batch every 200ms
    _log_batch = []

    async def _forward_logs():
        """Subscribe to console:logs and batch-forward to WebSocket."""
        if not redis_conn:
            return
        pubsub_logs = redis_conn.pubsub()
        try:
            await asyncio.to_thread(pubsub_logs.subscribe, "console:logs")
            while True:
                msg = await asyncio.to_thread(
                    pubsub_logs.get_message, ignore_subscribe_messages=True, timeout=0.15,
                )
                if msg and msg["type"] == "message":
                    try:
                        _log_batch.append(json.loads(msg["data"]))
                    except (json.JSONDecodeError, TypeError):
                        pass

                # Flush batch every ~200ms
                if _log_batch:
                    try:
                        await websocket.send_json({
                            "type": "log_batch",
                            "payload": {"entries": _log_batch[:]},
                        })
                    except Exception:
                        pass
                    _log_batch.clear()

                await asyncio.sleep(0.05)
        except Exception:
            pass
        finally:
            try:
                pubsub_logs.unsubscribe("console:logs")
                pubsub_logs.close()
            except Exception:
                pass

    push_task = asyncio.create_task(_push_queue_status())
    pubsub_task = asyncio.create_task(_listen_pubsub())
    log_task = asyncio.create_task(_forward_logs())

    try:
        while True:
            data = await websocket.receive_json()
            # Handle client messages
            if data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
            elif data.get("type") == "command" and redis_conn:
                cmd = data.get("command", "")
                if cmd in _VALID_COMMANDS:
                    cmd_json = json.dumps({
                        "command": cmd,
                        "payload": data.get("payload", {}),
                        "ts": datetime.now(timezone.utc).isoformat(),
                    })
                    await asyncio.to_thread(
                        redis_conn.lpush, "queue:operator-commands", cmd_json,
                    )
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.opt(exception=True).warning("console_ws_error")
    finally:
        push_task.cancel()
        pubsub_task.cancel()
        log_task.cancel()


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
    if body.mode not in ("replay", "live"):
        raise HTTPException(400, detail="mode must be 'replay' or 'live'")

    briefs_path = _briefs_dir(request)
    brief = _load_brief(briefs_path, body.domain)
    if brief is None:
        raise HTTPException(404, detail=f"No brief found for {body.domain}")

    scan_id = generate_scan_id()

    # Store the brief + mode for the WebSocket handler
    pending = getattr(request.app.state, "_pending_demos", {})
    pending[scan_id] = (brief, body.mode)
    request.app.state._pending_demos = pending

    return DemoStartResponse(scan_id=scan_id, domain=body.domain)


@router.websocket("/demo/ws/{scan_id}")
async def demo_websocket(websocket: WebSocket, scan_id: str):
    """Stream demo events to the client via WebSocket.

    The replay task launches here (not in demo_start) so events
    never publish before the client is listening.
    """
    await websocket.accept()

    # Launch the demo now that the client is connected
    pending = getattr(websocket.app.state, "_pending_demos", {})
    entry = pending.pop(scan_id, None)
    if entry is None:
        await websocket.close(code=1008, reason="Unknown scan_id")
        return

    brief, mode = entry
    redis_conn = getattr(websocket.app.state, "redis", None)

    if mode == "live":
        task = asyncio.create_task(run_demo_live(scan_id, brief, redis_conn))
    else:
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
        logger.bind(context={"scan_id": scan_id}).info("demo_ws_disconnected")
    except Exception:
        logger.bind(context={"scan_id": scan_id}).opt(exception=True).warning("demo_ws_error")
    finally:
        task.cancel()
        cleanup_demo_queue(scan_id)
