"""Tests for the Redis log sink module."""

import json
import queue
import time
from unittest.mock import MagicMock, patch

import pytest

from src.logging.redis_sink import _RedisSinkWorker, _make_sink, add_redis_sink


class TestRedisSinkWorker:
    def test_enqueue_adds_to_queue(self):
        worker = _RedisSinkWorker("redis://fake:6379/0")
        worker.enqueue('{"test": true}')
        assert worker._q.qsize() == 1

    def test_enqueue_drops_when_full(self):
        worker = _RedisSinkWorker("redis://fake:6379/0")
        worker._q = queue.Queue(maxsize=2)
        worker.enqueue("a")
        worker.enqueue("b")
        worker.enqueue("c")  # should be silently dropped
        assert worker._q.qsize() == 2

    def test_worker_is_daemon_thread(self):
        worker = _RedisSinkWorker("redis://fake:6379/0")
        assert worker.daemon is True


class TestMakeSink:
    def test_sink_serializes_entry(self):
        worker = MagicMock()
        sink = _make_sink(worker)

        # Create a mock loguru message
        level_mock = MagicMock()
        level_mock.name = "INFO"  # set directly, not via constructor
        record = {
            "time": MagicMock(timestamp=MagicMock(return_value=1712404800.0)),
            "level": level_mock,
            "name": "src.worker.scan_job",
            "message": "scan_complete domain=test.dk",
            "extra": {"context": {"domain": "test.dk", "job_id": "scan-001"}},
            "exception": None,
        }
        message = MagicMock()
        message.record = record

        sink(message)

        worker.enqueue.assert_called_once()
        entry = json.loads(worker.enqueue.call_args[0][0])
        assert entry["level"] == "INFO"
        assert entry["module"] == "src.worker.scan_job"
        assert entry["message"] == "scan_complete domain=test.dk"
        assert entry["ctx"]["domain"] == "test.dk"
        assert entry["ts"] == 1712404800.0

    def test_sink_handles_missing_context(self):
        worker = MagicMock()
        sink = _make_sink(worker)

        record = {
            "time": MagicMock(timestamp=MagicMock(return_value=1712404800.0)),
            "level": MagicMock(name="ERROR"),
            "name": "root",
            "message": "something broke",
            "extra": {},
            "exception": None,
        }
        message = MagicMock()
        message.record = record

        sink(message)

        entry = json.loads(worker.enqueue.call_args[0][0])
        assert "ctx" not in entry

    def test_sink_includes_exception(self):
        worker = MagicMock()
        sink = _make_sink(worker)

        try:
            raise ValueError("test error")
        except ValueError:
            import sys
            exc_info = sys.exc_info()

        exc_mock = MagicMock()
        exc_mock.value = exc_info[1]
        exc_mock.traceback = exc_info[2]

        record = {
            "time": MagicMock(timestamp=MagicMock(return_value=1712404800.0)),
            "level": MagicMock(name="ERROR"),
            "name": "root",
            "message": "error occurred",
            "extra": {},
            "exception": exc_mock,
        }
        message = MagicMock()
        message.record = record

        sink(message)

        entry = json.loads(worker.enqueue.call_args[0][0])
        assert "exc" in entry
        assert "ValueError" in entry["exc"]
        assert "test error" in entry["exc"]


class TestAddRedisSink:
    def test_noop_when_empty_url(self):
        """add_redis_sink with empty URL should not start any threads."""
        add_redis_sink("")
        add_redis_sink(None)
        # No exception = pass

    def test_adds_sink_to_loguru(self):
        with patch("src.logging.redis_sink._RedisSinkWorker") as MockWorker, \
             patch("loguru.logger.add") as mock_add:
            mock_instance = MagicMock()
            MockWorker.return_value = mock_instance

            add_redis_sink("redis://fake:6379/0")

            mock_instance.start.assert_called_once()
            mock_add.assert_called_once()
