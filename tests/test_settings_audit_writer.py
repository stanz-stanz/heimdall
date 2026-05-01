"""Stage A.5 spec §4.1.8 — file-backed settings writer-wrapper.

Four tests:

1. ``test_settings_put_writes_audit_row`` — PUT ``/console/settings/filters``
   with a new payload writes the file atomically and emits one
   ``clients.audit_log`` row (``action='config.file_write'``,
   ``target_id='filters.json'``, ``payload_json={old_sha256, new_sha256}``).
2. ``test_settings_put_no_change_skips_audit`` — re-PUTting byte-
   identical content (after the same JSON normalisation the handler
   applies) lands no audit row.
3. ``test_settings_put_records_request_id`` — when ``request.state.
   request_id`` is populated (which the X-Request-ID middleware will
   do in commit (3)), the audit row's ``request_id`` matches. This
   commit (1) test exercises the wrapper helper directly to lock the
   contract before the middleware lands.
4. ``test_settings_put_initial_write_old_sha_null`` — first PUT against
   a config dir with no pre-existing file produces a row whose
   ``payload_json.old_sha256`` is ``None``.

The audit row lives in ``clients.audit_log`` (NOT trigger-watched) —
config_changes is for tier-1 DB tables, file-backed settings need a
separate hand-written wrapper. The wrapper opens via
``connect_clients_audited`` so the connection still satisfies the
A.5 trigger contract for any sibling writes in the same handler
(today none — settings is a pure file-write surface).
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import fakeredis
import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.api.console import _write_settings_audit_row
from src.db.connection import init_db
from tests._console_auth_helpers import (
    login_console_client,
    seed_console_operator,
)


@pytest.fixture
def db_path(tmp_path):
    """Create a writable clients.db with the A.5 schema applied."""
    db_file = tmp_path / "clients.db"
    conn = init_db(str(db_file))
    conn.close()
    return str(db_file)


@pytest.fixture
def config_dir(tmp_path):
    """Create a config dir with one pre-existing file (filters.json).

    Tests that need a fresh dir (test_settings_put_initial_write_old_sha_null)
    delete the file inside the test body.
    """
    cfg = tmp_path / "config"
    cfg.mkdir()
    # Use canonical formatting so a no-change PUT actually round-trips
    # to byte-identical content. The handler json.dumps with indent=2
    # + trailing newline.
    (cfg / "filters.json").write_text(
        json.dumps({"bucket": ["A", "B"]}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return cfg


@pytest.fixture
def client(db_path, config_dir, tmp_path, monkeypatch):
    """Authenticated TestClient pointed at a writable clients.db."""
    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr("redis.Redis.from_url", lambda *a, **kw: fake)
    monkeypatch.chdir(tmp_path)

    config_link = tmp_path / "config"
    if not config_link.exists():
        config_link.symlink_to(config_dir)

    console_db_path = tmp_path / "console.db"
    monkeypatch.setenv("CONSOLE_DB_PATH", str(console_db_path))
    monkeypatch.setenv("HEIMDALL_COOKIE_SECURE", "0")

    app = create_app(
        redis_url="redis://fake:6379/0",
        results_dir=str(tmp_path / "results"),
        briefs_dir=str(tmp_path / "briefs"),
    )
    app.state.db_path = db_path

    with TestClient(app) as tc:
        seed_console_operator(console_db_path)
        login_console_client(tc)
        yield tc


def _read_audit_log_rows(db_path: str, *, action: str | None = None) -> list[dict]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        if action is None:
            sql = "SELECT * FROM audit_log ORDER BY id"
            params: tuple = ()
        else:
            sql = (
                "SELECT * FROM audit_log WHERE action = ? ORDER BY id"
            )
            params = (action,)
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def test_settings_put_writes_audit_row(client, db_path, config_dir):
    """PUT new content writes the file atomically and emits one audit row."""
    new_payload = {"bucket": ["A", "B", "C"], "min_findings": 5}

    resp = client.put("/console/settings/filters", json=new_payload)
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"status": "saved", "name": "filters"}

    # File on disk reflects the merged content.
    on_disk = json.loads((config_dir / "filters.json").read_text(encoding="utf-8"))
    assert on_disk["bucket"] == ["A", "B", "C"]
    assert on_disk["min_findings"] == 5

    rows = _read_audit_log_rows(db_path, action="config.file_write")
    assert len(rows) == 1
    row = rows[0]
    assert row["target_type"] == "settings_file"
    assert row["target_id"] == "filters.json"
    assert row["actor_kind"] == "operator"
    assert row["operator_id"] is not None  # populated by SessionAuth
    assert row["session_id"] is not None

    payload = json.loads(row["payload_json"])
    assert "old_sha256" in payload
    assert "new_sha256" in payload
    assert payload["old_sha256"] is not None
    assert payload["new_sha256"] is not None
    # Both digests are valid SHA-256 hex strings.
    for key in ("old_sha256", "new_sha256"):
        assert len(payload[key]) == 64
        int(payload[key], 16)
    # The new digest matches the on-disk content.
    on_disk_bytes = (config_dir / "filters.json").read_bytes()
    assert payload["new_sha256"] == hashlib.sha256(on_disk_bytes).hexdigest()


def test_settings_put_no_change_skips_audit(client, db_path, config_dir):
    """Re-PUTting byte-identical merged content lands NO audit row."""
    # Read what the handler will produce given the seeded body.
    existing = json.loads(
        (config_dir / "filters.json").read_text(encoding="utf-8")
    )
    # The handler does {**existing, **body} — passing the seed back as
    # the body produces an identical merged dict and the json.dumps
    # output is byte-identical.

    resp = client.put("/console/settings/filters", json=existing)
    assert resp.status_code == 200

    rows = _read_audit_log_rows(db_path, action="config.file_write")
    assert rows == [], (
        "no-op writes (old_sha == new_sha) must NOT emit an audit row"
    )


def test_settings_put_records_request_id(db_path):
    """When request.state.request_id is populated, the audit row's
    ``request_id`` column matches.

    The X-Request-ID middleware lands in commit (3); this test pins
    the wrapper's contract by exercising the helper directly with a
    request_id kwarg. Once the middleware mounts, the commit (3)
    integration test (``test_request_id_propagated_across_two_dbs``)
    re-asserts the same plumbing through the HTTP surface."""
    _write_settings_audit_row(
        db_path,
        filename="delivery.json",
        old_sha256="a" * 64,
        new_sha256="b" * 64,
        operator_id=42,
        session_id=7,
        request_id="abc-123",
        source_ip="127.0.0.1",
        user_agent="test-agent",
    )

    rows = _read_audit_log_rows(db_path, action="config.file_write")
    assert len(rows) == 1
    row = rows[0]
    assert row["request_id"] == "abc-123"
    assert row["operator_id"] == 42
    assert row["session_id"] == 7
    assert row["target_id"] == "delivery.json"


def test_settings_put_initial_write_old_sha_null(client, db_path, config_dir):
    """First PUT (no pre-existing file) → audit row carries old_sha256=null."""
    # Remove the seeded filters.json so this PUT is the initial write.
    (config_dir / "filters.json").unlink()
    assert not (config_dir / "filters.json").exists()

    resp = client.put(
        "/console/settings/filters",
        json={"bucket": ["A"]},
    )
    assert resp.status_code == 200

    rows = _read_audit_log_rows(db_path, action="config.file_write")
    assert len(rows) == 1
    payload = json.loads(rows[0]["payload_json"])
    assert payload["old_sha256"] is None
    assert payload["new_sha256"] is not None
    # Confirm the file exists and the digest matches.
    new_bytes = (config_dir / "filters.json").read_bytes()
    assert payload["new_sha256"] == hashlib.sha256(new_bytes).hexdigest()
