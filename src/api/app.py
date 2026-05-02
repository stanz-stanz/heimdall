"""FastAPI application factory with routes, middleware, and pub/sub listener."""

from __future__ import annotations

import asyncio
import collections
import json
import os
import re
import time
from contextlib import asynccontextmanager
from pathlib import Path

import redis
from fastapi import FastAPI, HTTPException, Query, Request
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from starlette.staticfiles import StaticFiles

from src.client_memory import (
    AtomicFileStore,
    ClientHistory,
    ClientProfile,
    DeltaDetector,
    RemediationTracker,
)
from src.api.auth.middleware import SessionAuthMiddleware
from src.api.auth.request_id import RequestIdMiddleware
from src.composer.telegram import compose_telegram
from src.db.console_connection import (
    DEFAULT_CONSOLE_DB_PATH,
    init_db_console,
)
from src.interpreter.interpreter import InterpreterError, interpret_brief

from .console import router as console_router
from .result_store import ResultStore
from .routers.auth import router as auth_router
from .signup import router as signup_router

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
        # Stage A.5 §4.3.4: read request_id off state populated by
        # RequestIdMiddleware (mounted outermost, so always present
        # for HTTP scopes). Defensive ``getattr`` keeps the logger
        # bind harmless on the unit-test path where this middleware
        # is exercised in isolation.
        request_id = getattr(request.state, "request_id", None)
        try:
            response: Response = await call_next(request)
        except Exception:
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            logger.bind(context={
                "method": request.method,
                "path": request.url.path,
                "duration_ms": elapsed_ms,
                "request_id": request_id,
            }).opt(exception=True).error("http_error")
            raise
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        logger.bind(context={
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "duration_ms": elapsed_ms,
            "request_id": request_id,
        }).info("http_request")
        return response


# ---------------------------------------------------------------------------
# Pub/sub listener — console:logs → in-memory ring buffer
# ---------------------------------------------------------------------------

_SELF_NOISE = frozenset(("http_request", "http_error", "log_listener_subscribed", "log_listener_reconnecting"))


async def _listen_console_logs(
    redis_conn: redis.Redis,
    log_buffer: collections.deque,
) -> None:
    """Subscribe to console:logs and append entries to the ring buffer.

    Selectively filters the API's own noise (HTTP middleware, health checks)
    while passing through operational logs (interpret, scan events, pubsub).
    """
    _own_source = os.environ.get("HEIMDALL_SOURCE", __import__("socket").gethostname())
    reconnect_count = 0

    while True:
        try:
            pubsub = redis_conn.pubsub()
            await asyncio.to_thread(pubsub.subscribe, "console:logs")
            logger.bind(context={"channel": "console:logs"}).info("log_listener_subscribed")
            reconnect_count = 0

            while True:
                msg = await asyncio.to_thread(
                    pubsub.get_message, ignore_subscribe_messages=True, timeout=1.0,
                )
                if msg and msg["type"] == "message":
                    try:
                        entry = json.loads(msg["data"])
                        # Drop API's own noise (health checks, request logs)
                        # but pass through operational logs (interpret, scan, pubsub)
                        if entry.get("source") == _own_source and entry.get("message", "") in _SELF_NOISE:
                            continue
                        log_buffer.append(entry)
                    except (json.JSONDecodeError, TypeError):
                        pass
                await asyncio.sleep(0.05)

        except asyncio.CancelledError:
            try:
                pubsub.unsubscribe("console:logs")
                pubsub.close()
            except Exception:
                pass
            return

        except Exception:
            reconnect_count += 1
            wait = _PUBSUB_RECONNECT_BACKOFF[min(reconnect_count - 1, len(_PUBSUB_RECONNECT_BACKOFF) - 1)]
            logger.bind(context={"reconnect_count": reconnect_count}).opt(exception=True).warning(
                "log_listener_reconnecting"
            )
            try:
                pubsub.close()
            except Exception:
                pass
            await asyncio.sleep(wait)


# ---------------------------------------------------------------------------
# Pub/sub listener — interpret + compose on client-scan-complete
# ---------------------------------------------------------------------------

_PUBSUB_RECONNECT_BACKOFF = [1, 2, 5, 10, 30]  # seconds


