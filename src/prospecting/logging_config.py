"""DEPRECATED — use ``src.core.logging_config`` instead.

This shim re-exports ``setup_logging`` so that internal prospecting
imports (``from .logging_config import setup_logging``) keep working
until they are migrated.
"""

from src.core.logging_config import setup_logging  # noqa: F401
