"""Console API router — monitor dashboard, operator console, and Hollywood demo endpoints."""

from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from fastapi import APIRouter, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from loguru import logger
from pydantic import BaseModel

from src.api.auth.audit import (
    maybe_write_disabled_operator_audit,
    write_console_audit_row,
)
from src.api.auth.middleware import SESSION_COOKIE
from src.api.auth.sessions import validate_session_by_hash
from src.db.console_connection import DEFAULT_CONSOLE_DB_PATH, get_console_conn
from src.db.console_views import (
    list_retention_queue_pending_due,
    list_trial_expiring,
)
from src.db.retention import (
    force_run_retention_job,
    retry_failed_retention_job,
)

from .demo_orchestrator import (
    cleanup_demo_queue,
    generate_scan_id,
    get_demo_queue,
    run_demo_replay,
)

router = APIRouter(prefix="/console", tags=["console"])


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class DemoStartRequest(BaseModel):
    domain: str


class DemoStartResponse(BaseModel):
    scan_id: str
    domain: str


class RetentionCancelBody(BaseModel):
    notes: str | None = None


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
        with open(brief_file, encoding="utf-8") as f:
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
        "timestamp": datetime.now(UTC).isoformat(),
    }


# ---------------------------------------------------------------------------
# Operator console endpoints
# ---------------------------------------------------------------------------

# Whitelists for input validation
_VALID_SETTINGS = frozenset(("filters", "interpreter", "delivery"))
_VALID_COMMANDS = frozenset(("run-pipeline", "interpret", "send"))


# ---------------------------------------------------------------------------
# WebSocket auth — handler-level gate (Stage A spec §5.2 Option 2 + §5.3)
# ---------------------------------------------------------------------------


class _WSRequestAdapter:
    """Duck-typed ``Request`` adapter over a ``WebSocket`` scope.

    ``write_console_audit_row`` only reads ``.client``, ``.headers``,
    and ``.state`` from its request argument; the WS scope exposes the
    first two natively, and ``.state`` is a fresh ``SimpleNamespace``
    because the WS path has no SessionAuthMiddleware to pre-populate
    operator / session / request-id attributes — the helper passes
    those explicitly via kwargs instead. Slice 3g spec §4.2 locks this
    adapter shape so the audit writer stays HTTP-Request-only.
    """

    __slots__ = ("client", "headers", "state")

    def __init__(self, websocket: WebSocket) -> None:
        self.client = websocket.client  # Address(host, port) | None
        self.headers = websocket.headers
        self.state = SimpleNamespace()


def _build_pseudo_request(websocket: WebSocket) -> _WSRequestAdapter:
    """Return a duck-typed ``Request`` for the audit-row helpers."""
    return _WSRequestAdapter(websocket)


async def _authenticate_ws(
    websocket: WebSocket, *, audit_payload: dict
) -> tuple[int, int] | None:
    """Read the session cookie, validate, accept-or-close-with-4401.

    On success: opens a single ``console.db`` connection, validates the
    session, accepts the WebSocket upgrade, writes the
    ``liveops.ws_connected`` audit row inside the same ``with conn:``
    block, then closes the connection and returns
    ``(operator_id, session_id)``. The returned identifiers let the
    caller log forensic context without re-fetching.

    On failure: accepts the upgrade then sends a clean
    ``websocket.close(code=4401)`` per RFC 6455 (you must accept before
    you can close cleanly). If the cookie maps to an otherwise-active
    session whose operator was disabled, the disabled-operator audit
    row is written first per §7.9 Option A — symmetry with the HTTP
    middleware's ``auth.session_rejected_disabled`` path.

    Returns ``None`` on every failure mode; the caller must ``return``
    immediately.
    """
    cookie_value = websocket.cookies.get(SESSION_COOKIE)
    if not cookie_value:
        await websocket.accept()
        await websocket.close(code=4401)
        return None

    presented_hash = hashlib.sha256(cookie_value.encode("utf-8")).hexdigest()
    console_db_path = getattr(
        websocket.app.state, "console_db_path", DEFAULT_CONSOLE_DB_PATH
    )

    pseudo_request = _build_pseudo_request(websocket)

    # Mirror SessionAuthMiddleware's conn lifecycle (src/api/auth/middleware.py
    # §3.2): open + use + close on the same thread so SQLite's
    # check_same_thread guard is satisfied. console.db is tiny; the
    # blocking SELECT / INSERT cost is sub-millisecond and not worth
    # the cross-thread complexity that ``asyncio.to_thread`` would add.
    conn = get_console_conn(console_db_path)
    try:
        session_row = validate_session_by_hash(conn, presented_hash)
        if session_row is None:
            maybe_write_disabled_operator_audit(
                conn, pseudo_request, presented_hash
            )
            await websocket.accept()
            await websocket.close(code=4401)
            return None

        operator_id = session_row["operator_id"]
        session_id = session_row["id"]

        await websocket.accept()

        # §5.8 — pair the per-WS audit row with the same connection
        # that authorized the upgrade. ``with conn:`` commits the row
        # atomically; the audit writer does not self-commit.
        with conn:
            write_console_audit_row(
                conn,
                pseudo_request,
                action="liveops.ws_connected",
                target_type="websocket",
                target_id=None,
                payload=audit_payload,
                operator_id=operator_id,
                session_id=session_id,
            )

        return operator_id, session_id
    finally:
        conn.close()


