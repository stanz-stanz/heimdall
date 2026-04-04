"""DB-backed client history -- SQLite replacement for JSON-based ClientHistory.

Reuses DeltaDetector and RemediationTracker unchanged. Stores finding lifecycle
in the normalised finding_definitions + finding_occurrences tables instead of
per-client JSON files.
"""

from __future__ import annotations

import sqlite3
from datetime import date

from loguru import logger

from src.client_memory.delta import DeltaDetector
from src.client_memory.models import DeltaResult, FindingRecord
from src.db.connection import _now
from src.db.findings import (
    get_open_occurrences,
    log_status_transition,
    resolve_occurrence,
    upsert_definition,
    upsert_occurrence,
)

class DBClientHistory:
    """Manages client history via SQLite instead of JSON files.

    Drop-in replacement for ClientHistory when the storage backend is the
    normalised client database (finding_definitions + finding_occurrences).
    DeltaDetector is reused unchanged -- this class only differs in how
    previous/current findings are loaded and persisted.
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        delta_detector: DeltaDetector | None = None,
    ) -> None:
        self.conn = conn
        self.delta = delta_detector or DeltaDetector()

    def record_scan(
        self,
        cvr: str,
        domain: str,
        brief: dict,
        scan_id: str | None = None,
    ) -> DeltaResult:
        """Record a scan, run delta detection, update DB.

        Args:
            cvr: Client CVR number.
            domain: Domain that was scanned.
            brief: Scan brief dict containing a ``findings`` list.
            scan_id: Optional scan_history.scan_id for audit linkage.

        Returns:
            DeltaResult with new, recurring, and resolved lists.

        Workflow:
            1. Load open occurrences from DB -> convert to FindingRecord list
            2. Run DeltaDetector.detect_delta() (unchanged logic)
            3. Persist: NEW -> upsert_definition + upsert_occurrence + log
                       RECURRING -> upsert_occurrence (bumps scan_count)
                       RESOLVED -> resolve_occurrence + log
            4. Return DeltaResult
        """
        today = _now()[:10]  # YYYY-MM-DD

        # Load previous open findings from DB
        db_rows = get_open_occurrences(self.conn, domain)
        previous_records = [self._row_to_finding_record(row) for row in db_rows]

        # Current findings from the brief
        current_findings = brief.get("findings", [])

        # Run delta detection (DeltaDetector is unchanged)
        delta = self.delta.detect_delta(previous_records, current_findings)

        # Persist NEW findings
        for finding in delta.new:
            fid = finding.get("_finding_id", "") or self.delta.generate_finding_id(
                finding.get("severity", ""), finding.get("description", ""),
            )

            # Create/ensure definition exists
            upsert_definition(
                self.conn,
                finding_hash=fid,
                severity=finding.get("severity", ""),
                description=finding.get("description", ""),
                risk=finding.get("risk", ""),
                cve_id=finding.get("cve_id"),
                plugin_slug=finding.get("plugin_slug"),
                provenance=finding.get("provenance"),
                category=finding.get("category"),
                first_seen_at=today,
            )

            # Create occurrence
            occ_id = upsert_occurrence(
                self.conn,
                cvr=cvr,
                domain=domain,
                finding_hash=fid,
                confidence=finding.get("confidence"),
                status="open",
                first_seen_at=today,
                last_seen_at=today,
                first_scan_id=scan_id,
                last_scan_id=scan_id,
            )

            log_status_transition(
                self.conn, occ_id, None, "open",
                f"scan:{scan_id or 'unknown'}",
            )

        # Persist RECURRING findings (bump last_seen)
        for finding in delta.recurring:
            fid = finding.get("_finding_id", "") or self.delta.generate_finding_id(
                finding.get("severity", ""), finding.get("description", ""),
            )
            upsert_occurrence(
                self.conn,
                cvr=cvr,
                domain=domain,
                finding_hash=fid,
                last_seen_at=today,
                last_scan_id=scan_id,
            )

        # Persist RESOLVED findings
        for record in delta.resolved:
            if record._occurrence_id:
                resolve_occurrence(
                    self.conn, record._occurrence_id, today, scan_id,
                )
                log_status_transition(
                    self.conn, record._occurrence_id,
                    "open", "resolved",
                    f"scan:{scan_id or 'unknown'}",
                )

        self.conn.commit()

        logger.bind(context={
            "cvr": cvr,
            "domain": domain,
            "scan_id": scan_id,
            "new_count": len(delta.new),
            "recurring_count": len(delta.recurring),
            "resolved_count": len(delta.resolved),
        }).info("db_delta_detected")

        return delta

    def get_open_findings(self, domain: str) -> list[FindingRecord]:
        """Get all non-resolved findings for a domain.

        Args:
            domain: The domain to query.

        Returns:
            List of FindingRecord objects with _occurrence_id set.
        """
        rows = get_open_occurrences(self.conn, domain)
        return [self._row_to_finding_record(row) for row in rows]

    def get_stale_findings(
        self, domain: str, days: int = 14,
    ) -> list[FindingRecord]:
        """Get findings open longer than threshold days.

        Args:
            domain: The domain to query.
            days: Minimum age in days to qualify as stale.

        Returns:
            List of FindingRecord objects older than the threshold.
        """
        threshold = date.today()
        findings = self.get_open_findings(domain)
        return [
            f for f in findings
            if f.first_detected
            and (threshold - date.fromisoformat(f.first_detected)).days >= days
        ]

    @staticmethod
    def _row_to_finding_record(row: dict) -> FindingRecord:
        """Convert a DB row (joined occurrence + definition) to FindingRecord.

        The row comes from get_open_occurrences() which JOINs
        finding_occurrences with finding_definitions.

        Args:
            row: Dict with columns from both tables.

        Returns:
            A FindingRecord with _occurrence_id linking back to the DB row.
        """
        return FindingRecord(
            finding_id=row.get("finding_hash", ""),
            description=row.get("description", ""),
            severity=row.get("severity", ""),
            status=row.get("status", "open"),
            first_detected=row.get("first_seen_at", ""),
            last_detected=row.get("last_seen_at", ""),
            risk=row.get("risk", ""),
            provenance=row.get("provenance", ""),
            follow_ups_sent=row.get("follow_ups_sent", 0),
            last_follow_up=row.get("last_follow_up"),
            _occurrence_id=row.get("id"),
        )
