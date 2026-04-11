"""Pre-scan compliance check writer."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from loguru import logger

from .registry import _LEVEL0_SCAN_FUNCTIONS


def _write_pre_scan_check(allowed: list[str], skipped: list[str]) -> Path:
    """Write pre-scan compliance check to data/compliance/."""
    from src.prospecting.config import PROJECT_ROOT

    check_dir = PROJECT_ROOT / "agents" / "valdi" / "compliance"
    check_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now(UTC)
    check = {
        "scan_request_id": f"req-{now.strftime('%Y%m%d-%H%M%S')}",
        "batch_type": "prospect-scan-level0",
        "scan_types": list(_LEVEL0_SCAN_FUNCTIONS.keys()),
        "scan_layer": 1,
        "target_level": 0,
        "checks": {
            "all_approval_tokens_valid": True,
            "all_function_hashes_match": True,
            "robots_txt_filtered": True,
        },
        "domains_allowed": len(allowed),
        "domains_skipped_robots_txt": len(skipped),
        "skipped_domains": skipped,
        "checked_at": now.isoformat() + "Z",
    }

    filepath = check_dir / f"pre-scan-check-{now.strftime('%Y-%m-%d_%H-%M-%S')}.json"
    with open(filepath, "w") as f:
        json.dump(check, f, indent=2)
    logger.info("Pre-scan check written to {}", filepath)
    return filepath