@router.get("/dashboard")
async def console_dashboard(request: Request):
    """Dashboard stats — prospect/brief/client/critical counts, queues, activity."""
    db_path = getattr(request.app.state, "db_path", "data/clients/clients.db")
    redis_conn = getattr(request.app.state, "redis", None)

    def _query():
        try:
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
        except sqlite3.OperationalError as exc:
            logger.warning("console_db_unavailable: {}", exc)
            return {"error": "Database unavailable", "detail": str(exc)}
        except sqlite3.DatabaseError as exc:
            logger.critical("console_db_corruption: {}", exc)
            return {"error": "Database error", "detail": str(exc)}

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
    data["timestamp"] = datetime.now(UTC).isoformat()
    return data


@router.get("/pipeline/last")
async def console_pipeline_last(request: Request):
    """Last completed pipeline run from v_latest_run."""
    db_path = getattr(request.app.state, "db_path", "data/clients/clients.db")

    def _query():
        try:
            conn = sqlite3.connect(db_path, timeout=5)
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute("SELECT * FROM v_latest_run").fetchone()
                return dict(row) if row else None
            finally:
                conn.close()
        except sqlite3.OperationalError as exc:
            logger.warning("console_db_unavailable: {}", exc)
            return {"error": "Database unavailable", "detail": str(exc)}
        except sqlite3.DatabaseError as exc:
            logger.critical("console_db_corruption: {}", exc)
            return {"error": "Database error", "detail": str(exc)}

    result = await asyncio.to_thread(_query)
    if result is None:
        return {"status": "no_runs"}
    return result


@router.get("/campaigns")
async def console_campaigns(request: Request):
    """Campaign list with status counts from v_campaign_summary."""
    db_path = getattr(request.app.state, "db_path", "data/clients/clients.db")

    def _query():
        try:
            conn = sqlite3.connect(db_path, timeout=5)
            conn.row_factory = sqlite3.Row
            try:
                rows = conn.execute("SELECT * FROM v_campaign_summary").fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()
        except sqlite3.OperationalError as exc:
            logger.warning("console_db_unavailable: {}", exc)
            return {"error": "Database unavailable", "detail": str(exc)}
        except sqlite3.DatabaseError as exc:
            logger.critical("console_db_corruption: {}", exc)
            return {"error": "Database error", "detail": str(exc)}

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
        try:
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
        except sqlite3.OperationalError as exc:
            logger.warning("console_db_unavailable: {}", exc)
            return {"error": "Database unavailable", "detail": str(exc)}
        except sqlite3.DatabaseError as exc:
            logger.critical("console_db_corruption: {}", exc)
            return {"error": "Database error", "detail": str(exc)}

    return await asyncio.to_thread(_query)


