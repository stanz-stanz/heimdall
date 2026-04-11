"""Backward-compatible re-exports — import from src.prospecting.scanners instead.

This module used to contain all scanning logic.  After decomposition (P2-2
through P2-4) the implementations live in ``src.prospecting.scanners.*``.
This shim re-exports every public symbol so that existing consumer imports
(``from src.prospecting.scanner import ...``) continue to work.
"""

from __future__ import annotations

# Re-export stdlib modules that test patches target via ``scanner.<module>``
import json  # noqa: F401
import os  # noqa: F401
import re  # noqa: F401
import shutil  # noqa: F401
import socket  # noqa: F401
import ssl  # noqa: F401
import subprocess  # noqa: F401

import requests  # noqa: F401

# Re-export everything from the scanners package
from .scanners import *  # noqa: F401,F403

# MAX_WORKERS_API was module-level in the old scanner.py and may be
# referenced by tests or benchmarks.
MAX_WORKERS_API = 5  # for rate-limited APIs (crt.sh, GrayHatWarfare)
