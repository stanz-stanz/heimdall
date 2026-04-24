"""CRUD operations for industries, clients, and client_domains tables.

Follows the enrichment/db.py pattern: thin functions, Row factory,
explicit commits, ISO-8601 timestamps via _now().
"""

from __future__ import annotations

import sqlite3

from src.db.connection import _now

# ---------------------------------------------------------------------------
# Validation constants
# ---------------------------------------------------------------------------

VALID_PLANS: set[str | None] = {None, "watchman", "sentinel"}
VALID_STATUSES: set[str] = {
    "prospect",
    "watchman_pending",
    "watchman_active",
    "watchman_expired",
    "onboarding",
    "active",
    "paused",
    "churned",
}
VALID_ONBOARDING_STAGES: set[str | None] = {
    None,
    "upgrade_interest",
    "pending_payment",
    "pending_consent",
    "pending_scope",
    "provisioning",
}

# Columns on the clients table that callers may set via create/update.
# Excludes cvr (immutable PK) and timestamps (auto-managed).
_CLIENT_MUTABLE_COLS: set[str] = {
    "company_name",
    "industry_code",
    "plan",
    "status",
    "consent_granted",
    "telegram_chat_id",
    "contact_name",
    "contact_email",
    "contact_phone",
    "notes",
    "gdpr_sensitive",
    "gdpr_reasons",
    "preferred_language",
    "trial_started_at",
    "trial_expires_at",
    "onboarding_stage",
    "signup_source",
    "churn_reason",
    "churn_requested_at",
    "churn_purge_at",
    "data_retention_mode",
}

# ---------------------------------------------------------------------------
# Industries
# ---------------------------------------------------------------------------


def upsert_industry(
    conn: sqlite3.Connection,
    code: str,
    name_da: str = "",
    name_en: str = "",
) -> None:
    """INSERT OR REPLACE a single industry row."""
    conn.execute(
        "INSERT OR REPLACE INTO industries (code, name_da, name_en) VALUES (?, ?, ?)",
        (code, name_da, name_en),
    )
    conn.commit()


def bulk_upsert_industries(conn: sqlite3.Connection, rows: list[dict]) -> int:
    """Batch insert from config/industry_codes.json format.

    Accepts two formats:
    - List of dicts with keys: code, name_da, name_en
    - List of dicts with keys: code, name (mapped to name_en)

    Returns count of rows written.
    """
    if not rows:
        return 0

    values = []
    for row in rows:
        code = row.get("code", "")
        name_da = row.get("name_da", "")
        name_en = row.get("name_en", row.get("name", ""))
        values.append((code, name_da, name_en))

    conn.executemany(
        "INSERT OR REPLACE INTO industries (code, name_da, name_en) VALUES (?, ?, ?)",
        values,
    )
    conn.commit()
    return len(values)


# ---------------------------------------------------------------------------
# Clients
# ---------------------------------------------------------------------------


def _validate_plan(plan: str | None) -> None:
    """Raise ValueError if plan is not a recognised value."""
    if plan not in VALID_PLANS:
        raise ValueError(
            f"Invalid plan {plan!r}. Must be one of: {sorted(p for p in VALID_PLANS if p is not None)} or None"
        )


def _validate_status(status: str) -> None:
    """Raise ValueError if status is not a recognised value."""
    if status not in VALID_STATUSES:
        raise ValueError(
            f"Invalid status {status!r}. Must be one of: {sorted(VALID_STATUSES)}"
        )


def _validate_onboarding_stage(stage: str | None) -> None:
    """Raise ValueError if onboarding_stage is not a recognised value."""
    if stage not in VALID_ONBOARDING_STAGES:
        valid = sorted(s for s in VALID_ONBOARDING_STAGES if s is not None)
        raise ValueError(
            f"Invalid onboarding_stage {stage!r}. Must be one of: {valid} or None"
        )