@router.get("/briefs/list")
async def console_briefs_list(
    request: Request,
    critical: bool = Query(default=False),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
):
    """List briefs from v_current_briefs — the dashboard's "Briefs" and
    "Critical" indicators both target this endpoint. Returns one row per
    current brief (latest snapshot per domain)."""
    db_path = getattr(request.app.state, "db_path", "data/clients/clients.db")

    def _query():
        try:
            conn = sqlite3.connect(db_path, timeout=5)
            conn.row_factory = sqlite3.Row
            try:
                sql = (
                    "SELECT domain, scan_date, bucket, cms, hosting,"
                    "       finding_count, critical_count, high_count,"
                    "       medium_count, low_count, info_count,"
                    "       company_name"
                    " FROM v_current_briefs"
                )
                params: list = []
                if critical:
                    sql += " WHERE critical_count > 0"
                sql += " ORDER BY critical_count DESC, high_count DESC,"
                sql += "          finding_count DESC, domain ASC"
                sql += " LIMIT ? OFFSET ?"
                params.extend([limit, offset])
                rows = conn.execute(sql, params).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()
        except sqlite3.OperationalError as exc:
            logger.warning("console_db_unavailable: {}", exc)
            return {"error": "Database unavailable", "detail": str(exc)}
        except sqlite3.DatabaseError as exc:
            logger.critical("console_db_corruption: {}", exc)
            return {"error": "Database error", "detail": str(exc)}

    return await asyncio.to_thread(_query)


@router.get("/clients/list")
async def console_clients_list(request: Request):
    """Onboarded clients with domain, latest scan, open findings, last delivery."""
    db_path = getattr(request.app.state, "db_path", "data/clients/clients.db")

    def _query():
        try:
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
        except sqlite3.OperationalError as exc:
            logger.warning("console_db_unavailable: {}", exc)
            return {"error": "Database unavailable", "detail": str(exc)}
        except sqlite3.DatabaseError as exc:
            logger.critical("console_db_corruption: {}", exc)
            return {"error": "Database error", "detail": str(exc)}

    return await asyncio.to_thread(_query)


# ---------------------------------------------------------------------------
# Operator-console list views — V1 trial-expiring, V6 retention queue
# ---------------------------------------------------------------------------
#
# Spec lives in ~/.claude/plans/i-need-you-to-logical-pebble.md (V1–V6).
# V2–V5 are soft-blocked on the Betalingsservice webhook plumbing and
# land alongside that work.


def _resolve_db_path(request: Request) -> str:
    return getattr(request.app.state, "db_path", "data/clients/clients.db")


_RETENTION_ACTION_VERBS = {
    "force_run": "force-ran",
    "cancel": "cancelled",
    "retry": "retried",
}


def _publish_retention_action(
    request: Request,
    *,
    action: str,
    job: dict,
) -> None:
    """Publish an operator-action event to console:activity.

    Uses ``type='activity'`` to match the existing console-activity
    consumer (``src/api/frontend/src/views/Logs.svelte`` and the
    Dashboard activity feed only render messages tagged ``activity``).
    The structured fields (``action``, ``job_id``, ``cvr``) ride along
    in ``payload`` for any future consumer that wants them, but the
    primary surface is the human-readable ``message`` field.

    Failure to publish is logged but not raised — the DB write has
    already committed.
    """
    redis_conn = getattr(request.app.state, "redis", None)
    if redis_conn is None:
        return
    verb = _RETENTION_ACTION_VERBS.get(action, action)
    message = (
        f"Operator {verb} retention job #{job['id']} "
        f"(cvr={job['cvr']}, action={job['action']})"
    )
    try:
        redis_conn.publish(
            "console:activity",
            json.dumps(
                {
                    "type": "activity",
                    "payload": {
                        "message": message,
                        "action": action,
                        "job_id": job["id"],
                        "cvr": job["cvr"],
                        "status": job["status"],
                    },
                    "ts": datetime.now(UTC).isoformat(),
                }
            ),
        )
    except Exception as exc:
        logger.warning("console_activity_publish_failed action={} err={}", action, exc)


@router.get("/clients/trial-expiring")
async def console_trial_expiring(
    request: Request,
    window_days: int = Query(default=7, ge=1, le=30),
):
    """V1 — Watchman trials expiring within ``window_days`` (default 7)
    that have not engaged with the Sentinel upgrade flow."""
    db_path = _resolve_db_path(request)

    def _query():
        try:
            conn = sqlite3.connect(db_path, timeout=5)
            conn.row_factory = sqlite3.Row
            try:
                return list_trial_expiring(conn, window_days=window_days)
            finally:
                conn.close()
        except sqlite3.OperationalError as exc:
            logger.warning("console_db_unavailable: {}", exc)
            return {"error": "Database unavailable", "detail": str(exc)}
        except sqlite3.DatabaseError as exc:
            logger.critical("console_db_corruption: {}", exc)
            return {"error": "Database error", "detail": str(exc)}

    return await asyncio.to_thread(_query)