async def _listen_scan_complete(
    redis_conn: redis.Redis,
    result_store: ResultStore,
    messages_dir: str,
    client_history: ClientHistory = None,
    client_profile: ClientProfile = None,
) -> None:
    """Subscribe to client-scan-complete and process events. Auto-reconnects on failure."""
    reconnect_count = 0

    while True:
        try:
            pubsub = redis_conn.pubsub()
            await asyncio.to_thread(pubsub.subscribe, "client-scan-complete")
            logger.bind(context={
                "channel": "client-scan-complete", "reconnect_count": reconnect_count,
            }).info("pubsub_subscribed")
            reconnect_count = 0  # reset on successful subscribe

            while True:
                msg = await asyncio.to_thread(
                    pubsub.get_message, ignore_subscribe_messages=True, timeout=1.0,
                )
                if msg and msg["type"] == "message":
                    try:
                        payload = json.loads(msg["data"])
                        logger.bind(context={
                            "job_id": payload.get("job_id"),
                            "domain": payload.get("domain"),
                            "client_id": payload.get("client_id"),
                            "status": payload.get("status"),
                        }).info("scan_complete_event")
                        await asyncio.to_thread(
                            _handle_scan_complete, payload, result_store, messages_dir,
                            client_history, client_profile,
                        )
                    except (json.JSONDecodeError, TypeError) as exc:
                        logger.bind(context={"error": str(exc)}).warning("scan_complete_parse_error")
                await asyncio.sleep(0.1)

        except asyncio.CancelledError:
            try:
                pubsub.unsubscribe("client-scan-complete")
                pubsub.close()
            except Exception:
                pass
            logger.info("pubsub_unsubscribed")
            return  # clean shutdown — do not reconnect

        except Exception:
            reconnect_count += 1
            wait = _PUBSUB_RECONNECT_BACKOFF[min(reconnect_count - 1, len(_PUBSUB_RECONNECT_BACKOFF) - 1)]
            logger.bind(context={
                "reconnect_count": reconnect_count, "wait_seconds": wait,
            }).opt(exception=True).warning("pubsub_reconnecting")
            try:
                pubsub.close()
            except Exception:
                pass
            await asyncio.sleep(wait)


