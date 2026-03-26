"""Structured logging configuration for the Heimdall pipeline.

Supports two output formats:
  - text: human-readable, same as previous basicConfig format
  - json: machine-readable, one JSON object per line

Usage:
    from .logging_config import setup_logging
    setup_logging(level="INFO", fmt="json")
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone


class JSONFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects.

    Output keys: timestamp, level, module, message, context (optional).
    The ``context`` dict is pulled from ``record.context`` if present
    (passed via ``extra={"context": {...}}``).
    """

    def format(self, record: logging.LogRecord) -> str:
        entry: dict = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "module": record.name,
            "message": record.getMessage(),
        }

        context = getattr(record, "context", None)
        if context is not None:
            entry["context"] = context

        return json.dumps(entry, default=str, ensure_ascii=False)


_TEXT_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_TEXT_DATEFMT = "%H:%M:%S"


def setup_logging(level: str = "INFO", fmt: str = "text") -> None:
    """Configure the root logger with the requested format.

    Parameters
    ----------
    level:
        Logging level name (DEBUG, INFO, WARNING, ERROR, CRITICAL).
    fmt:
        ``"text"`` for human-readable output (default),
        ``"json"`` for structured JSON lines.
    """
    root = logging.getLogger()

    # Clear existing handlers to avoid duplicate output on repeated calls
    root.handlers.clear()

    handler = logging.StreamHandler()

    if fmt == "json":
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(logging.Formatter(_TEXT_FORMAT, datefmt=_TEXT_DATEFMT))

    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.addHandler(handler)
