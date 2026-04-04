"""Delta detection — compare previous findings against current scan.

Identifies NEW, RECURRING, and RESOLVED findings by matching on a
deterministic finding ID (sha256 of severity + description) with
fuzzy fallback for minor description changes across scans.
"""

from __future__ import annotations

import hashlib
import re
from difflib import SequenceMatcher
from typing import Optional

from loguru import logger

from .models import DeltaResult, FindingRecord

# Default fuzzy match threshold (overridable via config)
_DEFAULT_THRESHOLD = 0.85


class DeltaDetector:
    """Compare previous finding records against current scan findings."""

    def __init__(self, fuzzy_threshold: float = _DEFAULT_THRESHOLD) -> None:
        self.fuzzy_threshold = fuzzy_threshold

    @staticmethod
    def generate_finding_id(severity: str, description: str) -> str:
        """Deterministic ID from severity + normalized description."""
        normalized = f"{severity.lower().strip()}:{normalize_description(description)}"
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:12]

    def detect_delta(
        self,
        previous_findings: list[FindingRecord],
        current_findings: list[dict],
    ) -> DeltaResult:
        """Compare previous records against current scan findings.

        Returns a DeltaResult with new, recurring, and resolved lists.
        """
        # Build lookup of previous open/non-resolved findings
        prev_by_id: dict[str, FindingRecord] = {}
        for f in previous_findings:
            if f.status != "resolved":
                prev_by_id[f.finding_id] = f

        # Deduplicate current findings by ID
        seen_ids: set[str] = set()
        deduped_current: list[dict] = []
        for finding in current_findings:
            fid = self.generate_finding_id(
                finding.get("severity", ""),
                finding.get("description", ""),
            )
            if fid not in seen_ids:
                seen_ids.add(fid)
                deduped_current.append(finding)
            else:
                logger.bind(context={
                    "finding_id": fid, "description": finding.get("description", ""),
                }).debug("delta_duplicate_finding")

        new: list[dict] = []
        recurring: list[dict] = []

        for finding in deduped_current:
            fid = self.generate_finding_id(
                finding.get("severity", ""),
                finding.get("description", ""),
            )
            finding["_finding_id"] = fid

            # Exact ID match
            if fid in prev_by_id:
                recurring.append(finding)
                prev_by_id.pop(fid)
                continue

            # Fuzzy match: same severity, similar description
            matched = self._fuzzy_match_previous(finding, prev_by_id)
            if matched:
                finding["_matched_previous_id"] = matched.finding_id
                recurring.append(finding)
                prev_by_id.pop(matched.finding_id)
                continue

            new.append(finding)

        # Everything remaining in prev_by_id → RESOLVED
        resolved = list(prev_by_id.values())

        return DeltaResult(new=new, recurring=recurring, resolved=resolved)

    def _fuzzy_match_previous(
        self,
        finding: dict,
        prev_by_id: dict[str, FindingRecord],
    ) -> Optional[FindingRecord]:
        """Try fuzzy matching against remaining previous findings."""
        severity = finding.get("severity", "").lower().strip()
        desc = normalize_description(finding.get("description", ""))

        best_match: Optional[FindingRecord] = None
        best_ratio = 0.0

        for record in prev_by_id.values():
            if record.severity.lower().strip() != severity:
                continue

            prev_desc = normalize_description(record.description)
            ratio = SequenceMatcher(None, desc, prev_desc).ratio()

            if ratio >= self.fuzzy_threshold and ratio > best_ratio:
                best_ratio = ratio
                best_match = record

        return best_match


def normalize_description(description: str) -> str:
    """Lowercase, strip, collapse whitespace."""
    text = description.lower().strip()
    text = re.sub(r"\s+", " ", text)
    return text