def _handle_scan_complete(
    payload: dict,
    result_store: ResultStore,
    messages_dir: str,
    client_history: ClientHistory = None,
    client_profile: ClientProfile = None,
) -> None:
    """Interpret findings and compose a Telegram message for a completed scan."""
    client_id = payload.get("client_id", "")
    domain = payload.get("domain", "")

    # Validate path components from untrusted pub/sub data
    if not _SAFE_NAME.match(client_id) or not _SAFE_NAME.match(domain):
        logger.bind(context={
            "client_id": client_id, "domain": domain,
            "reason": "Invalid characters in client_id or domain from pub/sub",
        }).warning("interpret_invalid_path")
        return

    if payload.get("status") != "completed":
        return

    # Load the scan result
    result = result_store.get_latest(client_id, domain)
    if not result:
        logger.bind(context={
            "client_id": client_id, "domain": domain,
        }).warning("interpret_no_result")
        return

    brief = result.get("brief")
    if not brief:
        logger.bind(context={
            "client_id": client_id, "domain": domain,
        }).warning("interpret_no_brief")
        return

    # Delta detection (if client memory available)
    delta_context = None
    if client_history and client_id != "prospect":
        try:
            delta_result = client_history.record_scan(client_id, brief)
            delta_context = {
                "new": [{"description": f.get("description", ""), "severity": f.get("severity", "")} for f in delta_result.new],
                "recurring": [{"description": f.get("description", ""), "severity": f.get("severity", "")} for f in delta_result.recurring],
                "resolved": [{"description": r.description, "severity": r.severity} for r in delta_result.resolved],
            }
            if client_profile:
                client_profile.update_profile(client_id, {
                    "last_scan_date": brief.get("scan_date"),
                })
        except Exception:
            logger.bind(context={
                "client_id": client_id, "domain": domain,
            }).opt(exception=True).warning("client_memory_error")

    # Interpret
    try:
        interpreted = interpret_brief(brief, delta_context=delta_context)
    except InterpreterError as exc:
        logger.bind(context={
            "client_id": client_id, "domain": domain, "error": str(exc),
        }).error("interpret_failed")
        return

    # Compose for Telegram
    messages = compose_telegram(interpreted, delta_context=delta_context)

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

    logger.bind(context={
        "client_id": client_id,
        "domain": domain,
        "message_count": len(messages),
        "message_chars": sum(len(m) for m in messages),
        "path": str(out_path),
    }).info("message_composed")


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app(
    redis_url: str,
    results_dir: str,
    messages_dir: str = "/data/messages",
    briefs_dir: str = "data/output/briefs",
    clients_dir: str = "/data/clients",
) -> FastAPI:
    """Build and return the FastAPI application."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Startup
        app.state.redis = None
        app.state.pubsub_task = None
        app.state.log_buffer = collections.deque(maxlen=5000)
        app.state.log_listener_task = None

        # console.db initialisation runs FIRST, before any pubsub task
        # or middleware engages. console.db is api-owned (operators /
        # sessions / audit_log); no other container initialises it.
        # CREATE TABLE IF NOT EXISTS makes the call idempotent.
        #
        # NOTE: this is about SCHEMA LIFECYCLE only, not runtime data
        # access. The api uses clients.db extensively at runtime (read
        # queries in console.py + signup.py; PR-#49-narrow writes for
        # retention CAS UPDATEs landing in slice 3+). What the api does
        # NOT do is run init_db() on clients.db, because that would
        # invoke apply_pending_migrations() with unguarded ALTER TABLE
        # statements concurrently with the writer containers (scheduler
        # / worker / delivery), and the loser would raise
        # OperationalError mid-startup. The clients.audit_log table
        # appended to client-db-schema.sql in this slice is created by
        # the writer containers' init_db() via executescript on their
        # own startup; the api sees it on first read.
        init_db_console(app.state.console_db_path).close()

        try:
            redis_conn = redis.Redis.from_url(redis_url, decode_responses=True)
            redis_conn.ping()  # Sync call OK — runs once at startup only
            app.state.redis = redis_conn
            app.state.pubsub_task = asyncio.create_task(
                _listen_scan_complete(
                    redis_conn, app.state.result_store, messages_dir,
                    app.state.client_history, app.state.client_profile,
                ),
            )
            app.state.log_listener_task = asyncio.create_task(
                _listen_console_logs(redis_conn, app.state.log_buffer),
            )
        except Exception:
            logger.bind(context={"url": redis_url}).warning("redis_unavailable")

        logger.bind(context={"results_dir": results_dir}).info("api_started")
        yield
        # Shutdown
        for task in (app.state.pubsub_task, app.state.log_listener_task):
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        if app.state.redis:
            app.state.redis.close()
        logger.info("api_stopped")

    app = FastAPI(
        title="Heimdall API",
        version="3.0.0",
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.results_dir = results_dir
    app.state.result_store = ResultStore(results_dir)

    # Client Memory — delta detection and remediation tracking
    client_store = AtomicFileStore(clients_dir)
    app.state.client_history = ClientHistory(
        client_store, DeltaDetector(), RemediationTracker(),
    )
    app.state.client_profile = ClientProfile(client_store)
    app.state.briefs_dir = briefs_dir
    _client_dir = os.environ.get("CLIENT_DATA_DIR", "data/clients")
    app.state.db_path = os.environ.get("DB_PATH", f"{_client_dir}/clients.db")
    app.state.console_db_path = os.environ.get(
        "CONSOLE_DB_PATH", DEFAULT_CONSOLE_DB_PATH,
    )

    # Stage A.5 §4.3.3 mount order (locked 2026-05-02): Starlette /
    # FastAPI ``add_middleware`` pushes onto the HEAD of the stack —
    # the LAST add_middleware call is the OUTERMOST runtime layer. So
    # to get [RequestId → RequestLogging → SessionAuth → handler] at
    # runtime, we add SessionAuth FIRST (innermost), RequestLogging
    # SECOND (middle), RequestIdMiddleware LAST (outermost).
    #
    # Behavior change vs slice 3g.5 baseline: RequestLoggingMiddleware
    # now wraps SessionAuthMiddleware, so unauthenticated probes (401s)
    # are logged with request_id (today they short-circuit before
    # logging fires). RequestIdMiddleware outermost ensures every
    # downstream layer (and the ASGI WS scope) sees state.request_id
    # populated.
    #
    # Stage A slice 3g (f) retired the legacy Basic Auth fallback per
    # spec §7.10 Option B. ``SessionAuthMiddleware`` is the only auth
    # gate for ``/console/*`` and ``/app/*``; rollback is ``git revert``
    # of the slice 3g merge SHA per spec §9.1, no env flag.
    app.add_middleware(
        SessionAuthMiddleware,
        console_db_path=app.state.console_db_path,
    )
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(RequestIdMiddleware)

    app.include_router(auth_router)
    app.include_router(console_router)
    app.include_router(signup_router)
    static_dir = Path(__file__).parent / "static"
    if static_dir.is_dir():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # Console SPA (Svelte build)
    dist_dir = Path(__file__).parent / "static" / "dist"
    if dist_dir.is_dir():
        app.mount("/app", StaticFiles(directory=str(dist_dir), html=True), name="console-spa")

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
        date: str | None = Query(default=None),
        include: str | None = Query(default=None),
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
