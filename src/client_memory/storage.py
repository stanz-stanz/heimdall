"""Atomic file store — thread-safe JSON read/write.

Write operations use a write-to-temp-then-rename pattern to prevent
partial writes from corrupting data on crash or power loss.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


class AtomicFileStore:
    """Thread-safe JSON file storage with atomic writes."""

    def __init__(self, base_dir: str) -> None:
        self.base_dir = Path(base_dir)

    def _resolve(self, *parts: str) -> Path:
        return self.base_dir.joinpath(*parts)

    def read_json(self, *path_parts: str) -> Optional[dict]:
        """Read a JSON file. Returns None if missing or corrupt."""
        path = self._resolve(*path_parts)
        if not path.is_file():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                log.warning("storage_not_dict", extra={"context": {
                    "path": str(path), "type": type(data).__name__,
                }})
                return None
            return data
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("storage_read_error", extra={"context": {
                "path": str(path), "error": str(exc),
            }})
            return None

    def write_json(self, data: dict, *path_parts: str) -> Path:
        """Write JSON atomically: temp file → fsync → rename.

        Creates parent directories if needed. Returns the written path.
        """
        path = self._resolve(*path_parts)
        path.parent.mkdir(parents=True, exist_ok=True)

        fd, tmp_path = tempfile.mkstemp(
            dir=str(path.parent), suffix=".tmp", prefix=".cm_",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.rename(tmp_path, str(path))
        except Exception:
            # Clean up temp file on failure
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

        return path

    def exists(self, *path_parts: str) -> bool:
        return self._resolve(*path_parts).is_file()
