"""Tests for delivery bot setup."""

import json
import os
from unittest.mock import patch

import pytest

from src.delivery.bot import (
    _DEFAULT_CONFIG,
    get_bot_token,
    get_operator_chat_id,
    load_config,
)


class TestLoadConfig:
    """Config loading with file overrides and fallback defaults."""

    def test_load_from_file(self, tmp_path: object) -> None:
        config_file = tmp_path / "delivery.json"
        config_file.write_text(
            json.dumps({"require_approval": False, "retry_max": 5})
        )
        config = load_config(config_file)
        assert config["require_approval"] is False
        assert config["retry_max"] == 5
        # Default preserved for keys not in file
        assert config["rate_limit_per_second"] == 1

    def test_load_missing_file_returns_defaults(self, tmp_path: object) -> None:
        config = load_config(tmp_path / "nonexistent.json")
        assert config == _DEFAULT_CONFIG

    def test_load_invalid_json_returns_defaults(self, tmp_path: object) -> None:
        config_file = tmp_path / "bad.json"
        config_file.write_text("not json {{{")
        config = load_config(config_file)
        assert config == _DEFAULT_CONFIG

    def test_load_non_dict_json_returns_defaults(self, tmp_path: object) -> None:
        config_file = tmp_path / "array.json"
        config_file.write_text(json.dumps([1, 2, 3]))
        config = load_config(config_file)
        assert config == _DEFAULT_CONFIG

    def test_load_partial_override_preserves_all_defaults(
        self, tmp_path: object
    ) -> None:
        config_file = tmp_path / "partial.json"
        config_file.write_text(json.dumps({"retry_delay_seconds": 10}))
        config = load_config(config_file)
        assert config["retry_delay_seconds"] == 10
        assert config["require_approval"] is True
        assert config["retry_max"] == 3
        assert config["rate_limit_per_second"] == 1


class TestGetBotToken:
    """Bot token retrieval from environment."""

    def test_token_from_env(self) -> None:
        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "test-token-123"}):
            assert get_bot_token() == "test-token-123"

    def test_missing_token_raises(self) -> None:
        env = {k: v for k, v in os.environ.items() if k != "TELEGRAM_BOT_TOKEN"}
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(RuntimeError, match="TELEGRAM_BOT_TOKEN"):
                get_bot_token()

    def test_empty_token_raises(self) -> None:
        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": ""}):
            with pytest.raises(RuntimeError, match="TELEGRAM_BOT_TOKEN"):
                get_bot_token()


class TestGetOperatorChatId:
    """Operator chat ID retrieval from environment."""

    def test_chat_id_from_env(self) -> None:
        with patch.dict(os.environ, {"TELEGRAM_OPERATOR_CHAT_ID": "12345"}):
            assert get_operator_chat_id() == "12345"

    def test_missing_chat_id_raises(self) -> None:
        env = {
            k: v for k, v in os.environ.items() if k != "TELEGRAM_OPERATOR_CHAT_ID"
        }
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(RuntimeError, match="TELEGRAM_OPERATOR_CHAT_ID"):
                get_operator_chat_id()

    def test_empty_chat_id_raises(self) -> None:
        with patch.dict(os.environ, {"TELEGRAM_OPERATOR_CHAT_ID": ""}):
            with pytest.raises(RuntimeError, match="TELEGRAM_OPERATOR_CHAT_ID"):
                get_operator_chat_id()
