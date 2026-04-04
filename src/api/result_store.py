"""Disk-based scan result reader.

Reads from the file tree at ``{base_dir}/{client_id}/{domain}/{date}.json``
written by the worker process.
"""

from __future__ import annotations

import json
from pathlib import Path

from loguru import logger


class ResultStore:
    """Read-only access to scan result JSON files on disk."""

    def __init__(self, base_dir: str) -> None:
        self._base = Path(base_dir)

    def get_latest(self, client_id: str, domain: str) -> dict | None:
        """Return the most recent result for a domain, or None."""
        domain_dir = self._base / client_id / domain
        if not domain_dir.is_dir():
            return None
        files = sorted(domain_dir.glob("*.json"), key=lambda p: p.stem, reverse=True)
        if not files:
            return None
        return self._read_file(files[0])

    def get_by_date(self, client_id: str, domain: str, date: str) -> dict | None:
        """Return result for a specific date, or None."""
        path = self._base / client_id / domain / f"{date}.json"
        if not path.is_file():
            return None
        return self._read_file(path)

    def list_domains(
        self, client_id: str, limit: int = 50, offset: int = 0,
    ) -> tuple[list[dict], int]:
        """Return (domain summaries, total count) for a client, paginated."""
        client_dir = self._base / client_id
        if not client_dir.is_dir():
            return [], 0
        domains = sorted(d.name for d in client_dir.iterdir() if d.is_dir())
        total = len(domains)
        page = domains[offset:offset + limit]
        summaries = []
        for domain in page:
            latest = self.get_latest(client_id, domain)
            if latest:
                brief = latest.get("brief", {})
                summaries.append({
                    "domain": domain,
                    "status": latest.get("status"),
                    "scan_date": brief.get("scan_date"),
                    "bucket": brief.get("bucket"),
                    "findings_count": len(brief.get("findings", [])),
                })
        return summaries, total

    def list_dates(self, client_id: str, domain: str) -> list[str]:
        """Return available scan dates for a domain, newest first."""
        domain_dir = self._base / client_id / domain
        if not domain_dir.is_dir():
            return []
        return sorted(
            (f.stem for f in domain_dir.glob("*.json")),
            reverse=True,
        )

    def _read_file(self, path: Path) -> dict | None:
        """Read and parse a JSON result file. Returns None on error."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            logger.bind(context={"path": str(path), "error": str(exc)}).warning("result_file_error")
            return None
