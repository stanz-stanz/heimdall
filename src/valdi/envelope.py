from __future__ import annotations

import hashlib
import inspect
import json
import os
import sqlite3
import subprocess
import uuid
from datetime import UTC, datetime
from pathlib import Path

from loguru import logger

from src.db.connection import init_db
from src.db.valdi import save_valdi_envelope
from src.prospecting.scanners.registry import (
    build_validated_scan_catalog,
    get_scan_functions_for_level,
)
from .models import Envelope, EnvelopeScanType

_CURRENT_ENVELOPE: Envelope | None = None
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_LOG_DIR = _PROJECT_ROOT / "logs" / "valdi"


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _registry_hash(scan_catalog: dict[str, dict]) -> str:
    payload = json.dumps(scan_catalog, sort_keys=True)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _code_version() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=_PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except Exception:
        return "unknown"


def _write_boot_log(
    *,
    surface: str,
    max_level: int,
    success: bool,
    scan_catalog: dict[str, dict] | None,
    reason: str,
    instance_id: str,
) -> str:
    log_dir = Path(os.environ.get("HEIMDALL_VALDI_LOG_DIR", str(_DEFAULT_LOG_DIR)))
    log_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y-%m-%d_%H-%M-%S")
    suffix = "" if success else "_REJECTED"
    path = log_dir / f"{ts}_{surface}_boot{suffix}.md"
    lines = [
        "# Valdi Worker Boot Envelope",
        "",
        f"- `surface`: {surface}",
        f"- `max_level`: {max_level}",
        f"- `instance_id`: {instance_id}",
        f"- `pid`: {os.getpid()}",
        f"- `validated_at`: {_now_iso()}",
        f"- `result`: {'approved' if success else 'rejected'}",
        f"- `reason`: {reason}",
    ]
    if scan_catalog is not None:
        lines.append(f"- `registry_hash`: {_registry_hash(scan_catalog)}")
        lines.append("")
        lines.append("## Scan Types")
        for scan_type, info in sorted(scan_catalog.items()):
            lines.append(
                f"- `{scan_type}` level={info['level']} token={info['approval_token']}"
            )
    try:
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except PermissionError:
        fallback_dir = Path("/tmp/heimdall-valdi-logs")
        fallback_dir.mkdir(parents=True, exist_ok=True)
        path = fallback_dir / path.name
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)


def get_current_envelope() -> Envelope:
    if _CURRENT_ENVELOPE is None:
        raise RuntimeError("Valdi envelope not initialised")
    return _CURRENT_ENVELOPE


def validate_and_persist_envelope(
    max_level: int,
    *,
    surface: str = "worker",
    db_path: str | None = None,
) -> Envelope:
    global _CURRENT_ENVELOPE

    instance_id = f"{surface}-{uuid.uuid4().hex[:12]}"
    try:
        scan_catalog = build_validated_scan_catalog(max_level=max_level)
    except Exception as exc:
        log_path = _write_boot_log(
            surface=surface,
            max_level=max_level,
            success=False,
            scan_catalog=None,
            reason=str(exc),
            instance_id=instance_id,
        )
        logger.error("Valdi envelope validation failed: {} ({})", exc, log_path)
        raise

    validated_at = _now_iso()
    envelope_id = str(uuid.uuid4())
    approval_token_ids = tuple(
        info["approval_token"] for _, info in sorted(scan_catalog.items())
    )
    envelope = Envelope(
        envelope_id=envelope_id,
        validated_at=validated_at,
        max_level=max_level,
        instance_id=instance_id,
        pid=os.getpid(),
        code_version=_code_version(),
        registry_hash=_registry_hash(scan_catalog),
        approval_token_ids=approval_token_ids,
        scan_types={
            scan_type: EnvelopeScanType(
                function_hash=info["function_hash"],
                helper_hash=info.get("helper_hash"),
                level=info["level"],
                approval_token=info["approval_token"],
            )
            for scan_type, info in scan_catalog.items()
        },
    )
    _write_boot_log(
        surface=surface,
        max_level=max_level,
        success=True,
        scan_catalog=scan_catalog,
        reason="validated",
        instance_id=instance_id,
    )

    if db_path:
        conn = init_db(db_path)
        try:
            save_valdi_envelope(
                conn,
                envelope_id=envelope.envelope_id,
                surface=surface,
                validated_at=envelope.validated_at,
                max_level=envelope.max_level,
                instance_id=envelope.instance_id,
                pid=envelope.pid,
                code_version=envelope.code_version,
                registry_hash=envelope.registry_hash,
                approval_token_ids=envelope.approval_token_ids,
                scan_types=scan_catalog,
            )
        finally:
            conn.close()

    if surface == "worker":
        _CURRENT_ENVELOPE = envelope
    return envelope
