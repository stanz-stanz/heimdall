"""Client history — scan recording, delta detection, finding lifecycle.

Orchestrates DeltaDetector and RemediationTracker to maintain per-client
history.json with scan entries, finding records, and message tracking.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timezone
from typing import Optional

from .delta import DeltaDetector
from .models import DeltaResult, FindingRecord, ScanEntry
from .remediation import RemediationTracker
from .storage import AtomicFileStore

log = logging.getLogger(__name__)


def _empty_history(client_id: str) -> dict:
    return {
        "client_id": client_id,
        "scans": [],
        "findings": [],
        "messages": [],
    }


class ClientHistory:
    """Manages client history.json — scans, findings, messages."""

    def __init__(
        self,
        store: AtomicFileStore,
        delta_detector: DeltaDetector,
        remediation_tracker: RemediationTracker,
    ) -> None:
        self.store = store
        self.delta = delta_detector
        self.remediation = remediation_tracker

    def load_history(self, client_id: str) -> dict:
        """Load history.json or return empty structure."""
        data = self.store.read_json(client_id, "history.json")
        if data is None:
            return _empty_history(client_id)
        return data

    def record_scan(
        self,
        client_id: str,
        brief: dict,
    ) -> DeltaResult:
        """Record a scan, run delta detection, update finding records.

        Returns the DeltaResult for downstream consumers (interpreter, composer).
        """
        history = self.load_history(client_id)
        today = date.today().isoformat()
        scan_id = f"scan-{today}-{uuid.uuid4().hex[:8]}"

        # Load previous finding records
        previous_records = [
            FindingRecord.from_dict(f) for f in history.get("findings", [])
        ]

        # Current findings from the brief
        current_findings = brief.get("findings", [])

        # Run delta detection
        delta = self.delta.detect_delta(previous_records, current_findings)

        # Update finding records based on delta
        updated_findings = self._apply_delta(
            previous_records, delta, today, scan_id,
        )

        # Build scan entry
        status_counts: dict[str, int] = {}
        for f in updated_findings:
            status_counts[f.status] = status_counts.get(f.status, 0) + 1

        scan_entry = ScanEntry(
            scan_id=scan_id,
            date=today,
            total_findings=len(current_findings),
            findings_by_status=status_counts,
            delta_summary={
                "new": len(delta.new),
                "recurring": len(delta.recurring),
                "resolved": len(delta.resolved),
            },
        )

        # Update history
        history["scans"].append({
            "scan_id": scan_entry.scan_id,
            "date": scan_entry.date,
            "total_findings": scan_entry.total_findings,
            "findings_by_status": scan_entry.findings_by_status,
            "delta_summary": scan_entry.delta_summary,
        })
        history["findings"] = [f.to_dict() for f in updated_findings]

        self.store.write_json(history, client_id, "history.json")

        log.info("delta_detected", extra={"context": {
            "client_id": client_id,
            "scan_id": scan_id,
            "new_count": len(delta.new),
            "recurring_count": len(delta.recurring),
            "resolved_count": len(delta.resolved),
            "total_findings": len(current_findings),
        }})

        return delta

    def _apply_delta(
        self,
        previous_records: list[FindingRecord],
        delta: DeltaResult,
        today: str,
        scan_id: str,
    ) -> list[FindingRecord]:
        """Apply delta results to finding records."""
        records_by_id: dict[str, FindingRecord] = {
            f.finding_id: f for f in previous_records
        }

        # NEW findings → create records
        for finding in delta.new:
            fid = finding.get("_finding_id", "")
            if not fid:
                fid = self.delta.generate_finding_id(
                    finding.get("severity", ""),
                    finding.get("description", ""),
                )

            # Check if this was previously resolved (regression)
            if fid in records_by_id and records_by_id[fid].status == "resolved":
                record = records_by_id[fid]
                self.remediation.reopen(record, source=f"scan:{scan_id}")
                record.last_detected = today
            else:
                record = FindingRecord(
                    finding_id=fid,
                    description=finding.get("description", ""),
                    severity=finding.get("severity", ""),
                    status="open",
                    first_detected=today,
                    last_detected=today,
                    status_history=[{
                        "status": "open",
                        "date": today,
                        "source": f"scan:{scan_id}",
                    }],
                    risk=finding.get("risk", ""),
                    provenance=finding.get("provenance", ""),
                )
            records_by_id[fid] = record

        # RECURRING findings → update last_detected
        for finding in delta.recurring:
            fid = finding.get("_finding_id", "")
            matched_id = finding.get("_matched_previous_id", fid)
            record = records_by_id.get(matched_id) or records_by_id.get(fid)
            if record:
                record.last_detected = today

        # RESOLVED findings → mark as resolved
        for record in delta.resolved:
            record.status = "resolved"
            record.resolved_date = today
            record.status_history.append({
                "status": "resolved",
                "date": today,
                "source": f"scan:{scan_id}",
            })

        return list(records_by_id.values())

    def get_finding_status(self, client_id: str, finding_id: str) -> Optional[str]:
        """Get the current status of a specific finding."""
        history = self.load_history(client_id)
        for f in history.get("findings", []):
            if f.get("finding_id") == finding_id:
                return f.get("status")
        return None

    def get_open_findings(self, client_id: str) -> list[FindingRecord]:
        """Get all non-resolved findings for a client."""
        history = self.load_history(client_id)
        return [
            FindingRecord.from_dict(f)
            for f in history.get("findings", [])
            if f.get("status") != "resolved"
        ]

    def get_stale_findings(self, client_id: str, days: int = 14) -> list[FindingRecord]:
        """Get findings open longer than threshold days."""
        today = date.today()
        stale = []
        for record in self.get_open_findings(client_id):
            if record.first_detected:
                first = date.fromisoformat(record.first_detected)
                if (today - first).days >= days:
                    stale.append(record)
        return stale

    def record_message(self, client_id: str, message_record: dict) -> None:
        """Append a message record to history."""
        history = self.load_history(client_id)
        history["messages"].append(message_record)
        self.store.write_json(history, client_id, "history.json")
