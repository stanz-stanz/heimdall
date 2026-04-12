"""Docker healthcheck for the CT collector service.

Reads the mtime of a liveness file that ``main.py`` touches on every
incoming CertStream WebSocket message (regardless of the ``.dk`` filter).
Decouples health from data freshness, so low-volume feeds or batch flush
cadence do not cause false alerts.
"""

from __future__ import annotations

import os
import sys
import time


def check(liveness_file: str = "/data/ct/liveness", max_age_seconds: int = 300) -> bool:
    """Return True if *liveness_file* has been touched within *max_age_seconds*."""
    try:
        mtime = os.path.getmtime(liveness_file)
    except OSError:
        return False
    return (time.time() - mtime) < max_age_seconds


def main() -> None:
    """Docker healthcheck entry point: exit 0 (healthy) or 1 (unhealthy)."""
    liveness_file = os.environ.get("LIVENESS_FILE", "/data/ct/liveness")
    healthy = check(liveness_file=liveness_file)
    sys.exit(0 if healthy else 1)


if __name__ == "__main__":
    main()
