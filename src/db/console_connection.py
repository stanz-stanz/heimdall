"""SQLite connection factory for the Heimdall console database.

Counterpart to ``src/db/connection.py`` (which owns ``clients.db``).
Stage A introduces a separate physical SQLite file ``console.db`` for
operator identity, sessions, and the auth-event audit log — see the
2026-04-27 evening D2 decision in ``docs/decisions/log.md`` and the
Stage A implementation spec at
``docs/architecture/stage-a-implementation-spec.md`` §2.5.

Mirror of the ``init_db()`` shape: WAL mode, Row factory, FK pragma,
schema loaded from a separate file via ``executescript``.

Slice 1 ships the schema + factories only. The Argon2id-backed
operator-#0 seed is deferred to slice 2 (it requires the
``argon2-cffi`` dependency that's not in ``requirements.txt`` yet).
The ``operators`` table stays empty until that slice lands; the api
keeps using the legacy ``BasicAuthMiddleware`` from
``src/api/app.py:53-91`` for now.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from loguru import logger

# Resolve project root from this file's location:
#   src/db/console_connection.py -> parents[2] = project root
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SCHEMA_PATH = _PROJECT_ROOT / "docs" / "architecture" / "console-db-schema.sql"

# Relative default mirrors ``src/db/connection._DEFAULT_DB_PATH``
# (``data/clients/clients.db``). The container compose env sets
# CONSOLE_DB_PATH=/data/console/console.db absolute so production
# resolves to the named-volume mount; tests running from the project
# root create a local data/console/ that's gitignored.
DEFAULT_CONSOLE_DB_PATH = "data/console/console.db"


def init_db_console(db_path: str | Path = DEFAULT_CONSOLE_DB_PATH) -> sqlite3.Connection:
    """Initialize the console database.

    Creates the file (and parent directories) and applies the schema
    if needed. Idempotent — every CREATE TABLE / INDEX in the schema
    file uses ``IF NOT EXISTS``, so re-running this on an existing
    console.db is a no-op.

    Args:
        db_path: Path to the SQLite database file. Parent directories
            are created automatically if they do not exist.

    Returns:
        A read-write connection with WAL mode, Row factory, and
        foreign keys enabled.

    Raises:
        FileNotFoundError: If the schema SQL file cannot be found.
            Fail-loud rather than create an empty DB silently — a
            missing schema file means the api Docker image was built
            without the file in its COPY layer (see Dockerfile.api).
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

    # Checkpoint the WAL so any reader opening this DB immediately
    # afterwards sees the new schema rather than an empty main DB +
    # the pending WAL.
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    logger.info("Console database initialized: {}", db_path)
    return conn


def get_console_conn(db_path: str | Path = DEFAULT_CONSOLE_DB_PATH) -> sqlite3.Connection:
    """Open a fresh read-write connection to console.db.

    Caller is responsible for closing. The schema is NOT re-applied —
    use this for runtime queries / writes after :func:`init_db_console`
    has run at least once.
    """
    conn = sqlite3.connect(str(db_path), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _load_schema() -> str:
    """Read the console-db schema SQL file from the project docs directory.

    Raises:
        FileNotFoundError: If the schema file does not exist at the
            expected path. This usually means the Docker image was
            built without ``COPY docs/architecture/console-db-schema.sql``
            in ``Dockerfile.api`` — fix the Dockerfile, do not paper
            over the missing file.
    """
    if not _SCHEMA_PATH.is_file():
        raise FileNotFoundError(
            f"Console schema file not found: {_SCHEMA_PATH}. "
            "Ensure infra/compose/Dockerfile.api copies "
            "docs/architecture/console-db-schema.sql into the runtime image."
        )
    return _SCHEMA_PATH.read_text(encoding="utf-8")
