from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from src.consent.validator import ConsentCheckResult
from src.db.connection import init_db
from src.prospecting.scanners.registry import _SCAN_TYPE_FUNCTIONS, _init_scan_type_map
from src.valdi import GateDeniedError, ScanRequest, gate_or_raise
from src.valdi.envelope import get_current_envelope, validate_and_persist_envelope
from src.valdi.models import GateDecision
from src.worker.cache import ScanCache
from src.worker.scan_job import execute_scan_job


def test_validate_and_persist_envelope_writes_db(tmp_path: Path) -> None:
    db_path = tmp_path / "clients.db"
    envelope = validate_and_persist_envelope(0, surface="worker", db_path=str(db_path))
    assert get_current_envelope().envelope_id == envelope.envelope_id

    conn = init_db(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM valdi_envelopes WHERE envelope_id = ?",
            (envelope.envelope_id,),
        ).fetchone()
        assert row is not None
        assert row["max_level"] == 0
    finally:
        conn.close()


def test_gate_first_pass_emitted_once(tmp_path: Path) -> None:
    db_path = tmp_path / "clients.db"
    validate_and_persist_envelope(1, surface="worker", db_path=str(db_path))

    consent = ConsentCheckResult(
        allowed=True,
        client_id="12345678",
        domain="example.dk",
        level_requested=1,
        level_authorised=1,
        reason="Consent active",
        authorised_by_role="owner",
    )
    req = ScanRequest(
        surface="worker",
        scan_type="passive_domain_scan_orchestrator",
        requested_level=1,
        domain="example.dk",
        client_id="12345678",
        client_data_dir=str(tmp_path),
        db_path=str(db_path),
        robots_allowed=True,
    )
    with patch("src.valdi.gate.check_consent", return_value=consent):
        first = gate_or_raise(req)
        second = gate_or_raise(req)

    assert first.decision == "allowed"
    assert second.decision == "allowed"

    conn = init_db(db_path)
    try:
        count = conn.execute(
            "SELECT COUNT(*) FROM conversion_events WHERE event_type = 'valdi_gate2_first_pass'"
        ).fetchone()[0]
        assert count == 1
    finally:
        conn.close()


def test_execute_scan_job_requires_gate_context(tmp_path: Path) -> None:
    cache = ScanCache.__new__(ScanCache)
    cache.hits = 0
    cache.misses = 0
    cache._available = False
    cache._redis = None
    with pytest.raises(RuntimeError, match="without Valdi gate context"):
        execute_scan_job(
            {
                "job_id": "job-1",
                "domain": "example.dk",
                "client_id": "prospect",
                "level": 0,
                "robots_allowed": True,
            },
            cache,
        )