def create_client(
    conn: sqlite3.Connection,
    cvr: str,
    company_name: str,
    **kwargs: object,
) -> dict:
    """Insert a new client row.

    Sets created_at and updated_at automatically. Returns the inserted row
    as a dict.

    Args:
        conn: Database connection.
        cvr: Danish CVR number (primary key).
        company_name: Company name (required).
        **kwargs: Optional columns matching _CLIENT_MUTABLE_COLS
            (excluding company_name which is positional).

    Raises:
        ValueError: If plan or status values are invalid.
        sqlite3.IntegrityError: If CVR already exists.
    """
    plan = kwargs.get("plan")
    _validate_plan(plan)

    status = kwargs.get("status", "prospect")
    _validate_status(status)

    if "onboarding_stage" in kwargs:
        _validate_onboarding_stage(kwargs["onboarding_stage"])  # type: ignore[arg-type]

    now = _now()
    data: dict[str, object] = {
        "cvr": cvr,
        "company_name": company_name,
        "created_at": now,
        "updated_at": now,
    }

    # Merge caller-supplied columns (only recognised ones).
    for key, value in kwargs.items():
        if key in _CLIENT_MUTABLE_COLS:
            data[key] = value

    # Ensure status is set (may have been in kwargs, or defaults).
    data.setdefault("status", "prospect")

    cols = list(data.keys())
    placeholders = ", ".join(["?"] * len(cols))
    sql = f"INSERT INTO clients ({', '.join(cols)}) VALUES ({placeholders})"

    conn.execute(sql, [data[c] for c in cols])
    conn.commit()

    return get_client(conn, cvr)  # type: ignore[return-value]


def get_client(conn: sqlite3.Connection, cvr: str) -> dict | None:
    """Fetch a single client by CVR.

    Returns the row as a dict, or None if not found.
    """
    row = conn.execute("SELECT * FROM clients WHERE cvr = ?", (cvr,)).fetchone()
    return dict(row) if row else None


def update_client(
    conn: sqlite3.Connection,
    cvr: str,
    updates: dict,
) -> dict:
    """Partial update of a client row.

    Cannot change the 'cvr' column. Sets updated_at automatically.
    Returns the updated row as a dict.

    Args:
        conn: Database connection.
        cvr: CVR of the client to update.
        updates: Dict of column -> new value.

    Raises:
        ValueError: If 'cvr' is in updates or plan/status values are invalid.
        KeyError: If the client does not exist.
    """
    if "cvr" in updates:
        raise ValueError("Cannot change the 'cvr' column — it is the immutable primary key")

    if "plan" in updates:
        _validate_plan(updates["plan"])
    if "status" in updates:
        _validate_status(updates["status"])
    if "onboarding_stage" in updates:
        _validate_onboarding_stage(updates["onboarding_stage"])

    # Filter to recognised columns only.
    filtered = {k: v for k, v in updates.items() if k in _CLIENT_MUTABLE_COLS}
    if not filtered:
        # Nothing to update — just return current row.
        client = get_client(conn, cvr)
        if client is None:
            raise KeyError(f"Client with CVR {cvr!r} not found")
        return client

    filtered["updated_at"] = _now()

    set_clause = ", ".join(f"{col} = ?" for col in filtered)
    values = list(filtered.values()) + [cvr]

    conn.execute(f"UPDATE clients SET {set_clause} WHERE cvr = ?", values)
    conn.commit()

    client = get_client(conn, cvr)
    if client is None:
        raise KeyError(f"Client with CVR {cvr!r} not found")
    return client


def list_clients(
    conn: sqlite3.Connection,
    status: str | None = None,
) -> list[dict]:
    """List all clients, optionally filtered by status.

    Returns a list of dicts, one per client row.
    """
    if status is not None:
        rows = conn.execute(
            "SELECT * FROM clients WHERE status = ? ORDER BY company_name",
            (status,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM clients ORDER BY company_name",
        ).fetchall()

    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Client domains
# ---------------------------------------------------------------------------


def add_domain(
    conn: sqlite3.Connection,
    cvr: str,
    domain: str,
    is_primary: int = 1,
) -> None:
    """Add a domain to a client.

    Sets added_at automatically.

    Raises:
        sqlite3.IntegrityError: If the (cvr, domain) pair already exists.
    """
    conn.execute(
        "INSERT INTO client_domains (cvr, domain, is_primary, added_at) VALUES (?, ?, ?, ?)",
        (cvr, domain, is_primary, _now()),
    )
    conn.commit()


def get_domains(conn: sqlite3.Connection, cvr: str) -> list[dict]:
    """Get all domains for a given CVR.

    Returns a list of dicts, one per domain row.
    """
    rows = conn.execute(
        "SELECT * FROM client_domains WHERE cvr = ? ORDER BY is_primary DESC, domain",
        (cvr,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_client_by_domain(conn: sqlite3.Connection, domain: str) -> dict | None:
    """Reverse lookup: find the client that owns a given domain.

    Returns the client dict, or None if the domain is not registered.
    """
    row = conn.execute(
        "SELECT c.* FROM clients c "
        "JOIN client_domains cd ON c.cvr = cd.cvr "
        "WHERE cd.domain = ?",
        (domain,),
    ).fetchone()
    return dict(row) if row else None
