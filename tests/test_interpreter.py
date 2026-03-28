"""Tests for the finding interpreter and LLM abstraction."""

import json

import pytest

from src.interpreter.interpreter import InterpreterError, interpret_brief, _parse_response
from src.interpreter.llm import LLMError
from src.interpreter.prompts import build_system_prompt, build_user_prompt


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _sample_brief(**overrides):
    """Build a brief matching the worker output format."""
    base = {
        "domain": "example.dk",
        "cvr": "12345678",
        "company_name": "Test Restaurant ApS",
        "scan_date": "2026-03-27",
        "bucket": "A",
        "gdpr_sensitive": True,
        "gdpr_reasons": ["Data-handling plugins: Gravityforms"],
        "industry": "Restaurant and café services",
        "technology": {
            "cms": "WordPress",
            "hosting": "Cloudflare",
            "ssl": {"valid": True, "issuer": "Let's Encrypt", "expiry": "2026-06-01", "days_remaining": 60},
            "server": "cloudflare",
            "detected_plugins": ["Gravityforms", "WP Rocket"],
            "headers": {
                "x_frame_options": False,
                "content_security_policy": False,
                "strict_transport_security": False,
                "x_content_type_options": False,
            },
        },
        "tech_stack": ["WordPress:6.9.4", "PHP", "MySQL"],
        "subdomains": {"count": 2, "list": ["www.example.dk", "mail.example.dk"]},
        "dns": {"a": ["1.2.3.4"]},
        "cloud_exposure": [],
        "findings": [
            {"severity": "medium", "description": "Missing HSTS header", "risk": "Unsecured WiFi interception risk."},
            {"severity": "medium", "description": "Data-handling plugins: Gravityforms", "risk": "Collects user data."},
            {"severity": "low", "description": "Missing CSP header", "risk": "No script restrictions."},
            {"severity": "info", "description": "2 subdomains detected", "risk": "Each is a separate entry point."},
        ],
    }
    base.update(overrides)
    return base


_MOCK_LLM_RESPONSE = json.dumps({
    "good_news": ["SSL certificate valid", "Cloudflare protection active"],
    "findings": [
        {
            "title": "Your contact form is not fully protected",
            "explanation": "Your Gravity Forms plugin collects customer data, but the site is missing a security setting (HSTS) that protects the connection.",
            "action": "Ask your web host to enable HSTS",
            "who": "web_host",
            "effort": "5 minutes",
        },
        {
            "title": "WordPress version is visible",
            "explanation": "Anyone can see you run WordPress 6.9.4 by viewing the page source.",
            "action": "Install a security plugin to hide the version number",
            "who": "developer",
            "effort": "10 minutes",
        },
    ],
    "summary": "Your site has a solid foundation. Two quick fixes will significantly improve security.",
})


# ---------------------------------------------------------------------------
# Prompt building
# ---------------------------------------------------------------------------

class TestPrompts:
    def test_system_prompt_includes_tone(self):
        prompt = build_system_prompt(
            industry="restaurant",
            tone="concise",
            tone_description="Brief and direct.",
            language="en",
        )
        assert "Brief and direct" in prompt
        assert "English" in prompt
        assert "restaurant" in prompt

    def test_system_prompt_danish(self):
        prompt = build_system_prompt(
            industry="restaurant", tone="balanced",
            tone_description="Friendly professional.", language="da",
        )
        assert "Danish" in prompt

    def test_user_prompt_includes_brief_data(self):
        brief = _sample_brief()
        prompt = build_user_prompt(brief)
        assert "example.dk" in prompt
        assert "WordPress" in prompt
        assert "Gravityforms" in prompt
        assert "HSTS" in prompt
        assert "Restaurant" in prompt

    def test_user_prompt_no_plugins(self):
        brief = _sample_brief()
        brief["technology"]["detected_plugins"] = []
        prompt = build_user_prompt(brief)
        assert "none detected" in prompt


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

class TestParseResponse:
    def test_valid_json(self):
        parsed = _parse_response(_MOCK_LLM_RESPONSE)
        assert isinstance(parsed, dict)
        assert len(parsed["findings"]) == 2
        assert len(parsed["good_news"]) == 2

    def test_json_with_markdown_fences(self):
        wrapped = f"```json\n{_MOCK_LLM_RESPONSE}\n```"
        parsed = _parse_response(wrapped)
        assert len(parsed["findings"]) == 2

    def test_invalid_json_raises(self):
        with pytest.raises((json.JSONDecodeError, ValueError)):
            _parse_response("not json at all")

    def test_missing_findings_key(self):
        with pytest.raises(ValueError, match="findings"):
            _parse_response('{"good_news": []}')

    def test_findings_not_list(self):
        with pytest.raises(ValueError, match="list"):
            _parse_response('{"findings": "not a list"}')

    def test_array_response_rejected(self):
        with pytest.raises(ValueError, match="dict"):
            _parse_response('[1, 2, 3]')

    def test_defaults_set(self):
        minimal = '{"findings": []}'
        parsed = _parse_response(minimal)
        assert parsed["good_news"] == []
        assert parsed["summary"] == ""


# ---------------------------------------------------------------------------
# interpret_brief (with mocked LLM)
# ---------------------------------------------------------------------------

class TestInterpretBrief:
    def test_interpret_success(self, monkeypatch):
        monkeypatch.setattr(
            "src.interpreter.interpreter.complete",
            lambda prompt, system="": _MOCK_LLM_RESPONSE,
        )
        brief = _sample_brief()
        result = interpret_brief(brief, tone="balanced", language="en")

        assert result["domain"] == "example.dk"
        assert result["company_name"] == "Test Restaurant ApS"
        assert len(result["findings"]) == 2
        assert result["meta"]["tone"] == "balanced"
        assert result["meta"]["language"] == "en"
        assert "duration_ms" in result["meta"]

    def test_interpret_with_tone_override(self, monkeypatch):
        calls = []
        def _capture(prompt, system=""):
            calls.append(system)
            return _MOCK_LLM_RESPONSE
        monkeypatch.setattr("src.interpreter.interpreter.complete", _capture)

        interpret_brief(_sample_brief(), tone="concise", language="en")
        assert "Brief and direct" in calls[0]

    def test_interpret_llm_failure(self, monkeypatch):
        def _fail(prompt, system=""):
            raise LLMError("API key invalid")
        monkeypatch.setattr("src.interpreter.interpreter.complete", _fail)

        with pytest.raises(InterpreterError, match="LLM call failed"):
            interpret_brief(_sample_brief())

    def test_interpret_bad_response(self, monkeypatch):
        monkeypatch.setattr(
            "src.interpreter.interpreter.complete",
            lambda prompt, system="": "not json",
        )
        with pytest.raises(InterpreterError, match="Failed to parse"):
            interpret_brief(_sample_brief())