@router.get("/clients/retention-queue")
async def console_retention_queue(
    request: Request,
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
):
    """V6 — retention jobs the cron is about to claim
    (``status='pending' AND scheduled_for <= now``)."""
    db_path = _resolve_db_path(request)

    def _query():
        try:
            conn = sqlite3.connect(db_path, timeout=5)
            conn.row_factory = sqlite3.Row
            try:
                return list_retention_queue_pending_due(
                    conn, limit=limit, offset=offset
                )
            finally:
                conn.close()
        except sqlite3.OperationalError as exc:
            logger.warning("console_db_unavailable: {}", exc)
            return {"error": "Database unavailable", "detail": str(exc)}
        except sqlite3.DatabaseError as exc:
            logger.critical("console_db_corruption: {}", exc)
            return {"error": "Database error", "detail": str(exc)}

    return await asyncio.to_thread(_query)


def _run_retention_action(
    db_path: str,
    job_id: int,
    *,
    action: str,
    fn,
    fn_kwargs: dict | None = None,
) -> dict:
    """Open a connection, dispatch the helper, log the audit line.

    The helper raises ``KeyError`` on missing / wrong-state rows; we
    re-raise the same ``KeyError`` so the FastAPI handler can map it
    to a 404. The DB write is the source of truth — logging happens
    after a successful commit.
    """
    conn = sqlite3.connect(db_path, timeout=5)
    conn.row_factory = sqlite3.Row
    try:
        kwargs = fn_kwargs or {}
        updated = fn(conn, job_id, **kwargs)
    finally:
        conn.close()

    logger.bind(
        context={
            "event": "operator_retention_action",
            "action": action,
            "job_id": job_id,
            "cvr": updated["cvr"],
            "operator": "console",
        }
    ).info("operator_retention_action")
    return updated


@router.post("/retention-jobs/{job_id}/force-run")
async def console_retention_force_run(job_id: int, request: Request):
    """Advance a pending retention job's ``scheduled_for`` to now so the
    next cron tick claims it. The cron remains the sole executor."""
    db_path = _resolve_db_path(request)
    try:
        updated = await asyncio.to_thread(
            _run_retention_action,
            db_path,
            job_id,
            action="force_run",
            fn=force_run_retention_job,
        )
    except KeyError as exc:
        raise HTTPException(404, detail=str(exc)) from exc
    except sqlite3.OperationalError as exc:
        logger.warning("console_db_unavailable_force_run job_id={} err={}", job_id, exc)
        raise HTTPException(503, detail=f"Database unavailable: {exc}") from exc
    except sqlite3.DatabaseError as exc:
        logger.critical("console_db_corruption_force_run job_id={} err={}", job_id, exc)
        raise HTTPException(500, detail=f"Database error: {exc}") from exc
    _publish_retention_action(request, action="force_run", job=updated)
    return updated


@router.post("/retention-jobs/{job_id}/cancel")
async def console_retention_cancel(
    job_id: int,
    request: Request,
    body: RetentionCancelBody | None = None,
):
    """Cancel a pending retention job using a CAS UPDATE.

    The CAS predicate ``status='pending'`` makes the transition atomic
    against the cron's claim-lock — if the cron already promoted the
    row to ``running`` we surface 404 rather than cancelling a job
    mid-execution.

    The request body is optional. When ``notes`` is omitted or ``null``
    the existing ``notes`` column is preserved (one-click cancel flow);
    a non-null ``notes`` value overwrites the column.
    """
    db_path = _resolve_db_path(request)
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    notes_override = body.notes if body is not None else None

    def _do():
        conn = sqlite3.connect(db_path, timeout=5)
        conn.row_factory = sqlite3.Row
        try:
            # CAS UPDATE: only flip pending → cancelled. The cron's
            # claim path uses BEGIN IMMEDIATE + UPDATE ... WHERE
            # status='pending' RETURNING; this matches that pattern so
            # exactly one of the two transitions wins.
            #
            # COALESCE preserves any pre-existing notes when the
            # operator submits a body-less cancel — Codex flagged the
            # naive ``notes = ?`` overwrite on 2026-04-26.
            cursor = conn.execute(
                """
                UPDATE retention_jobs
                   SET status = 'cancelled',
                       executed_at = ?,
                       notes = COALESCE(?, notes)
                 WHERE id = ?
                   AND status = 'pending'
                """,
                (now, notes_override, job_id),
            )
            conn.commit()
            if cursor.rowcount == 0:
                # Either the row doesn't exist or the cron beat us.
                # Distinguish for the operator's sake.
                row = conn.execute(
                    "SELECT status FROM retention_jobs WHERE id = ?",
                    (job_id,),
                ).fetchone()
                if row is None:
                    raise KeyError(f"Retention job {job_id} not found")
                raise KeyError(
                    f"Retention job {job_id} is not pending "
                    f"(status={row['status']!r})"
                )
            row = conn.execute(
                "SELECT * FROM retention_jobs WHERE id = ?", (job_id,)
            ).fetchone()
            return dict(row)
        finally:
            conn.close()

    try:
        updated = await asyncio.to_thread(_do)
    except KeyError as exc:
        raise HTTPException(404, detail=str(exc)) from exc
    except sqlite3.OperationalError as exc:
        logger.warning("console_db_unavailable_cancel job_id={} err={}", job_id, exc)
        raise HTTPException(503, detail=f"Database unavailable: {exc}") from exc
    except sqlite3.DatabaseError as exc:
        logger.critical("console_db_corruption_cancel job_id={} err={}", job_id, exc)
        raise HTTPException(500, detail=f"Database error: {exc}") from exc

    logger.bind(
        context={
            "event": "operator_retention_action",
            "action": "cancel",
            "job_id": job_id,
            "cvr": updated["cvr"],
            "operator": "console",
        }
    ).info("operator_retention_action")
    _publish_retention_action(request, action="cancel", job=updated)
    return updated


