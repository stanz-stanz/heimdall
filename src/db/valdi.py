"""Persistence helpers for Valdi runtime artifacts."""

from __future__ import annotations

import json
import sqlite3

from src.db.connection import _now


def save_valdi_envelope(
    conn: sqlite3.Connection,
    *,
    envelope_id: str,
    surface: str,
    validated_at: str,
    max_level: int,
    instance_id: str,
    pid: int,
    code_version: str,
    registry_hash: str,
    approval_token_ids: tuple[str, ...],
    scan_types: dict,
) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO valdi_envelopes
            (envelope_id, surface, validated_at, max_level, instance_id, pid,
             code_version, registry_hash, approval_token_ids_json, scan_types_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            envelope_id,
            surface,
            validated_at,
            max_level,
            instance_id,
            pid,
            code_version,
            registry_hash,
            json.dumps(list(approval_token_ids)),
            json.dumps(scan_types, sort_keys=True),
            _now(),
        ),
    )
    conn.commit()


def save_gate_decision(
    conn: sqlite3.Connection,
    *,
    envelope_id: str,
    approval_token_ids: tuple[str, ...],
    scan_type: str,
    domain: str,
    client_id: str | None,
    requested_level: int,
    authorised_level: int,
    target_basis: str,
    decision: str,
    reason: str,
    surface: str,
    job_id: str | None = None,
    run_id: str | None = None,
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO valdi_gate_decisions
            (envelope_id, approval_token_ids_json, scan_type, domain, client_id,
             requested_level, authorised_level, target_basis, decision, reason,
             surface, job_id, run_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            envelope_id,
            json.dumps(list(approval_token_ids)),
            scan_type,
            domain,
            client_id,
            requested_level,
            authorised_level,
            target_basis,
            decision,
            reason,
            surface,
            job_id,
            run_id,
            _now(),
        ),
    )
    conn.commit()
    return int(cursor.lastrowid)
