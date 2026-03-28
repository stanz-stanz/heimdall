"""API entry point: parse args, configure logging, start uvicorn.

Run as::

    python -m src.api.main [--redis-url redis://localhost:6379/0] [--log-format json]
"""

from __future__ import annotations

import argparse
import os
from typing import Optional

import uvicorn

from src.prospecting.logging_config import setup_logging


def _parse_args(argv: Optional[list] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Heimdall Results API")
    parser.add_argument(
        "--redis-url",
        default=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
        help="Redis connection URL (default: redis://localhost:6379/0)",
    )
    parser.add_argument(
        "--results-dir",
        default=os.environ.get("RESULTS_DIR", "/data/results"),
        help="Base directory for result JSON files (default: /data/results)",
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("API_HOST", "0.0.0.0"),
        help="Bind host (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("API_PORT", "8000")),
        help="Bind port (default: 8000)",
    )
    parser.add_argument(
        "--log-format",
        default=os.environ.get("LOG_FORMAT", "json"),
        choices=["json", "text"],
        help="Log format (default: json)",
    )
    parser.add_argument(
        "--log-level",
        default=os.environ.get("LOG_LEVEL", "INFO"),
        help="Log level (default: INFO)",
    )
    return parser.parse_args(argv)


def main(argv: Optional[list] = None) -> None:
    args = _parse_args(argv)
    setup_logging(level=args.log_level, fmt=args.log_format)

    from .app import create_app

    app = create_app(
        redis_url=args.redis_url,
        results_dir=args.results_dir,
    )
    uvicorn.run(app, host=args.host, port=args.port, log_config=None)


if __name__ == "__main__":
    main()
