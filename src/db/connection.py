"""SQLite connection factory for the Heimdall client database.

Follows the enrichment/db.py pattern: WAL mode, Row factory, _now() helper.
Schema is loaded from docs/architecture/client-db-schema.sql rather than
embedded inline (the client DB schema is too large to inline).
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger

# Resolve project root from this file's location:
#   src/db/connection.py -> parents[2] = project root
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SCHEMA_PATH = _PROJECT_ROOT / "docs" / "architecture" / "client-db-schema.sql"

_DEFAULT_DB_PATH = "data/clients/clients.db"


def init_db(db_path: str | Path = _DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Initialize the client database. Creates file and applies schema if needed.

    Args:
        db_path: Path to the SQLite database file. Parent directories are
            created automatically if they do not exist.

    Returns:
        A read-write connection with WAL mode, Row factory, and foreign keys
        enabled.

    Raises:
        FileNotFoundError: If the schema SQL file cannot be found.
    """
    db_path = str(db_path)
    parent = os.path.dirname(db_path)
    if parent:
        os.makedirs(parent, exist_ok=True)

    conn = sqlite3.connect(db_path, timeout=10)
    conn.row_factory = sqlite3.Row

    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA cache_size=-8000")

    schema_sql = _load_schema()
    conn.executescript(schema_sql)

    logger.info("Client database initialized: {}", db_path)
    return conn


def open_readonly(db_path: str | Path) -> sqlite3.Connection:
    """Open the database in immutable/read-only mode.

    Args:
        db_path: Path to an existing SQLite database file.

    Returns:
        A read-only connection with Row factory enabled.
    """
    uri = f"file:{db_path}?immutable=1"
    conn = sqlite3.connect(uri, uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


def _now() -> str:
    """ISO-8601 UTC timestamp.

    Returns:
        Timestamp string in ``YYYY-MM-DDTHH:MM:SSZ`` format.
    """
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_schema() -> str:
    """Read the schema SQL file from the project docs directory.

    Raises:
        FileNotFoundError: If the schema file does not exist at the expected
            path.
    """
    if not _SCHEMA_PATH.is_file():
        raise FileNotFoundError(
            f"Schema file not found: {_SCHEMA_PATH}. "
            f"Expected at docs/architecture/client-db-schema.sql relative to project root."
        )
    return _SCHEMA_PATH.read_text(encoding="utf-8")
