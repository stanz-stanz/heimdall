"""One-time crt.sh bulk import for historical .dk certificate data.

Run as::

    python -m src.ct_collector.backfill [--db-path /data/ct/certificates.db]

Fetches all certificate records from crt.sh for .dk domains and inserts
them into the local CT database.  Supports resumption via a progress file.
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from src.prospecting.logging_config import setup_logging

from .db import init_db, insert_certificates_batch

log = logging.getLogger(__name__)

_CRT_SH_URL = "https://crt.sh"
_USER_AGENT = "Heimdall-EASM/0.1 (CT backfill)"


def _fetch_crtsh_page(domain_pattern: str, timeout: int = 60) -> List[Dict[str, Any]]:
    """Fetch certificate records from crt.sh for a domain pattern.

    Parameters
    ----------
    domain_pattern:
        crt.sh search pattern, e.g. ``%.dk`` or ``%.a.dk``.
    timeout:
        HTTP request timeout in seconds.

    Returns
    -------
    list[dict]
        Raw crt.sh JSON response entries.
    """
    resp = requests.get(
        f"{_CRT_SH_URL}/",
        params={"q": domain_pattern, "output": "json"},
        timeout=timeout,
        headers={"User-Agent": _USER_AGENT},
    )
    resp.raise_for_status()

    data = resp.json()
    if not isinstance(data, list):
        return []
    return data


def _backfill_chunk(
    conn: Any,
    domain_pattern: str,
    progress: Dict[str, Any],
    progress_file: str,
) -> int:
    """Fetch and insert certificates for a single domain pattern.

    Uses exponential backoff on failure (5s base, 120s max).
    Returns the number of rows inserted.
    """
    backoff = 5.0
    max_backoff = 120.0
    max_retries = 5

    for attempt in range(max_retries):
        try:
            entries = _fetch_crtsh_page(domain_pattern)
            break
        except (requests.RequestException, ValueError) as exc:
            if attempt == max_retries - 1:
                log.warning(
                    "backfill_chunk_failed",
                    extra={"context": {"pattern": domain_pattern, "error": str(exc)}},
                )
                return 0

            log.info(
                "backfill_retry",
                extra={"context": {"pattern": domain_pattern, "attempt": attempt + 1, "backoff_s": backoff}},
            )
            time.sleep(backoff)
            backoff = min(backoff * 2, max_backoff)

    if not entries:
        return 0

    now = datetime.now(timezone.utc).isoformat()
    certs = []
    for entry in entries:
        cn = entry.get("common_name", "")
        if not cn:
            continue
        certs.append({
            "common_name": cn,
            "issuer_name": entry.get("issuer_name", ""),
            "not_before": entry.get("not_before", ""),
            "not_after": entry.get("not_after", ""),
            "san_domains": [],  # crt.sh JSON doesn't include full SAN list
            "seen_at": now,
        })

    inserted = insert_certificates_batch(conn, certs)

    # Update progress
    progress["completed_patterns"].append(domain_pattern)
    progress["total_inserted"] += inserted
    progress["last_updated"] = now
    _save_progress(progress, progress_file)

    log.info(
        "backfill_chunk_complete",
        extra={"context": {"pattern": domain_pattern, "fetched": len(entries), "inserted": inserted}},
    )
    return inserted


def _save_progress(progress: Dict[str, Any], progress_file: str) -> None:
    """Save progress to file for resume support."""
    parent = os.path.dirname(progress_file)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(progress_file, "w", encoding="utf-8") as f:
        json.dump(progress, f, indent=2, default=str, ensure_ascii=False)


def _load_progress(progress_file: str) -> Dict[str, Any]:
    """Load progress from file, or return fresh progress dict."""
    try:
        with open(progress_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {
            "completed_patterns": [],
            "total_inserted": 0,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "last_updated": None,
        }


def backfill(
    db_path: str = "/data/ct/certificates.db",
    progress_file: str = "/data/ct/backfill_progress.json",
) -> None:
    """Main backfill entry point.

    Fetches .dk certificates from crt.sh using alphabetic chunking to
    stay within crt.sh response limits.  Resumes from where it left off
    using the progress file.
    """
    conn = init_db(db_path)
    progress = _load_progress(progress_file)
    completed = set(progress.get("completed_patterns", []))

    # Generate patterns: %.dk, %.a.dk through %.z.dk, plus %.0.dk through %.9.dk
    patterns = ["%.dk"]
    for c in "abcdefghijklmnopqrstuvwxyz0123456789":
        patterns.append(f"%.{c}.dk")

    remaining = [p for p in patterns if p not in completed]

    if not remaining:
        log.info("backfill_already_complete", extra={"context": {"total_inserted": progress["total_inserted"]}})
        conn.close()
        return

    log.info(
        "backfill_starting",
        extra={"context": {"total_patterns": len(patterns), "remaining": len(remaining)}},
    )

    total_inserted = 0
    for i, pattern in enumerate(remaining, 1):
        log.info(
            "backfill_progress",
            extra={"context": {"pattern": pattern, "step": i, "of": len(remaining)}},
        )

        inserted = _backfill_chunk(conn, pattern, progress, progress_file)
        total_inserted += inserted

        # Rate limit between requests
        if i < len(remaining):
            time.sleep(5)

    conn.close()
    log.info(
        "backfill_complete",
        extra={"context": {"total_inserted": total_inserted, "patterns_processed": len(remaining)}},
    )


def main() -> None:
    """CLI entry point for backfill."""
    import argparse

    parser = argparse.ArgumentParser(description="Backfill CT database from crt.sh")
    parser.add_argument(
        "--db-path",
        default=os.environ.get("CT_DB_PATH", "/data/ct/certificates.db"),
        help="Path to SQLite CT database",
    )
    parser.add_argument(
        "--progress-file",
        default=os.environ.get("BACKFILL_PROGRESS_FILE", "/data/ct/backfill_progress.json"),
        help="Path to progress file for resume support",
    )
    parser.add_argument(
        "--log-format",
        choices=("text", "json"),
        default=os.environ.get("LOG_FORMAT", "json"),
        help="Log output format (default: json)",
    )
    parser.add_argument(
        "--log-level",
        default=os.environ.get("LOG_LEVEL", "INFO"),
        help="Log level (default: INFO)",
    )
    args = parser.parse_args()
    setup_logging(level=args.log_level, fmt=args.log_format)

    backfill(db_path=args.db_path, progress_file=args.progress_file)


if __name__ == "__main__":
    main()
