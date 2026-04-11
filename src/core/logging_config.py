"""Structured logging configuration for the Heimdall pipeline.

Supports two output formats:
  - text: human-readable colored output
  - json: machine-readable, one JSON object per line

Usage:
    from src.core.logging_config import setup_logging
    setup_logging(level="INFO", fmt="json")
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime

from loguru import logger


def _json_formatter(record: dict) -> str:
    """Format a loguru record as a single-line JSON string.

    Loguru calls format functions with a record dict and expects a format
    template string in return.  We build the JSON, stash it in
    ``record["extra"]["_serialized"]``, and return a template that
    references it — avoiding brace-expansion issues with raw JSON.
    """
    entry: dict = {
        "timestamp": datetime.fromtimestamp(
            record["time"].timestamp(), tz=UTC
        ).isoformat(),
        "level": record["level"].name,
        "module": record["name"] or "root",
        "message": record["message"],
    }

    context = record["extra"].get("context")
    if context is not None:
        entry["context"] = context

    record["extra"]["_serialized"] = json.dumps(entry, default=str, ensure_ascii=False)
    return "{extra[_serialized]}\n"


_TEXT_FORMAT = (
    "{time:HH:mm:ss} [{level.name}] {name}: {message}\n"
)


class _InterceptHandler(logging.Handler):
    """Route stdlib logging records into loguru.

    Installed on the root stdlib logger so that third-party libraries
    (uvicorn, redis, telegram, etc.) emit through loguru's sinks.
    """

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


def setup_logging(
    level: str = "INFO",
    fmt: str = "text",
    sink=None,
) -> None:
    """Configure loguru with the requested format.

    Parameters
    ----------
    level:
        Logging level name (DEBUG, INFO, WARNING, ERROR, CRITICAL).
    fmt:
        ``"text"`` for human-readable output (default),
        ``"json"`` for structured JSON lines.
    sink:
        Output destination. Defaults to ``sys.stderr``.
        Pass a StringIO for testing.
    """
    if sink is None:
        sink = sys.stderr

    logger.remove()

    if fmt == "json":
        logger.add(sink, format=_json_formatter, level=level.upper(), colorize=False)
    else:
        logger.add(sink, format=_TEXT_FORMAT, level=level.upper(), colorize=sink == sys.stderr)

    stdlib_root = logging.getLogger()
    stdlib_root.handlers.clear()
    stdlib_root.addHandler(_InterceptHandler())
    stdlib_root.setLevel(logging.DEBUG)
