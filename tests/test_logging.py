"""Tests for the structured logging configuration."""

import json
import logging

from src.prospecting.logging_config import JSONFormatter, setup_logging


class TestJSONFormatter:
    def test_outputs_valid_json(self):
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="hello", args=(), exc_info=None,
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        assert isinstance(parsed, dict)

    def test_has_required_keys(self):
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test.module", level=logging.WARNING, pathname="", lineno=0,
            msg="some warning", args=(), exc_info=None,
        )
        parsed = json.loads(formatter.format(record))
        assert "timestamp" in parsed
        assert "level" in parsed
        assert "module" in parsed
        assert "message" in parsed
        assert parsed["level"] == "WARNING"
        assert parsed["module"] == "test.module"
        assert parsed["message"] == "some warning"

    def test_includes_context(self):
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="with context", args=(), exc_info=None,
        )
        record.context = {"key": "value", "count": 42}
        parsed = json.loads(formatter.format(record))
        assert "context" in parsed
        assert parsed["context"]["key"] == "value"
        assert parsed["context"]["count"] == 42

    def test_no_context_when_absent(self):
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="no context", args=(), exc_info=None,
        )
        parsed = json.loads(formatter.format(record))
        assert "context" not in parsed


class TestSetupLogging:
    def _reset_root(self):
        """Clear root logger state between tests."""
        root = logging.getLogger()
        root.handlers.clear()
        root.setLevel(logging.WARNING)

    def test_json_format(self):
        self._reset_root()
        setup_logging(fmt="json")
        root = logging.getLogger()
        assert len(root.handlers) == 1
        assert isinstance(root.handlers[0].formatter, JSONFormatter)

    def test_text_format(self):
        self._reset_root()
        setup_logging(fmt="text")
        root = logging.getLogger()
        assert len(root.handlers) == 1
        formatter = root.handlers[0].formatter
        assert not isinstance(formatter, JSONFormatter)
        assert isinstance(formatter, logging.Formatter)

    def test_level_setting(self):
        self._reset_root()
        setup_logging(level="DEBUG")
        root = logging.getLogger()
        assert root.level == logging.DEBUG

        setup_logging(level="ERROR")
        assert root.level == logging.ERROR
