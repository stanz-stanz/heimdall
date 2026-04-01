"""SQLite database layer for enriched CVR data.

Follows the ct_collector/db.py pattern: WAL mode, Row factory, batch ops.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS companies (
    cvr TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    address TEXT DEFAULT '',
    postcode TEXT DEFAULT '',
    city TEXT DEFAULT '',
    company_form TEXT DEFAULT '',
    company_form_short TEXT DEFAULT '',
    industry_code TEXT DEFAULT '',
    industry_name_da TEXT DEFAULT '',
    industry_name_en TEXT DEFAULT '',
    phone TEXT DEFAULT '',
    email TEXT DEFAULT '',
    ad_protected INTEGER DEFAULT 0,
    contactable INTEGER DEFAULT 1,
    gdpr_industry_flag INTEGER DEFAULT 0,
    gdpr_industry_reason TEXT DEFAULT '',
    domain TEXT DEFAULT '',
    domain_source TEXT DEFAULT '',
    domain_verified INTEGER DEFAULT 0,
    email_domain TEXT DEFAULT '',
    is_free_webmail INTEGER DEFAULT 0,
    discard_reason TEXT DEFAULT '',
    enriched_at TEXT DEFAULT '',
    source_file TEXT DEFAULT '',
    source_row INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_companies_domain ON companies(domain);
CREATE INDEX IF NOT EXISTS idx_companies_industry ON companies(industry_code);
CREATE INDEX IF NOT EXISTS idx_companies_contactable ON companies(contactable);
CREATE INDEX IF NOT EXISTS idx_companies_gdpr ON companies(gdpr_industry_flag);

CREATE TABLE IF NOT EXISTS domains (
    domain TEXT PRIMARY KEY,
    cvr_count INTEGER DEFAULT 1,
    representative_cvr TEXT DEFAULT '',
    representative_name TEXT DEFAULT '',
    industry_code TEXT DEFAULT '',
    domain_source TEXT DEFAULT '',
    ready_for_scan INTEGER DEFAULT 1,
    created_at TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS enrichment_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cvr TEXT NOT NULL,
    step TEXT NOT NULL,
    input_value TEXT DEFAULT '',
    output_value TEXT DEFAULT '',
    success INTEGER DEFAULT 0,
    detail TEXT DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_log_cvr ON enrichment_log(cvr);
CREATE INDEX IF NOT EXISTS idx_log_step ON enrichment_log(step);
"""


def init_db(db_path: str | Path) -> sqlite3.Connection:
    """Create the database schema and configure WAL mode.

    Returns a read-write connection.
    """
    db_path = str(db_path)
    parent = os.path.dirname(db_path)
    if parent:
        os.makedirs(parent, exist_ok=True)

    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row

    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-8000")
    conn.executescript(_SCHEMA_SQL)

    log.info("Database initialized: %s", db_path)
    return conn


def open_readonly(db_path: str | Path) -> sqlite3.Connection:
    """Open the database in immutable/read-only mode (for Pi5 scheduler)."""
    uri = f"file:{db_path}?immutable=1"
    conn = sqlite3.connect(uri, uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


def _now() -> str:
    """ISO-8601 UTC timestamp."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def upsert_companies(conn: sqlite3.Connection, rows: list[dict]) -> int:
    """Insert or replace companies. Returns count of rows written."""
    if not rows:
        return 0

    cols = [
        "cvr", "name", "address", "postcode", "city", "company_form",
        "industry_code", "industry_name_da", "phone", "email",
        "ad_protected", "source_file", "source_row",
    ]
    placeholders = ", ".join(["?"] * len(cols))
    sql = f"INSERT OR REPLACE INTO companies ({', '.join(cols)}) VALUES ({placeholders})"

    values = [
        tuple(row.get(c, "") for c in cols)
        for row in rows
    ]

    conn.executemany(sql, values)
    conn.commit()
    return len(values)


def update_enrichments(conn: sqlite3.Connection, updates: list[dict]) -> int:
    """Batch-update enrichment fields on companies. Each dict must have 'cvr' key."""
    if not updates:
        return 0

    enrichment_cols = [
        "company_form_short", "industry_name_en",
        "contactable", "gdpr_industry_flag", "gdpr_industry_reason",
        "email_domain", "is_free_webmail", "enriched_at",
    ]

    now = _now()
    count = 0
    for row in updates:
        sets = []
        vals = []
        for col in enrichment_cols:
            if col in row:
                sets.append(f"{col} = ?")
                vals.append(row[col])
        if not sets:
            continue
        sets.append("enriched_at = ?")
        vals.append(now)
        vals.append(row["cvr"])
        conn.execute(
            f"UPDATE companies SET {', '.join(sets)} WHERE cvr = ?",
            vals,
        )
        count += 1

    conn.commit()
    return count


def update_domain(conn: sqlite3.Connection, cvr: str, domain: str,
                  source: str, verified: int) -> None:
    """Set the domain fields on a single company."""
    conn.execute(
        "UPDATE companies SET domain = ?, domain_source = ?, domain_verified = ? WHERE cvr = ?",
        (domain, source, verified, cvr),
    )
    conn.commit()


def log_enrichment(conn: sqlite3.Connection, cvr: str, step: str,
                   input_value: str, output_value: str,
                   success: bool, detail: str = "") -> None:
    """Append an entry to the enrichment audit log."""
    conn.execute(
        "INSERT INTO enrichment_log (cvr, step, input_value, output_value, success, detail, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (cvr, step, input_value, output_value, int(success), detail, _now()),
    )
    conn.commit()


def populate_domains(conn: sqlite3.Connection) -> int:
    """Build the domains table from companies with valid domains.

    Groups by domain, picks a representative CVR (preferring verified + email-derived).
    Returns count of domains inserted.
    """
    conn.execute("DELETE FROM domains")

    rows = conn.execute("""
        SELECT domain, cvr, name, industry_code, domain_source, domain_verified
        FROM companies
        WHERE domain != '' AND discard_reason = ''
        ORDER BY domain_verified DESC, domain_source ASC, cvr
    """).fetchall()

    domain_groups: dict[str, list[sqlite3.Row]] = {}
    for row in rows:
        domain_groups.setdefault(row["domain"], []).append(row)

    now = _now()
    count = 0
    for domain, group in domain_groups.items():
        rep = group[0]  # best candidate (sorted by verified DESC, source ASC)
        conn.execute(
            "INSERT OR REPLACE INTO domains "
            "(domain, cvr_count, representative_cvr, representative_name, "
            "industry_code, domain_source, ready_for_scan, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, 1, ?)",
            (domain, len(group), rep["cvr"], rep["name"],
             rep["industry_code"], rep["domain_source"], now),
        )
        count += 1

    conn.commit()
    return count


def set_domain_not_ready(conn: sqlite3.Connection, domain: str, reason: str) -> None:
    """Mark a domain as not ready for scanning."""
    conn.execute(
        "UPDATE domains SET ready_for_scan = 0 WHERE domain = ?",
        (domain,),
    )
    conn.execute(
        "UPDATE companies SET discard_reason = ? WHERE domain = ? AND discard_reason = ''",
        (reason, domain),
    )
    conn.commit()


def get_scan_ready_domains(conn: sqlite3.Connection) -> list[str]:
    """Return all domains marked ready_for_scan = 1."""
    rows = conn.execute(
        "SELECT domain FROM domains WHERE ready_for_scan = 1 ORDER BY domain"
    ).fetchall()
    return [row["domain"] for row in rows]
