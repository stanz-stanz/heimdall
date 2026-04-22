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
import random
import uuid

from loguru import logger

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
    redis_conn: object | None = None,
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
    logger.bind(context={"scan_id": scan_id, "domain": domain}).info("demo_started")

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

    # --- Phase 3: Findings one by one -------------------------------------
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
    logger.bind(context={
        "scan_id": scan_id, "domain": domain,
        "findings_count": len(findings),
    }).info("demo_completed")

