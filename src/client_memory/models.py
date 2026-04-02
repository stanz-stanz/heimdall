"""Data models for Client Memory."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

FindingStatus = Literal[
    "open", "acknowledged", "in_progress", "completed", "verified", "resolved",
]
DeltaTag = Literal["new", "recurring", "resolved"]


@dataclass
class FindingRecord:
    """A tracked finding across scans."""

    finding_id: str
    description: str
    severity: str
    status: FindingStatus
    first_detected: str
    last_detected: str
    status_history: list = field(default_factory=list)
    follow_ups_sent: int = 0
    last_follow_up: str | None = None
    resolved_date: str | None = None
    risk: str = ""
    provenance: str = ""
    _occurrence_id: int | None = None

    def to_dict(self) -> dict:
        d = {
            "finding_id": self.finding_id,
            "description": self.description,
            "severity": self.severity,
            "status": self.status,
            "first_detected": self.first_detected,
            "last_detected": self.last_detected,
            "status_history": self.status_history,
            "follow_ups_sent": self.follow_ups_sent,
            "last_follow_up": self.last_follow_up,
            "resolved_date": self.resolved_date,
            "risk": self.risk,
            "provenance": self.provenance,
        }
        if self._occurrence_id is not None:
            d["_occurrence_id"] = self._occurrence_id
        return d

    @classmethod
    def from_dict(cls, data: dict) -> FindingRecord:
        return cls(
            finding_id=data.get("finding_id", ""),
            description=data.get("description", ""),
            severity=data.get("severity", ""),
            status=data.get("status", "open"),
            first_detected=data.get("first_detected", ""),
            last_detected=data.get("last_detected", ""),
            status_history=data.get("status_history", []),
            follow_ups_sent=data.get("follow_ups_sent", 0),
            last_follow_up=data.get("last_follow_up"),
            resolved_date=data.get("resolved_date"),
            risk=data.get("risk", ""),
            provenance=data.get("provenance", ""),
            _occurrence_id=data.get("_occurrence_id"),
        )


@dataclass
class DeltaResult:
    """Result of comparing previous findings against current scan."""

    new: list = field(default_factory=list)
    recurring: list = field(default_factory=list)
    resolved: list = field(default_factory=list)


@dataclass
class ScanEntry:
    """A recorded scan in client history."""

    scan_id: str
    date: str
    total_findings: int
    findings_by_status: dict = field(default_factory=dict)
    delta_summary: dict = field(default_factory=dict)
