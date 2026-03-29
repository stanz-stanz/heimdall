"""Remediation tracker — state machine for finding lifecycle.

Transitions: open → acknowledged → in_progress → completed → verified → resolved
Regression: any state → open (when a finding reappears after resolution)

Valid transitions are loaded from config/remediation_states.json.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .models import FindingRecord, FindingStatus

log = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "remediation_states.json"

_DEFAULT_TRANSITIONS = {
    "open": ["acknowledged"],
    "acknowledged": ["in_progress"],
    "in_progress": ["completed"],
    "completed": ["verified"],
    "verified": ["resolved"],
}


class InvalidTransition(ValueError):
    """Raised when a remediation state transition is not valid."""


class RemediationTracker:
    """State machine for finding remediation lifecycle."""

    def __init__(self, config_path: Optional[Path] = None) -> None:
        config = self._load_config(config_path or _CONFIG_PATH)
        self.transitions: dict[str, list[str]] = config.get("transitions", _DEFAULT_TRANSITIONS)
        self.regression_target: str = config.get("regression_target", "open")
        self.escalation_threshold_days: int = config.get("escalation_threshold_days", 14)

    @staticmethod
    def _load_config(path: Path) -> dict:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            pass
        return {}

    def is_valid_transition(self, from_status: str, to_status: str) -> bool:
        """Check if a forward transition is valid."""
        allowed = self.transitions.get(from_status, [])
        return to_status in allowed

    def transition(
        self,
        finding: FindingRecord,
        new_status: FindingStatus,
        source: str,
        timestamp: Optional[str] = None,
    ) -> FindingRecord:
        """Validate and apply a forward transition.

        Raises InvalidTransition if the transition is not allowed.
        """
        if not self.is_valid_transition(finding.status, new_status):
            raise InvalidTransition(
                f"Cannot transition from '{finding.status}' to '{new_status}'. "
                f"Valid targets: {self.transitions.get(finding.status, [])}"
            )

        ts = timestamp or datetime.now(timezone.utc).isoformat()
        finding.status = new_status
        finding.status_history.append({
            "status": new_status,
            "date": ts,
            "source": source,
        })

        if new_status == "resolved":
            finding.resolved_date = ts

        log.info("remediation_transition", extra={"context": {
            "finding_id": finding.finding_id,
            "from_status": finding.status_history[-2]["status"] if len(finding.status_history) > 1 else "unknown",
            "to_status": new_status,
            "source": source,
        }})

        return finding

    def reopen(
        self,
        finding: FindingRecord,
        source: str,
        timestamp: Optional[str] = None,
    ) -> FindingRecord:
        """Regression: finding reappeared. Any state → open."""
        ts = timestamp or datetime.now(timezone.utc).isoformat()
        old_status = finding.status
        finding.status = self.regression_target
        finding.resolved_date = None
        finding.status_history.append({
            "status": self.regression_target,
            "date": ts,
            "source": source,
        })

        log.info("remediation_regression", extra={"context": {
            "finding_id": finding.finding_id,
            "from_status": old_status,
            "to_status": self.regression_target,
            "source": source,
        }})

        return finding
