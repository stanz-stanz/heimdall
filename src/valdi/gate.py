from __future__ import annotations

import json
import os
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
import sqlite3

from loguru import logger

from src.consent.validator import ConsentCheckResult, check_consent
from src.db.connection import init_db
from src.db.conversion import record_conversion_event
from src.db.valdi import save_gate_decision
from src.prospecting.scanners.registry import get_scan_function, get_scan_functions_for_level
from .envelope import get_current_envelope
from .models import Envelope, GateDecision, GateExecutionContext, ScanRequest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_LOG_DIR = _PROJECT_ROOT / "logs" / "valdi"
_GATE_CTX: ContextVar[GateExecutionContext | None] = ContextVar(
    "valdi_gate_ctx", default=None
)


class GateDeniedError(RuntimeError):
    pass


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_forensic_log(req: ScanRequest, decision: str, reason: str, target_basis: str) -> str:
    log_dir = Path(os.environ.get("HEIMDALL_VALDI_LOG_DIR", str(_DEFAULT_LOG_DIR)))
    log_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y-%m-%d_%H-%M-%S")
    suffix = "allowed" if decision == "allowed" else "blocked"
    path = log_dir / f"{ts}_gate_{suffix}.md"
    lines = [
        "# Valdi Gate Decision",
        "",
        f"- `surface`: {req.surface}",
        f"- `scan_type`: {req.scan_type}",
        f"- `requested_level`: {req.requested_level}",
        f"- `domain`: {req.domain}",
        f"- `domains`: {list(req.domains)}",
        f"- `client_id`: {req.client_id}",
        f"- `decision`: {decision}",
        f"- `target_basis`: {target_basis}",
        f"- `reason`: {reason}",
        f"- `occurred_at`: {_now_iso()}",
    ]
    try:
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except PermissionError:
        fallback_dir = Path("/tmp/heimdall-valdi-logs")
        fallback_dir.mkdir(parents=True, exist_ok=True)
        path = fallback_dir / path.name
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)


def get_gate_execution_context() -> GateExecutionContext | None:
    return _GATE_CTX.get()


@contextmanager
def gated_execution(decision: GateDecision):
    token = _GATE_CTX.set(GateExecutionContext(decision=decision))
    try:
        yield
    finally:
        _GATE_CTX.reset(token)


def run_gated_scan(scan_type: str, *args, **kwargs):
    ctx = get_gate_execution_context()
    if ctx is None:
        raise RuntimeError(f"Registered scan {scan_type} executed without Valdi gate context")
    if scan_type not in ctx.decision.allowed_scan_types:
        raise RuntimeError(f"Registered scan {scan_type} not authorised by current Valdi decision")
    fn = get_scan_function(scan_type)
    return fn(*args, **kwargs)


def _persist_decision(
    req: ScanRequest,
    envelope: Envelope,
    decision: str,
    reason: str,
    target_basis: str,
    allowed_scan_types: tuple[str, ...],
    authorised_level: int,
    forensic_path: str,
) -> GateDecision:
    approval_token_ids = tuple(
        envelope.scan_types[scan_type].approval_token
        for scan_type in allowed_scan_types
        if scan_type in envelope.scan_types
    )
    decision_id: int | None = None
    if req.db_path:
        conn = init_db(req.db_path)
        try:
            decision_id = save_gate_decision(
                conn,
                envelope_id=envelope.envelope_id,
                approval_token_ids=approval_token_ids,
                scan_type=req.scan_type,
                domain=req.domain,
                client_id=req.client_id,
                requested_level=req.requested_level,
                authorised_level=authorised_level,
                target_basis=target_basis,
                decision=decision,
                reason=reason,
                surface=req.surface,
                job_id=req.job_id,
                run_id=req.run_id,
            )
            if (
                decision == "allowed"
                and target_basis == "consented_client"
                and req.client_id
            ):
                existing = conn.execute(
                    """
                    SELECT 1 FROM conversion_events
                     WHERE cvr = ? AND event_type = 'valdi_gate2_first_pass'
                     LIMIT 1
                    """,
                    (req.client_id,),
                ).fetchone()
                if existing is None:
                    record_conversion_event(
                        conn,
                        req.client_id,
                        "valdi_gate2_first_pass",
                        source="valdi_gate",
                        payload={
                            "domain": req.domain,
                            "job_id": req.job_id,
                            "requested_level": req.requested_level,
                        },
                    )
        finally:
            conn.close()
    return GateDecision(
        decision_id=decision_id,
        envelope_id=envelope.envelope_id,
        approval_token_ids=approval_token_ids,
        scan_type=req.scan_type,
        requested_level=req.requested_level,
        authorised_level=authorised_level,
        target_basis=target_basis,
        decision=decision,
        reason=reason,
        forensic_path=forensic_path,
        allowed_scan_types=allowed_scan_types,
    )


