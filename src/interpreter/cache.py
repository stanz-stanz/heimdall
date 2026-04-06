"""Interpretation cache — avoid re-interpreting identical finding sets.

Keyed by a hash of the sorted finding descriptions + tier + language.
If two prospects have the exact same High/Critical findings, the
interpretation is identical regardless of domain or company name.

The per-site summary (greeting, domain name) is injected after cache
lookup by the caller — only the findings interpretation is cached.

Cache invalidation: include a prompt_version in the hash. When the
interpreter prompt changes, bump the version to invalidate stale entries.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone

from loguru import logger

PROMPT_VERSION = "1"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS interpretation_cache (
    finding_hash    TEXT NOT NULL,
    tier            TEXT NOT NULL,
    language        TEXT NOT NULL,
    prompt_version  TEXT NOT NULL,
    interpretation  TEXT NOT NULL,
    model           TEXT NOT NULL DEFAULT '',
    input_tokens    INTEGER DEFAULT 0,
    output_tokens   INTEGER DEFAULT 0,
    created_at      TEXT NOT NULL,
    PRIMARY KEY (finding_hash, tier, language, prompt_version)
);
"""

_DEFAULT_DB_PATH = os.environ.get(
    "INTERPRETATION_CACHE_PATH",
    "data/clients/clients.db",
)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _get_conn(db_path: str | None = None) -> sqlite3.Connection:
    path = db_path or _DEFAULT_DB_PATH
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    conn.commit()
    return conn


def compute_finding_hash(findings: list[dict], tier: str, language: str) -> str:
    """Hash the sorted finding descriptions to create a cache key.

    Only severity, description, risk, and provenance matter for
    interpretation. Domain-specific fields (company_name, etc.) are
    excluded — those are injected by the caller after cache lookup.
    """
    normalized = sorted(
        f"{f.get('severity', '')}|{f.get('description', '')}|{f.get('risk', '')}|{f.get('provenance', '')}"
        for f in findings
    )
    blob = f"v{PROMPT_VERSION}|{tier}|{language}|{'||'.join(normalized)}"
    return hashlib.sha256(blob.encode()).hexdigest()


def get_cached(
    findings: list[dict],
    tier: str,
    language: str,
    db_path: str | None = None,
) -> dict | None:
    """Look up a cached interpretation. Returns parsed dict or None."""
    fh = compute_finding_hash(findings, tier, language)
    conn = _get_conn(db_path)
    row = conn.execute(
        "SELECT interpretation FROM interpretation_cache "
        "WHERE finding_hash = ? AND tier = ? AND language = ? AND prompt_version = ?",
        (fh, tier, language, PROMPT_VERSION),
    ).fetchone()
    conn.close()

    if row:
        logger.debug("interpretation_cache_hit hash={}", fh[:12])
        return json.loads(row["interpretation"])
    return None


def store(
    findings: list[dict],
    tier: str,
    language: str,
    interpretation: dict,
    model: str = "",
    input_tokens: int = 0,
    output_tokens: int = 0,
    db_path: str | None = None,
) -> None:
    """Store an interpretation result in the cache."""
    fh = compute_finding_hash(findings, tier, language)
    conn = _get_conn(db_path)
    conn.execute(
        "INSERT OR REPLACE INTO interpretation_cache "
        "(finding_hash, tier, language, prompt_version, interpretation, "
        " model, input_tokens, output_tokens, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            fh, tier, language, PROMPT_VERSION,
            json.dumps(interpretation, ensure_ascii=False),
            model, input_tokens, output_tokens, _now(),
        ),
    )
    conn.commit()
    conn.close()
    logger.debug("interpretation_cache_store hash={}", fh[:12])


def cache_stats(db_path: str | None = None) -> dict:
    """Return cache size and hit potential stats."""
    conn = _get_conn(db_path)
    row = conn.execute(
        "SELECT COUNT(*) as entries, "
        "SUM(input_tokens + output_tokens) as total_tokens "
        "FROM interpretation_cache WHERE prompt_version = ?",
        (PROMPT_VERSION,),
    ).fetchone()
    conn.close()
    return {
        "entries": row["entries"] or 0,
        "total_tokens_saved_per_hit": (row["total_tokens"] or 0) // max(row["entries"] or 1, 1),
        "prompt_version": PROMPT_VERSION,
    }