@router.post("/retention-jobs/{job_id}/retry")
async def console_retention_retry(job_id: int, request: Request):
    """Re-queue a failed retention job. Sets status back to ``'pending'``
    with ``scheduled_for=now``; the cron will retry on next tick."""
    db_path = _resolve_db_path(request)
    try:
        updated = await asyncio.to_thread(
            _run_retention_action,
            db_path,
            job_id,
            action="retry",
            fn=retry_failed_retention_job,
        )
    except KeyError as exc:
        raise HTTPException(404, detail=str(exc)) from exc
    except sqlite3.OperationalError as exc:
        logger.warning("console_db_unavailable_retry job_id={} err={}", job_id, exc)
        raise HTTPException(503, detail=f"Database unavailable: {exc}") from exc
    except sqlite3.DatabaseError as exc:
        logger.critical("console_db_corruption_retry job_id={} err={}", job_id, exc)
        raise HTTPException(500, detail=f"Database error: {exc}") from exc
    _publish_retention_action(request, action="retry", job=updated)
    return updated


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
        "ts": datetime.now(UTC).isoformat(),
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
    """WebSocket for live console updates — queue polling + Redis pub/sub forwarding.

    Stage A slice 3g (d): the auth gate lives in the handler, not the
    HTTP middleware (master spec §5.2 Option 2). ``_authenticate_ws``
    reads the session cookie BEFORE accepting the upgrade and either
    accepts + writes ``liveops.ws_connected`` or sends ``close(4401)``
    and returns ``None`` — see helper docstring for the contract.
    """
    auth = await _authenticate_ws(
        websocket, audit_payload={"path": "/console/ws"}
    )
    if auth is None:
        return

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
                        "ts": datetime.now(UTC).timestamp(),
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
                        "ts": datetime.now(UTC).isoformat(),
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
    briefs_path = _briefs_dir(request)
    brief = _load_brief(briefs_path, body.domain)
    if brief is None:
        raise HTTPException(404, detail=f"No brief found for {body.domain}")

    scan_id = generate_scan_id()

    pending = getattr(request.app.state, "_pending_demos", {})
    pending[scan_id] = brief
    request.app.state._pending_demos = pending

    return DemoStartResponse(scan_id=scan_id, domain=body.domain)


@router.websocket("/demo/ws/{scan_id}")
async def demo_websocket(websocket: WebSocket, scan_id: str):
    """Stream demo events to the client via WebSocket.

    The replay task launches here (not in demo_start) so events
    never publish before the client is listening.

    Stage A slice 3g (d): the same handler-level auth contract as
    ``/console/ws`` (master spec §5.5) — demo replay is operator-only.
    """
    auth = await _authenticate_ws(
        websocket,
        audit_payload={"path": "/console/demo/ws", "scan_id": scan_id},
    )
    if auth is None:
        return

    # Launch the demo now that the client is connected
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
            except TimeoutError:
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
