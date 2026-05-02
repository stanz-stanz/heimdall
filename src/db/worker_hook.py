"""Worker DB hook -- saves scan results to SQLite after each scan.

Called by src/worker/main.py after _write_result(). Fail-safe:
exceptions are caught and logged by the caller in main.py, never
fatal to the scan pipeline.
"""

from __future__ import annotations

import json
import sqlite3
import uuid

from loguru import logger

from src.db.connection import _now
from src.db.scans import complete_scan_entry, create_scan_entry, save_brief_snapshot


def save_scan_to_db(conn: sqlite3.Connection, job: dict, result: dict) -> None:
    """Save a completed scan result to the client database.

    Creates a scan_history entry, completes it with timing/cache data,
    saves a brief_snapshot if the result contains a brief, and runs
    delta detection when a CVR is available.

    Args:
        conn: Connection to data/clients/clients.db (must be read-write).
        job: The scan job dict with keys: job_id, domain, client_id,
            and optionally run_id.
        result: The scan result dict from execute_scan_job(), with keys:
            domain, status, brief, timing, cache_stats, scan_result.

    Raises:
        Any exception from the underlying DB operations. The caller in
        main.py wraps this in try/except to keep the pipeline running.
    """
    domain = job.get("domain", "")
    scan_id = f"scan-{_now()[:10]}-{uuid.uuid4().hex[:8]}"
    brief = result.get("brief", {})
    timing = result.get("timing", {})
    cache_stats = result.get("cache_stats", {})
    status = result.get("status", "completed")
    gate_decision_id = job.get("gate_decision_id")

    # 1. Create scan_history entry
    create_scan_entry(
        conn,
        scan_id=scan_id,
        domain=domain,
        scan_date=_now()[:10],
        run_id=job.get("run_id"),
        cvr=job.get("client_id"),
        gate_decision_id=gate_decision_id,
    )

    # 2. Complete it with timing, cache stats, and raw result
    complete_scan_entry(
        conn,
        scan_id=scan_id,
        status="completed" if status != "skipped" else "skipped",
        total_ms=int(timing.get("total_ms", 0)) if timing else None,
        timing_json=json.dumps(timing) if timing else None,
        cache_hits=cache_stats.get("hits", 0),
        cache_misses=cache_stats.get("misses", 0),
        result_json=json.dumps(result.get("scan_result")) if result.get("scan_result") else None,
    )

    # 3. Save brief snapshot (if brief is non-empty)
    if brief:
        save_brief_snapshot(
            conn,
            domain=domain,
            scan_date=_now()[:10],
            brief_dict=brief,
            scan_id=scan_id,
            company_name=brief.get("company_name"),
            cvr=job.get("client_id"),
        )

    # 4. Run delta detection if CVR is available and findings exist
    cvr = job.get("client_id")
    if cvr and brief.get("findings"):
        try:
            from src.db.client_history import DBClientHistory

            history = DBClientHistory(conn)
            delta = history.record_scan(cvr, domain, brief, scan_id=scan_id)
            logger.bind(context={
                "domain": domain,
                "new": len(delta.new),
                "recurring": len(delta.recurring),
                "resolved": len(delta.resolved),
            }).info("db_hook_delta")
        except Exception:
            logger.opt(exception=True).error("db_hook_delta_failed for {}", domain)

    conn.commit()

    logger.bind(context={
        "domain": domain,
        "scan_id": scan_id,
        "finding_count": len(brief.get("findings", [])),
    }).info("db_hook_saved")
