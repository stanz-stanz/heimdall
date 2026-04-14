"""Integration tests that exercise the real dev stack.

These tests run ONLY when the dev stack is up (`make dev-up`). The
session-autouse fixture in ``conftest.py`` fails loud if Redis is
unreachable, so a failure here means either (a) the dev stack isn't
running or (b) the wire format actually broke. Both are signals — no
silent skips.

The bug class we are catching: Redis wire format drift, schema
mismatches, BRPOP/LPUSH behaviour differences between mocked and real
redis-py — the "shipping theater" pattern where unit tests pass but the
stack fails on deploy.
"""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path

import pytest
import redis

from scripts.dev.seed_dev_db import run_seed

pytestmark = pytest.mark.integration


_TEST_PREFIX = "heimdall_test:"


@pytest.fixture
def redis_client(dev_redis_url: str):
    """Yield a real Redis client pointed at the dev stack."""
    client = redis.from_url(dev_redis_url, decode_responses=True)
    yield client
    # Clean up any keys we created under the test prefix.
    keys = client.keys(f"{_TEST_PREFIX}*")
    if keys:
        client.delete(*keys)
    client.close()


def test_redis_round_trip(redis_client: redis.Redis) -> None:
    """Baseline: real Redis SET/GET round-trip on the dev stack."""
    key = f"{_TEST_PREFIX}round_trip_{uuid.uuid4().hex}"
    payload = {"domain": "example.dk", "severity": "high"}

    redis_client.set(key, json.dumps(payload), ex=30)
    assert redis_client.get(key) == json.dumps(payload)


def test_redis_pubsub_matches_delivery_wire_format(
    redis_client: redis.Redis,
    dev_redis_url: str,
) -> None:
    """Pub/sub round-trip using the exact channel the delivery bot consumes.

    The delivery runner subscribes to ``client-scan-complete``. This test
    publishes a payload shaped like what the worker emits and asserts the
    subscriber side receives an identical JSON string. If the wire format
    or JSON encoding drifts, this test fires first.
    """
    channel = f"{_TEST_PREFIX}client-scan-complete-{uuid.uuid4().hex}"
    event = {
        "client_id": "dev-client-001",
        "domain": "farylochan.dk",
        "scan_id": uuid.uuid4().hex,
        "completed_at": "2026-04-13T12:00:00Z",
    }

    pubsub = redis_client.pubsub(ignore_subscribe_messages=True)
    pubsub.subscribe(channel)
    publisher = redis.from_url(dev_redis_url, decode_responses=True)
    try:
        publisher.publish(channel, json.dumps(event))

        deadline = time.monotonic() + 5.0
        received = None
        while time.monotonic() < deadline:
            msg = pubsub.get_message(timeout=0.5)
            if msg and msg.get("type") == "message":
                received = msg
                break

        assert received is not None, "pubsub message not received within 5s"
        assert received["channel"] == channel
        assert json.loads(received["data"]) == event
    finally:
        publisher.close()
        pubsub.unsubscribe(channel)
        pubsub.close()


def test_redis_brpop_round_trip(redis_client: redis.Redis) -> None:
    """LPUSH + BRPOP round-trip — the exact queue pattern worker/scheduler use.

    Unit tests mock redis-py; the real BRPOP timeout semantics only show
    up against a live server. If redis-py ever changes BRPOP return
    shape, this test catches it.
    """
    queue = f"{_TEST_PREFIX}queue:operator-commands-{uuid.uuid4().hex}"
    payload = json.dumps({"command": "run-pipeline", "args": {}})

    redis_client.lpush(queue, payload)
    result = redis_client.brpop([queue], timeout=2)

    assert result is not None, f"BRPOP returned None for queue {queue}"
    returned_queue, returned_payload = result
    assert returned_queue == queue
    assert json.loads(returned_payload) == {"command": "run-pipeline", "args": {}}


def test_dev_seed_produces_readable_db(tmp_path: Path) -> None:
    """Seed the dev DB into a tmp path, then read it back with real sqlite3.

    Catches schema drift between ``docs/architecture/client-db-schema.sql``
    and the seed path. If ``init_db`` ever fails to apply the full schema,
    this test fires before the delivery bot crashes on a missing column.
    """
    db_path = tmp_path / "dev-integration.db"
    report = run_seed(db_path=db_path)

    assert report.missing == []
    assert report.inserted == 30
    assert db_path.is_file()

    conn = sqlite3.connect(db_path)
    try:
        count = conn.execute(
            "SELECT COUNT(*) FROM prospects WHERE campaign = 'dev-fixture'"
        ).fetchone()[0]
        buckets = {
            row[0]: row[1]
            for row in conn.execute(
                "SELECT bucket, COUNT(*) FROM prospects "
                "WHERE campaign = 'dev-fixture' GROUP BY bucket"
            )
        }
    finally:
        conn.close()

    assert count == 30
    # Every prospect has a brief with a bucket letter; none should be empty.
    assert "" not in buckets
