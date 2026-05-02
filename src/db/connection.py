"""SQLite connection factory for the Heimdall client database.

Follows the enrichment/db.py pattern: WAL mode, Row factory, _now() helper.
Schema is loaded from docs/architecture/client-db-schema.sql rather than
embedded inline (the client DB schema is too large to inline).

Stage A.5 (2026-05-01): connections opened via :func:`init_db` are
:class:`HeimdallConnection` instances (a thin subclass of
:class:`sqlite3.Connection`). The subclass exposes ``__dict__`` so
per-connection actor metadata for the audit-trigger ``audit_context()``
SQL function can live as a regular attribute (``conn._audit_ctx``). Base
``sqlite3.Connection`` does not allow arbitrary attributes. The
``audit_context`` UDF is registered automatically on every connection
opened through this module — see :func:`src.db.audit_context.install_audit_context`.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from loguru import logger

# Resolve project root from this file's location:
#   src/db/connection.py -> parents[2] = project root
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SCHEMA_PATH = _PROJECT_ROOT / "docs" / "architecture" / "client-db-schema.sql"

_DEFAULT_DB_PATH = "data/clients/clients.db"


class HeimdallConnection(sqlite3.Connection):
    """Subclass that adds ``__dict__`` for per-connection state.

    The Stage A.5 audit-trigger machinery stores actor metadata on
    ``conn._audit_ctx`` so a Python-side UDF (``audit_context()``) can
    read it inside trigger bodies. Base ``sqlite3.Connection`` rejects
    attribute assignment because it has no ``__dict__``; subclassing
    fixes that without touching SQLite behaviour.
    """

    pass


def init_db(db_path: str | Path = _DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Initialize the client database. Creates file and applies schema if needed.

    Args:
        db_path: Path to the SQLite database file. Parent directories are
            created automatically if they do not exist.

    Returns:
        A :class:`HeimdallConnection` with WAL mode, Row factory, foreign
        keys enabled, and the ``audit_context()`` UDF registered. The
        UDF is mandatory — Stage A.5 ``config_changes`` triggers crash on
        first fire if it is missing.

    Raises:
        FileNotFoundError: If the schema SQL file cannot be found.
    """
    db_path = str(db_path)
    parent = os.path.dirname(db_path)
    if parent:
        os.makedirs(parent, exist_ok=True)

    conn = sqlite3.connect(db_path, timeout=10, factory=HeimdallConnection)
    conn.row_factory = sqlite3.Row

    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA cache_size=-8000")

    # Register the audit_context() UDF BEFORE the schema bundle runs.
    # The bundle's CREATE TRIGGER statements compile against the
    # presence of this function (SQLite verifies at fire time, not
    # create time, but registering early is harmless and guards
    # against any future SQLite tightening).
    # Lazy-imported because audit_context imports nothing from this
    # module today, but circular imports are easy to introduce later.
    from src.db.audit_context import install_audit_context

    install_audit_context(conn)

    schema_sql = _load_schema()
    conn.executescript(schema_sql)

    # Apply pending ALTER TABLE migrations that cannot live in CREATE TABLE
    # IF NOT EXISTS (e.g. columns added to existing tables). Lazy-imported
    # because src.db.migrate imports init_db from this module.
    from src.db.migrate import apply_pending_migrations

    added = apply_pending_migrations(conn)
    if added:
        logger.info("Applied pending column migrations: {}", ", ".join(added))

    # Checkpoint the WAL so immutable=1 readers (e.g. the API container
    # mounting client-data:/data/clients:ro) observe the new columns.
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    logger.info("Client database initialized: {}", db_path)
    return conn


def verify_integrity(conn: sqlite3.Connection) -> bool:
    """Run PRAGMA integrity_check on the database.

    Returns:
        True if the database passes integrity checks, False otherwise.
    """
    try:
        result = conn.execute("PRAGMA integrity_check").fetchone()
        if result and result[0] == "ok":
            return True
        logger.critical("Database integrity check FAILED: {}", result)
        return False
    except sqlite3.DatabaseError as exc:
        logger.critical("Database integrity check error: {}", exc)
        return False


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


def connect_clients_audited(
    db_path: str | Path,
    *,
    timeout: float = 10.0,
) -> sqlite3.Connection:
    """Open ``clients.db`` for read-write under the A.5 trigger contract.

    Returns a :class:`HeimdallConnection` with the ``audit_context()``
    UDF registered, so any UPDATE / DELETE on a tier-1 table can fire
    its ``config_changes`` trigger without the
    ``no such function: audit_context`` crash that a plain
    ``sqlite3.connect`` would produce.

    Distinct from :func:`init_db`: this helper does NOT load the schema
    bundle and does NOT call ``apply_pending_migrations``. It is the
    canonical opener for the api container, which intentionally never
    runs ``init_db()`` on ``clients.db`` (see ``src/api/app.py``'s
    lifespan comment: the api would race ALTER TABLE statements against
    the writer containers' ``init_db()`` and lose with
    ``OperationalError`` — the column-add phase has TOCTOU between
    ``PRAGMA table_info`` and ``ALTER TABLE``). Schema is the writer
    containers' responsibility; the api just connects, registers the
    UDF, and gets out of the way.

    Use :func:`init_db` from writer containers (scheduler, worker,
    delivery, retention runner). Use :func:`connect_clients_audited`
    from the api container for any code path that mutates a tier-1
    table.

    Args:
        db_path: Path to an existing SQLite database file. Parent dir
            is NOT auto-created — that's a writer concern.
        timeout: ``sqlite3.connect`` busy-wait timeout in seconds.
            Default 10s matches :func:`init_db`.

    Returns:
        A :class:`HeimdallConnection` with WAL-friendly defaults
        (``foreign_keys=ON``, Row factory) and ``audit_context()``
        registered. Caller owns the connection lifecycle.
    """
    conn = sqlite3.connect(
        str(db_path), timeout=timeout, factory=HeimdallConnection
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")

    # Lazy import for the same reason init_db does it (defensive against
    # future circular dependencies; today audit_context.py imports only
    # stdlib).
    from src.db.audit_context import install_audit_context

    install_audit_context(conn)
    return conn


def _now() -> str:
    """ISO-8601 UTC timestamp.

    Returns:
        Timestamp string in ``YYYY-MM-DDTHH:MM:SSZ`` format.
    """
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


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