def gate_or_raise(req: ScanRequest) -> GateDecision:
    envelope = req.envelope or get_current_envelope()
    if req.requested_level > envelope.max_level:
        reason = (
            f"Requested level {req.requested_level} exceeds worker envelope max_level "
            f"{envelope.max_level}"
        )
        forensic_path = _write_forensic_log(req, "blocked", reason, "unknown")
        decision = _persist_decision(
            req,
            envelope,
            "blocked",
            reason,
            "unknown",
            tuple(),
            envelope.max_level,
            forensic_path,
        )
        raise GateDeniedError(decision.reason)

    allowed_scan_types = tuple(sorted(get_scan_functions_for_level(req.requested_level)))
    missing = [scan_type for scan_type in allowed_scan_types if scan_type not in envelope.scan_types]
    if missing:
        reason = f"Envelope missing approved scan types: {missing}"
        forensic_path = _write_forensic_log(req, "blocked", reason, "unknown")
        _persist_decision(
            req,
            envelope,
            "blocked",
            reason,
            "unknown",
            tuple(),
            envelope.max_level,
            forensic_path,
        )
        raise GateDeniedError(reason)

    if req.surface == "runner":
        if not req.confirmed:
            reason = "Operator confirmation missing for prospecting batch"
            forensic_path = _write_forensic_log(req, "blocked", reason, "prospect")
            _persist_decision(
                req,
                envelope,
                "blocked",
                reason,
                "prospect",
                tuple(),
                req.requested_level,
                forensic_path,
            )
            raise GateDeniedError(reason)
        reason = "Prospecting batch approved"
        forensic_path = _write_forensic_log(req, "allowed", reason, "prospect")
        return _persist_decision(
            req,
            envelope,
            "allowed",
            reason,
            "prospect",
            allowed_scan_types,
            req.requested_level,
            forensic_path,
        )

    robots_allowed = req.robots_allowed
    if robots_allowed is not True:
        reason = "robots.txt denies automated access"
        forensic_path = _write_forensic_log(req, "blocked", reason, "prospect")
        _persist_decision(
            req,
            envelope,
            "blocked",
            reason,
            "prospect",
            tuple(),
            0,
            forensic_path,
        )
        raise GateDeniedError(reason)

    if req.requested_level == 0:
        reason = "Level 0 scan approved"
        forensic_path = _write_forensic_log(req, "allowed", reason, "prospect")
        return _persist_decision(
            req,
            envelope,
            "allowed",
            reason,
            "prospect",
            allowed_scan_types,
            0,
            forensic_path,
        )

    if req.client_data_dir is None:
        raise GateDeniedError("client_data_dir required for Level 1+ gate checks")

    consent: ConsentCheckResult = check_consent(
        client_dir=Path(req.client_data_dir),
        client_id=req.client_id or "",
        domain=req.domain,
        level_requested=req.requested_level,
    )
    target_basis = (
        "synthetic_target"
        if "Synthetic target" in consent.reason
        else "consented_client"
    )
    if not consent.allowed:
        forensic_path = _write_forensic_log(req, "blocked", consent.reason, target_basis)
        _persist_decision(
            req,
            envelope,
            "blocked",
            consent.reason,
            target_basis,
            tuple(),
            consent.level_authorised,
            forensic_path,
        )
        raise GateDeniedError(consent.reason)

    reason = consent.reason
    forensic_path = _write_forensic_log(req, "allowed", reason, target_basis)
    return _persist_decision(
        req,
        envelope,
        "allowed",
        reason,
        target_basis,
        allowed_scan_types,
        consent.level_authorised,
        forensic_path,
    )
