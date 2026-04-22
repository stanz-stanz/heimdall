"""End-to-end: operator clicks "Run Pipeline" → scheduler publishes feedback.

This is the integration test that was missing when a dead scheduler
made the button queue commands that silently vanished. The UI in that
state just showed "Starting pipeline..." forever.

What this test proves in one assertion chain:

1. The api process is reachable at the dev port and accepts basic auth.
2. ``POST /console/commands/run-pipeline`` validates + enqueues against
   the real Redis (no mocks).
3. The scheduler daemon (running in the ``scheduler`` container) is
   alive enough to BRPOP the command and publish a status message on
   ``console:command-results`` within a bounded time window.

If any of those links breaks, the "Run Pipeline" button will silently
hang for the operator — and this test is designed to fire first.

Scope guard: even when this runs, the scheduler will proceed to
extract domains (from the dev fixture under HEIMDALL_DEV_DATASET, not
the production enriched DB). We drain ``queue:scan`` and
``queue:enrichment`` in teardown to keep the dev stack idle after
the test.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
import redis

try:
    import httpx
except ImportError:
    httpx = None

pytestmark = pytest.mark.integration


_DEFAULT_API_HOST = "localhost"
_DEFAULT_API_PORT = 8001
_DEFAULT_CONSOLE_USER = "admin"
_COMMAND_RESULTS_CHANNEL = "console:command-results"
_OPERATOR_QUEUE = "queue:operator-commands"
_DOWNSTREAM_QUEUES = ("queue:scan", "queue:enrichment")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _resolve_console_password() -> str:
    """Prefer env var (CI), fall back to the dev secrets file on the laptop."""
    env = os.environ.get("CONSOLE_PASSWORD")
    if env:
        return env
    secret_file = _repo_root() / "infra" / "compose" / "secrets.dev" / "console_password"
    if secret_file.is_file():
        return secret_file.read_text(encoding="utf-8").strip()
    pytest.fail(
        "CONSOLE_PASSWORD not set and "
        f"{secret_file} not present — cannot authenticate against the dev console",
        pytrace=False,
    )


@pytest.fixture(scope="session")
def dev_api_url() -> str:
    host = os.environ.get("HEIMDALL_DEV_API_HOST", _DEFAULT_API_HOST)
    port = int(os.environ.get("HEIMDALL_DEV_API_PORT", _DEFAULT_API_PORT))
    return f"http://{host}:{port}"


@pytest.fixture(scope="session")
def console_auth() -> tuple[str, str]:
    user = os.environ.get("CONSOLE_USER", _DEFAULT_CONSOLE_USER)
    password = _resolve_console_password()
    return user, password


@pytest.fixture
def clean_queues(dev_redis_url: str) -> Iterator[redis.Redis]:
    """Clear operator-commands before the test so we own the queue state.

    We deliberately do NOT clear queue:scan / queue:enrichment — the
    scheduler's pipeline handler is synchronous after the publish ('started'
    fires before enrichment) and continues enriching + scanning the dev
    fixture's 30 domains. Clearing those queues mid-run would leave the
    scheduler waiting forever on a batch-complete signal that never comes.
    The fixture run is small and bounded (~30 domains), so we let it finish.
    """
    client = redis.from_url(dev_redis_url, decode_responses=True)
    client.delete(_OPERATOR_QUEUE)
    try:
        yield client
    finally:
        client.delete(_OPERATOR_QUEUE)
        client.close()


# ---------------------------------------------------------------------------
# The test
# ---------------------------------------------------------------------------


def test_run_pipeline_button_roundtrip(
    dev_api_url: str,
    dev_redis_url: str,
    console_auth: tuple[str, str],
    clean_queues: redis.Redis,
) -> None:
    """Full click → queue → consume → publish-result chain, bounded to 10s.

    Had this test existed earlier, a dead scheduler container would
    have fired the assertion instead of leaving an operator watching
    a spinning progress bar.
    """
    if httpx is None:
        pytest.fail(
            "httpx not installed — required for the integration HTTP client",
            pytrace=False,
        )

    # Subscribe BEFORE queuing to avoid missing an instant publish.
    subscriber = redis.from_url(dev_redis_url, decode_responses=True)
    pubsub = subscriber.pubsub(ignore_subscribe_messages=True)
    pubsub.subscribe(_COMMAND_RESULTS_CHANNEL)

    try:
        # Give Redis a breath to register the subscription (SUBSCRIBE is
        # asynchronous; without this, a very fast publish can land
        # before the server routes it to us).
        time.sleep(0.1)

        # Act: hit the endpoint exactly the way the console does.
        correlation = uuid.uuid4().hex
        with httpx.Client(auth=console_auth, timeout=5.0) as client:
            response = client.post(
                f"{dev_api_url}/console/commands/run-pipeline",
                json={"correlation": correlation},
            )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body.get("status") == "queued"
        assert body.get("command") == "run-pipeline"

        # Assert: scheduler consumes AND publishes a status within 10s.
        # Payload shape published by _publish_result is:
        #   {"type": "command_result", "payload": {"command": ..., "status": ...}, "ts": ...}
        def _matches_run_pipeline(event: dict) -> bool:
            return (event.get("payload") or {}).get("command") == "run-pipeline"

        deadline = time.monotonic() + 10.0
        received: list[dict] = []
        while time.monotonic() < deadline:
            msg = pubsub.get_message(timeout=0.5)
            if not msg or msg.get("type") != "message":
                continue
            try:
                event = json.loads(msg["data"])
            except (json.JSONDecodeError, TypeError):
                continue
            received.append(event)
            if _matches_run_pipeline(event):
                break

        # Helpful failure message — tells the operator which link broke.
        assert any(_matches_run_pipeline(e) for e in received), (
            "No run-pipeline result on console:command-results within 10s. "
            "Likely causes: (a) scheduler container down or dead-locked, "
            "(b) scheduler lost its Redis connection and didn't reconnect, "
            "(c) console endpoint wrote to a different queue name. "
            f"Messages seen: {received}"
        )

        # Queue should be drained — proves scheduler actually BRPOPped.
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            if subscriber.llen(_OPERATOR_QUEUE) == 0:
                break
            time.sleep(0.1)
        assert subscriber.llen(_OPERATOR_QUEUE) == 0, (
            "Command still sitting in queue:operator-commands — "
            "scheduler acknowledged the publish but never BRPOPped it."
        )
    finally:
        pubsub.unsubscribe(_COMMAND_RESULTS_CHANNEL)
        pubsub.close()
        subscriber.close()
