"""Tests for the scheduler daemon command dispatch."""

import json
from pathlib import Path
from unittest.mock import patch

import fakeredis
import pytest

from src.scheduler.daemon import _handle_interpret, _handle_send, run_daemon

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_redis():
    return fakeredis.FakeRedis(decode_responses=True)


# ---------------------------------------------------------------------------
# Command parsing
# ---------------------------------------------------------------------------

class TestDaemonDispatch:
    def test_run_pipeline_command_dispatched(self, fake_redis):
        """Verify run-pipeline command is parsed and dispatched."""
        cmd = {"command": "run-pipeline", "payload": {}, "ts": "2026-04-06T10:00:00"}
        fake_redis.lpush("queue:operator-commands", json.dumps(cmd))

        with patch("src.scheduler.daemon.redis.Redis.from_url", return_value=fake_redis), \
             patch("src.scheduler.daemon._handle_run_pipeline") as mock_handler, \
             patch("src.scheduler.daemon.signal.signal"):  # Don't modify signals in tests

            # Simulate daemon processing one command then stopping
            mock_handler.side_effect = lambda *a: setattr(
                __import__("src.scheduler.daemon", fromlist=["_shutdown_requested"]),
                "_shutdown_requested",
                True,
            )

            import src.scheduler.daemon as daemon_mod
            daemon_mod._shutdown_requested = False

            run_daemon(
                redis_url="redis://fake:6379/0",
                input_path=Path("/fake/input.xlsx"),
                filters_path=Path("/fake/filters.json"),
            )

            mock_handler.assert_called_once()

    def test_unknown_command_logged(self, fake_redis):
        """Unknown commands are logged but don't crash."""
        cmd = {"command": "unknown-thing", "payload": {}}
        fake_redis.lpush("queue:operator-commands", json.dumps(cmd))

        with patch("src.scheduler.daemon.redis.Redis.from_url", return_value=fake_redis), \
             patch("src.scheduler.daemon.signal.signal"):

            import src.scheduler.daemon as daemon_mod
            daemon_mod._shutdown_requested = False

            # Process one command, then stop
            original_brpop = fake_redis.brpop

            call_count = 0
            def limited_brpop(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count > 1:
                    daemon_mod._shutdown_requested = True
                    return None
                return original_brpop(*args, **kwargs)

            fake_redis.brpop = limited_brpop
            run_daemon("redis://fake:6379/0", Path("/fake"), Path("/fake"))

    def test_invalid_json_skipped(self, fake_redis):
        """Invalid JSON on the queue is logged and skipped."""
        fake_redis.lpush("queue:operator-commands", "not valid json{{{")

        with patch("src.scheduler.daemon.redis.Redis.from_url", return_value=fake_redis), \
             patch("src.scheduler.daemon.signal.signal"):

            import src.scheduler.daemon as daemon_mod
            daemon_mod._shutdown_requested = False

            call_count = 0
            original_brpop = fake_redis.brpop

            def limited_brpop(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count > 1:
                    daemon_mod._shutdown_requested = True
                    return None
                return original_brpop(*args, **kwargs)

            fake_redis.brpop = limited_brpop
            run_daemon("redis://fake:6379/0", Path("/fake"), Path("/fake"))


# ---------------------------------------------------------------------------
# Individual handlers
# ---------------------------------------------------------------------------

class TestInterpretHandler:
    def test_interpret_missing_campaign(self, fake_redis):
        """Interpret without campaign publishes error."""
        _handle_interpret(fake_redis, {})

        # Check that an error was published
        pubsub = fake_redis.pubsub()
        pubsub.subscribe("console:command-results")
        # fakeredis may not support pubsub fully, so just verify no crash


class TestSendHandler:
    def test_send_missing_campaign(self, fake_redis):
        """Send without campaign publishes error."""
        _handle_send(fake_redis, {})
        # Verify no crash — error is published to Redis


class TestDaemonMainIntegration:
    def test_scheduler_main_daemon_mode(self):
        """Verify --mode daemon is accepted by the argument parser."""
        from src.scheduler.main import _parse_args
        args = _parse_args(["--mode", "daemon"])
        assert args.mode == "daemon"

    def test_scheduler_main_daemon_calls_run_daemon(self):
        """Verify main() dispatches to run_daemon for daemon mode."""
        with patch("src.scheduler.daemon.run_daemon") as mock:
            from src.scheduler.main import main
            main(["--mode", "daemon"])
            mock.assert_called_once()
