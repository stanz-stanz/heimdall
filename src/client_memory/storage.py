"""Atomic file store — thread-safe JSON read/write.

Write operations use a write-to-temp-then-rename pattern to prevent
partial writes from corrupting data on crash or power loss.
"""

from __future__ import annotations

import fcntl
import json
import logging
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


class AtomicFileStore:
    """Thread-safe JSON file storage with atomic writes."""

    def __init__(self, base_dir: str) -> None:
        self.base_dir = Path(base_dir)

    def _resolve(self, *parts: str) -> Path:
        resolved = self.base_dir.joinpath(*parts).resolve()
        if not resolved.is_relative_to(self.base_dir.resolve()):
            raise ValueError(f"Path escapes base directory: {parts}")
        return resolved

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
            os.replace(tmp_path, str(path))
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

    @contextmanager
    def lock(self, *path_parts: str):
        """Advisory file lock for read-modify-write operations.

        Usage::

            with store.lock(client_id):
                data = store.read_json(client_id, "history.json")
                data["key"] = "value"
                store.write_json(data, client_id, "history.json")
        """
        lock_path = self.base_dir.joinpath(*path_parts, ".lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_file = open(lock_path, "w")
        try:
            fcntl.flock(lock_file, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(lock_file, fcntl.LOCK_UN)
            lock_file.close()
