"""Tests for scheduler daemon crash resilience and error message quality."""

import json
from pathlib import Path
from unittest.mock import patch, call

import fakeredis
import pytest

import src.scheduler.daemon as daemon_mod
from src.scheduler.daemon import run_daemon


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_redis():
    return fakeredis.FakeRedis(decode_responses=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _push_command(fake_redis, command: str) -> None:
    """Push a single command onto the queue and arrange daemon to stop after it."""
    cmd = {"command": command, "payload": {}, "ts": "2026-04-11T10:00:00"}
    fake_redis.lpush("queue:operator-commands", json.dumps(cmd))


def _make_stopping_brpop(fake_redis):
    """Return a brpop wrapper that stops the daemon after the first real pop."""
    original = fake_redis.brpop
    call_count = [0]

    def limited(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] > 1:
            daemon_mod._shutdown_requested = True
            return None
        return original(*args, **kwargs)

    return limited


# ---------------------------------------------------------------------------
# Bug 1: crash resilience
# ---------------------------------------------------------------------------

class TestPublishFailureDoesNotCrashDaemon:
    def test_publish_failure_in_except_does_not_crash(self, fake_redis):
        """
        If _handle_run_pipeline raises AND _publish_result raises (Redis down),
        the daemon must NOT propagate the second exception out of the while loop.
        """
        _push_command(fake_redis, "run-pipeline")

        with patch("src.scheduler.daemon.redis.Redis.from_url", return_value=fake_redis), \
             patch("src.scheduler.daemon.signal.signal"), \
             patch("src.scheduler.daemon._handle_run_pipeline",
                   side_effect=RuntimeError("pipeline exploded")), \
             patch("src.scheduler.daemon._publish_result",
                   side_effect=ConnectionError("Redis is down")):

            daemon_mod._shutdown_requested = False

            # Arrange: stop the loop after the first command is consumed.
            fake_redis.brpop = _make_stopping_brpop(fake_redis)

            # Must not raise — the daemon should absorb both exceptions.
            run_daemon(
                redis_url="redis://fake:6379/0",
                input_path=Path("/fake/input.xlsx"),
                filters_path=Path("/fake/filters.json"),
            )
            # If we reach this line, the daemon did not crash — test passes.


# ---------------------------------------------------------------------------
# Bug 2: error message includes exception detail
# ---------------------------------------------------------------------------

class TestErrorMessageIncludesExceptionDetail:
    def test_error_message_includes_exception_detail(self, fake_redis):
        """
        When _handle_run_pipeline raises, the message passed to _publish_result
        must contain the actual exception text, not the generic fallback string.
        """
        _push_command(fake_redis, "run-pipeline")

        captured_calls = []

        def capture_publish(conn, command, status, message):
            captured_calls.append((command, status, message))

        with patch("src.scheduler.daemon.redis.Redis.from_url", return_value=fake_redis), \
             patch("src.scheduler.daemon.signal.signal"), \
             patch("src.scheduler.daemon._handle_run_pipeline",
                   side_effect=RuntimeError("enrichment timeout")), \
             patch("src.scheduler.daemon._publish_result",
                   side_effect=capture_publish):

            daemon_mod._shutdown_requested = False
            fake_redis.brpop = _make_stopping_brpop(fake_redis)

            run_daemon(
                redis_url="redis://fake:6379/0",
                input_path=Path("/fake/input.xlsx"),
                filters_path=Path("/fake/filters.json"),
            )

        # At least one publish call should have happened for the error case.
        assert captured_calls, "Expected _publish_result to be called at least once"

        # Find the error call.
        error_calls = [(cmd, status, msg) for cmd, status, msg in captured_calls
                       if status == "error"]
        assert error_calls, (
            f"Expected an 'error' status publish call, got: {captured_calls}"
        )

        _, status, message = error_calls[-1]
        assert "enrichment timeout" in message, (
            f"Expected exception text in error message, got: {message!r}"
        )
        assert message != "Command failed — check logs", (
            "Error message must not be the generic fallback string"
        )
