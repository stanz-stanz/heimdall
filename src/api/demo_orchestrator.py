"""Demo scan replay orchestrator.

Reads a pre-computed prospect brief and publishes scan events with
theatrical pacing for the Hollywood demo mode.  Events flow through
an asyncio.Queue (in-process) so the demo works without Redis.
When Redis is available, events are also published to pub/sub for
multi-process setups.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import shutil
import uuid
from typing import Optional

log = logging.getLogger(__name__)

# Scan types shown in the demo timeline (Layer 1 only)
SCAN_SEQUENCE = [
    ("ssl", "SSL Certificate"),
    ("headers", "Security Headers"),
    ("meta", "Page Metadata"),
    ("httpx", "HTTP Fingerprint"),
    ("webanalyze", "CMS Detection"),
    ("subfinder", "Subdomain Scan"),
    ("dnsx", "DNS Records"),
    ("crtsh", "Certificate Transparency"),
]

# In-process event queues keyed by scan_id
_demo_queues: dict[str, asyncio.Queue] = {}


def generate_scan_id() -> str:
    return str(uuid.uuid4())[:8]


def get_demo_queue(scan_id: str) -> asyncio.Queue:
    """Get or create the event queue for a demo session."""
    if scan_id not in _demo_queues:
        _demo_queues[scan_id] = asyncio.Queue()
    return _demo_queues[scan_id]


def cleanup_demo_queue(scan_id: str) -> None:
    """Remove the event queue for a completed demo."""
    _demo_queues.pop(scan_id, None)


async def run_demo_replay(
    scan_id: str,
    brief: dict,
    redis_conn: Optional[object] = None,
) -> None:
    """Replay a prospect brief as a theatrical scan demo.

    Pushes events to an in-process asyncio.Queue that the WebSocket
    handler reads from directly.  Optionally also publishes to Redis
    pub/sub when a connection is available.
    """
    queue = get_demo_queue(scan_id)
    channel = f"demo:{scan_id}"

    def publish(event: dict) -> None:
        data = json.dumps(event)
        queue.put_nowait(data)
        if redis_conn:
            try:
                redis_conn.publish(channel, data)
            except Exception:
                pass

    domain = brief.get("domain", "unknown")
    log.info("demo_started", extra={"context": {"scan_id": scan_id, "domain": domain}})

    # --- Phase 1: Initialisation ------------------------------------------
    publish({"type": "phase", "phase": "initializing",
             "message": "Preparing target environment..."})
    await asyncio.sleep(1.5)

    publish({"type": "phase", "phase": "scanning",
             "message": "Target online. Beginning scan."})
    await asyncio.sleep(0.8)

    # --- Phase 2: Scan type progress --------------------------------------
    total = len(SCAN_SEQUENCE)
    for idx, (scan_type, label) in enumerate(SCAN_SEQUENCE, 1):
        publish({
            "type": "scan_start",
            "scan_type": scan_type,
            "label": label,
            "index": idx,
            "total": total,
        })
        await asyncio.sleep(random.uniform(0.4, 1.2))

        publish({
            "type": "scan_complete",
            "scan_type": scan_type,
            "duration_ms": random.randint(80, 600),
            "index": idx,
            "total": total,
        })
        await asyncio.sleep(0.3)

    # --- Phase 3: Tech stack reveal ---------------------------------------
    tech_stack = brief.get("tech_stack", [])
    publish({"type": "tech_reveal", "tech_stack": tech_stack})
    await asyncio.sleep(1.5)

    # --- Phase 4: Findings one by one -------------------------------------
    findings = brief.get("findings", [])
    for idx, finding in enumerate(findings, 1):
        publish({
            "type": "finding",
            "index": idx,
            "total": len(findings),
            "severity": finding.get("severity", "info"),
            "description": finding.get("description", ""),
            "risk": finding.get("risk", ""),
        })
        await asyncio.sleep(random.uniform(0.8, 1.5))

    # --- Done -------------------------------------------------------------
    publish({
        "type": "complete",
        "domain": domain,
        "findings_count": len(findings),
        "company_name": brief.get("company_name", ""),
    })
    log.info("demo_completed", extra={"context": {
        "scan_id": scan_id, "domain": domain,
        "findings_count": len(findings),
    }})


# --- Live twin demo mode ---------------------------------------------------

# Concurrency guard: only one live demo at a time
_live_demo_lock = asyncio.Lock()


async def _stream_nuclei_scan(port: int, publish) -> list[dict]:
    """Run Nuclei against the twin and publish findings as they arrive."""
    if not shutil.which("nuclei"):
        publish({"type": "phase", "phase": "warning",
                 "message": "Nuclei not installed — falling back to brief findings"})
        return []

    proc = await asyncio.create_subprocess_exec(
        "nuclei", "-u", f"http://127.0.0.1:{port}",
        "-jsonl", "-silent", "-no-color",
        "-severity", "critical,high,medium,low",
        "-rate-limit", "50", "-concurrency", "5",
        "-timeout", "10", "-no-update-check",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    findings = []
    idx = 0
    async for line in proc.stdout:
        text = line.decode().strip()
        if not text:
            continue
        try:
            entry = json.loads(text)
            idx += 1
            severity = entry.get("info", {}).get("severity", "info").lower()
            finding = {
                "type": "finding",
                "index": idx,
                "total": "?",
                "severity": severity,
                "description": entry.get("info", {}).get("name", "Unknown"),
                "risk": entry.get("info", {}).get("description", ""),
                "provenance": "unconfirmed",
            }
            publish(finding)
            findings.append(finding)
        except json.JSONDecodeError:
            continue

    await proc.wait()
    return findings


async def run_demo_live(
    scan_id: str,
    brief: dict,
    redis_conn: Optional[object] = None,
) -> None:
    """Run a live twin scan and stream findings as they happen.

    Starts a digital twin from the brief, runs Layer 2 tools against it,
    and publishes events in real-time. Falls back to replay mode if the
    twin cannot be started or tools are not installed.
    """
    queue = get_demo_queue(scan_id)
    channel = f"demo:{scan_id}"

    def publish(event: dict) -> None:
        data = json.dumps(event)
        queue.put_nowait(data)
        if redis_conn:
            try:
                redis_conn.publish(channel, data)
            except Exception:
                pass

    domain = brief.get("domain", "unknown")
    log.info("demo_live_started", extra={"context": {"scan_id": scan_id, "domain": domain}})

    if not _live_demo_lock.locked():
        pass  # will acquire below
    else:
        publish({"type": "phase", "phase": "busy",
                 "message": "Another live demo is running. Falling back to replay."})
        await run_demo_replay(scan_id, brief, redis_conn)
        return

    async with _live_demo_lock:
        # --- Phase 1: Start twin ------------------------------------------
        publish({"type": "phase", "phase": "twin_starting",
                 "message": "Building digital twin..."})

        try:
            from tools.twin.twin_server import (
                TwinHandler, _build_routes, _build_common_headers, HTTPServer,
            )
            from tools.twin.templates import load_slug_map

            slug_map = load_slug_map()
            routes = _build_routes(brief, slug_map)
            common_headers = _build_common_headers(brief)

            TwinHandler.routes = routes
            TwinHandler.domain = domain
            TwinHandler.common_headers = common_headers
            TwinHandler.login_cookie = f"domain={domain}"
            TwinHandler.jitter = False

            import threading
            server = HTTPServer(("127.0.0.1", 0), TwinHandler)
            port = server.server_address[1]
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
        except Exception as exc:
            log.error("demo_live_twin_failed: %s", exc)
            publish({"type": "phase", "phase": "error",
                     "message": "Twin failed to start. Falling back to replay."})
            await run_demo_replay(scan_id, brief, redis_conn)
            return

        try:
            await asyncio.sleep(0.5)
            publish({"type": "phase", "phase": "twin_ready",
                     "message": f"Twin online at port {port}. Scanning..."})

            # --- Phase 2: Scan sequence ------------------------------------
            publish({"type": "scan_start", "scan_type": "nuclei",
                     "label": "Nuclei Vulnerability Scanner", "index": 1, "total": 2})

            findings = await _stream_nuclei_scan(port, publish)

            publish({"type": "scan_complete", "scan_type": "nuclei",
                     "duration_ms": 0, "index": 1, "total": 2})

            # WPScan if WordPress
            cms = brief.get("technology", {}).get("cms", "")
            if cms and cms.lower() == "wordpress" and shutil.which("wpscan"):
                publish({"type": "scan_start", "scan_type": "wpscan",
                         "label": "WPScan WordPress Scanner", "index": 2, "total": 2})
                # WPScan doesn't stream JSONL easily, run batch
                from src.worker.twin_scan import _run_wpscan_against_twin
                wp_findings = await asyncio.to_thread(_run_wpscan_against_twin, port)
                for f in wp_findings:
                    findings.append(f)
                    publish({
                        "type": "finding",
                        "index": len(findings),
                        "total": "?",
                        "severity": f.get("severity", "info"),
                        "description": f.get("description", ""),
                        "risk": f.get("risk", ""),
                        "provenance": "unconfirmed",
                    })
                publish({"type": "scan_complete", "scan_type": "wpscan",
                         "duration_ms": 0, "index": 2, "total": 2})

            # If no tools found findings, show brief's existing findings
            if not findings:
                publish({"type": "phase", "phase": "fallback",
                         "message": "No Layer 2 tools available. Showing Layer 1 findings."})
                for idx, finding in enumerate(brief.get("findings", []), 1):
                    publish({
                        "type": "finding",
                        "index": idx,
                        "total": len(brief.get("findings", [])),
                        "severity": finding.get("severity", "info"),
                        "description": finding.get("description", ""),
                        "risk": finding.get("risk", ""),
                    })
                    await asyncio.sleep(random.uniform(0.5, 1.0))
                findings = brief.get("findings", [])

            # Tech reveal
            tech_stack = brief.get("tech_stack", [])
            publish({"type": "tech_reveal", "tech_stack": tech_stack})
            await asyncio.sleep(0.5)

            # --- Complete -------------------------------------------------
            publish({
                "type": "complete",
                "domain": domain,
                "findings_count": len(findings),
                "company_name": brief.get("company_name", ""),
                "mode": "live",
            })
            log.info("demo_live_completed", extra={"context": {
                "scan_id": scan_id, "domain": domain,
                "findings_count": len(findings),
            }})
        finally:
            server.shutdown()
