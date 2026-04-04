"""Remediation tracker — state machine for finding lifecycle.

Transitions: open → acknowledged → in_progress → completed → verified → resolved
Regression: any state → open (when a finding reappears after resolution)

Valid transitions are loaded from config/remediation_states.json.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from loguru import logger

from .models import FindingRecord, FindingStatus

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
        conn: Optional[sqlite3.Connection] = None,
        occurrence_id: Optional[int] = None,
    ) -> FindingRecord:
        """Validate and apply a forward transition.

        Args:
            finding: The finding to transition.
            new_status: Target status (must be a valid successor).
            source: What triggered the change (e.g. "scan", "operator").
            timestamp: ISO-8601 timestamp. Defaults to now (UTC).
            conn: Optional DB connection. When provided together with
                ``occurrence_id``, the transition is also written to the
                ``finding_status_log`` table and the occurrence row is updated.
            occurrence_id: Optional PK of the ``finding_occurrences`` row.

        Raises:
            InvalidTransition: If the transition is not allowed.
        """
        if not self.is_valid_transition(finding.status, new_status):
            raise InvalidTransition(
                f"Cannot transition from '{finding.status}' to '{new_status}'. "
                f"Valid targets: {self.transitions.get(finding.status, [])}"
            )

        old_status = finding.status
        ts = timestamp or datetime.now(timezone.utc).isoformat()
        finding.status = new_status
        finding.status_history.append({
            "status": new_status,
            "date": ts,
            "source": source,
        })

        if new_status == "resolved":
            finding.resolved_date = ts

        logger.bind(context={
            "finding_id": finding.finding_id,
            "from_status": old_status,
            "to_status": new_status,
            "source": source,
        }).info("remediation_transition")

        if conn is not None and occurrence_id is not None:
            from src.db.findings import log_status_transition, update_occurrence_status

            update_occurrence_status(conn, occurrence_id, new_status)
            log_status_transition(conn, occurrence_id, old_status, new_status, source)

        return finding

    def reopen(
        self,
        finding: FindingRecord,
        source: str,
        timestamp: Optional[str] = None,
        conn: Optional[sqlite3.Connection] = None,
        occurrence_id: Optional[int] = None,
    ) -> FindingRecord:
        """Regression: finding reappeared. Any state -> open.

        Args:
            finding: The finding to reopen.
            source: What triggered the regression (e.g. "scan:regression").
            timestamp: ISO-8601 timestamp. Defaults to now (UTC).
            conn: Optional DB connection. When provided together with
                ``occurrence_id``, the regression is also written to the
                ``finding_status_log`` table and the occurrence row is updated.
            occurrence_id: Optional PK of the ``finding_occurrences`` row.
        """
        ts = timestamp or datetime.now(timezone.utc).isoformat()
        old_status = finding.status
        finding.status = self.regression_target
        finding.resolved_date = None
        finding.status_history.append({
            "status": self.regression_target,
            "date": ts,
            "source": source,
        })

        logger.bind(context={
            "finding_id": finding.finding_id,
            "from_status": old_status,
            "to_status": self.regression_target,
            "source": source,
        }).info("remediation_regression")

        if conn is not None and occurrence_id is not None:
            from src.db.findings import log_status_transition, update_occurrence_status

            update_occurrence_status(conn, occurrence_id, self.regression_target)
            log_status_transition(conn, occurrence_id, old_status, self.regression_target, source)

        return finding
