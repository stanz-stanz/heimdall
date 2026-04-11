"""Tests for the loguru-based logging configuration."""

import json
from io import StringIO

from loguru import logger

from src.core.logging_config import setup_logging


class TestSetupLogging:
    def setup_method(self):
        """Reset loguru state between tests."""
        logger.remove()

    def test_json_format_outputs_valid_json(self):
        buf = StringIO()
        setup_logging(level="INFO", fmt="json", sink=buf)
        logger.info("hello")
        line = buf.getvalue().strip().split("\n")[-1]
        parsed = json.loads(line)
        assert parsed["message"] == "hello"
        assert parsed["level"] == "INFO"
        assert "timestamp" in parsed
        assert "module" in parsed

    def test_json_format_includes_bound_context(self):
        buf = StringIO()
        setup_logging(level="INFO", fmt="json", sink=buf)
        logger.bind(context={"key": "value", "count": 42}).info("with context")
        line = buf.getvalue().strip().split("\n")[-1]
        parsed = json.loads(line)
        assert parsed["context"]["key"] == "value"
        assert parsed["context"]["count"] == 42

    def test_json_format_no_context_when_absent(self):
        buf = StringIO()
        setup_logging(level="INFO", fmt="json", sink=buf)
        logger.info("no context")
        line = buf.getvalue().strip().split("\n")[-1]
        parsed = json.loads(line)
        assert "context" not in parsed

    def test_text_format(self):
        buf = StringIO()
        setup_logging(level="INFO", fmt="text", sink=buf)
        logger.info("hello text")
        output = buf.getvalue()
        assert "hello text" in output
        assert "INFO" in output

    def test_level_filtering(self):
        buf = StringIO()
        setup_logging(level="WARNING", fmt="text", sink=buf)
        logger.info("should be hidden")
        logger.warning("should be visible")
        output = buf.getvalue()
        assert "should be hidden" not in output
        assert "should be visible" in output

    def test_repeated_setup_does_not_duplicate(self):
        buf = StringIO()
        setup_logging(level="INFO", fmt="text", sink=buf)
        setup_logging(level="INFO", fmt="text", sink=buf)
        logger.info("once")
        lines = [l for l in buf.getvalue().strip().split("\n") if "once" in l]
        assert len(lines) == 1

    def test_stdlib_intercept(self):
        """Third-party libraries using stdlib logging should route through loguru."""
        import logging as stdlib_logging

        buf = StringIO()
        setup_logging(level="INFO", fmt="json", sink=buf)
        stdlib_logger = stdlib_logging.getLogger("fake_thirdparty")
        stdlib_logger.info("from stdlib")
        output = buf.getvalue()
        assert "from stdlib" in output
