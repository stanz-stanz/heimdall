"""FastAPI application factory with routes, middleware, and pub/sub listener."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

import redis
from fastapi import FastAPI, HTTPException, Query, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from src.interpreter.interpreter import InterpreterError, interpret_brief
from src.composer.telegram import compose_telegram

from .result_store import ResultStore

log = logging.getLogger(__name__)

# Path parameter validation — rejects path traversal attempts
_SAFE_NAME = re.compile(r"^[a-z0-9][a-z0-9.\-]{0,253}[a-z0-9]$")
_SAFE_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _validate_name(value: str, label: str) -> str:
    if not _SAFE_NAME.match(value):
        raise HTTPException(400, detail=f"Invalid {label} format")
    return value


# ---------------------------------------------------------------------------
# Request logging middleware
# ---------------------------------------------------------------------------

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        t0 = time.monotonic()
        try:
            response: Response = await call_next(request)
        except Exception:
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            log.error(
                "http_error",
                extra={"context": {
                    "method": request.method,
                    "path": request.url.path,
                    "duration_ms": elapsed_ms,
                }},
                exc_info=True,
            )
            raise
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        log.info(
            "http_request",
            extra={"context": {
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": elapsed_ms,
            }},
        )
        return response


# ---------------------------------------------------------------------------
# Pub/sub listener — interpret + compose on scan-complete
# ---------------------------------------------------------------------------

async def _listen_scan_complete(
    redis_conn: redis.Redis,
    result_store: ResultStore,
    messages_dir: str,
) -> None:
    pubsub = redis_conn.pubsub()
    await asyncio.to_thread(pubsub.subscribe, "scan-complete")
    log.info("pubsub_subscribed", extra={"context": {"channel": "scan-complete"}})
    try:
        while True:
            msg = await asyncio.to_thread(
                pubsub.get_message, ignore_subscribe_messages=True, timeout=1.0,
            )
            if msg and msg["type"] == "message":
                try:
                    payload = json.loads(msg["data"])
                    log.info("scan_complete_event", extra={"context": {
                        "job_id": payload.get("job_id"),
                        "domain": payload.get("domain"),
                        "client_id": payload.get("client_id"),
                        "status": payload.get("status"),
                    }})
                    # Interpret + compose in a thread to avoid blocking
                    await asyncio.to_thread(
                        _handle_scan_complete, payload, result_store, messages_dir,
                    )
                except (json.JSONDecodeError, TypeError) as exc:
                    log.warning("scan_complete_parse_error", extra={"context": {"error": str(exc)}})
            await asyncio.sleep(0.1)
    except asyncio.CancelledError:
        pubsub.unsubscribe("scan-complete")
        pubsub.close()
        log.info("pubsub_unsubscribed")
    except Exception:
        log.exception("pubsub_error")


def _handle_scan_complete(
    payload: dict,
    result_store: ResultStore,
    messages_dir: str,
) -> None:
    """Interpret findings and compose a Telegram message for a completed scan."""
    client_id = payload.get("client_id", "")
    domain = payload.get("domain", "")

    # Validate path components from untrusted pub/sub data
    if not _SAFE_NAME.match(client_id) or not _SAFE_NAME.match(domain):
        log.warning("interpret_invalid_path", extra={"context": {
            "client_id": client_id, "domain": domain,
            "reason": "Invalid characters in client_id or domain from pub/sub",
        }})
        return

    if payload.get("status") != "completed":
        return

    # Load the scan result
    result = result_store.get_latest(client_id, domain)
    if not result:
        log.warning("interpret_no_result", extra={"context": {
            "client_id": client_id, "domain": domain,
        }})
        return

    brief = result.get("brief")
    if not brief:
        log.warning("interpret_no_brief", extra={"context": {
            "client_id": client_id, "domain": domain,
        }})
        return

    # Interpret
    try:
        interpreted = interpret_brief(brief)
    except InterpreterError as exc:
        log.error("interpret_failed", extra={"context": {
            "client_id": client_id, "domain": domain, "error": str(exc),
        }})
        return

    # Compose for Telegram
    messages = compose_telegram(interpreted)

    # Write to disk for Sprint 4.1 (Telegram delivery)
    out_dir = Path(messages_dir) / client_id / domain
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "message.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "domain": domain,
            "client_id": client_id,
            "interpreted": interpreted,
            "telegram_messages": messages,
        }, f, indent=2, ensure_ascii=False)

    log.info("message_composed", extra={"context": {
        "client_id": client_id,
        "domain": domain,
        "message_count": len(messages),
        "message_chars": sum(len(m) for m in messages),
        "path": str(out_path),
    }})


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app(redis_url: str, results_dir: str, messages_dir: str = "/data/messages") -> FastAPI:
    """Build and return the FastAPI application."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Startup
        app.state.redis = None
        app.state.pubsub_task = None
        try:
            redis_conn = redis.Redis.from_url(redis_url, decode_responses=True)
            redis_conn.ping()  # Sync call OK — runs once at startup only
            app.state.redis = redis_conn
            app.state.pubsub_task = asyncio.create_task(
                _listen_scan_complete(redis_conn, app.state.result_store, messages_dir),
            )
        except Exception:
            log.warning("redis_unavailable", extra={"context": {"url": redis_url}})

        log.info("api_started", extra={"context": {"results_dir": results_dir}})
        yield
        # Shutdown
        if app.state.pubsub_task:
            app.state.pubsub_task.cancel()
            try:
                await app.state.pubsub_task
            except asyncio.CancelledError:
                pass
        if app.state.redis:
            app.state.redis.close()
        log.info("api_stopped")

    app = FastAPI(
        title="Heimdall API",
        version="3.0.0",
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.results_dir = results_dir
    app.state.result_store = ResultStore(results_dir)

    app.add_middleware(RequestLoggingMiddleware)

    # -------------------------------------------------------------------
    # Routes
    # -------------------------------------------------------------------

    @app.get("/health")
    async def health(request: Request):
        redis_status = "disconnected"
        redis_conn = getattr(request.app.state, "redis", None)
        if redis_conn:
            try:
                await asyncio.to_thread(redis_conn.ping)
                redis_status = "connected"
            except Exception:
                redis_status = "disconnected"

        results_status = "available" if Path(results_dir).is_dir() else "missing"

        return {
            "status": "ok",
            "redis": redis_status,
            "results_dir": results_status,
        }

    @app.get("/results/{client_id}")
    async def list_domains(
        client_id: str,
        request: Request,
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
    ):
        _validate_name(client_id, "client_id")
        store: ResultStore = request.app.state.result_store
        domains, total = store.list_domains(client_id, limit=limit, offset=offset)
        return {
            "client_id": client_id,
            "domains": domains,
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    @app.get("/results/{client_id}/{domain}/dates")
    async def list_dates(client_id: str, domain: str, request: Request):
        _validate_name(client_id, "client_id")
        _validate_name(domain, "domain")
        store: ResultStore = request.app.state.result_store
        dates = store.list_dates(client_id, domain)
        if not dates:
            raise HTTPException(404, detail=f"No results found for {domain}")
        return {"domain": domain, "dates": dates}

    @app.get("/results/{client_id}/{domain}")
    async def get_result(
        client_id: str,
        domain: str,
        request: Request,
        date: Optional[str] = Query(default=None),
        include: Optional[str] = Query(default=None),
    ):
        _validate_name(client_id, "client_id")
        _validate_name(domain, "domain")
        if date and not _SAFE_DATE.match(date):
            raise HTTPException(400, detail="Invalid date format (expected YYYY-MM-DD)")

        store: ResultStore = request.app.state.result_store
        if date:
            result = store.get_by_date(client_id, domain, date)
        else:
            result = store.get_latest(client_id, domain)

        if result is None:
            raise HTTPException(404, detail=f"No results found for {domain}")

        if include != "full":
            result.pop("scan_result", None)

        return result

    return app
