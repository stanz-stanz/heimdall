"""Tests for the Telegram message composer."""

import pytest

from src.composer.telegram import compose_telegram, _MESSAGE_BUDGET


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _sample_interpreted(**overrides):
    """Build an interpreted brief matching interpreter output."""
    base = {
        "domain": "example.dk",
        "company_name": "Test Restaurant ApS",
        "scan_date": "2026-03-27",
        "good_news": ["SSL certificate valid", "Cloudflare protection active"],
        "findings": [
            {
                "title": "Your contact form is not fully protected",
                "explanation": "Gravity Forms collects data but HSTS is missing.",
                "action": "Ask your web host to enable HSTS",
                "who": "web_host",
                "effort": "5 minutes",
            },
            {
                "title": "WordPress version is visible",
                "explanation": "Version 6.9.4 is exposed in page source.",
                "action": "Install a security plugin to hide it",
                "who": "developer",
                "effort": "10 minutes",
            },
        ],
        "summary": "Two quick fixes will significantly improve security.",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Basic composition
# ---------------------------------------------------------------------------

class TestComposeTelegram:
    def test_single_message(self):
        messages = compose_telegram(_sample_interpreted())
        assert len(messages) == 1
        msg = messages[0]
        assert "example.dk" in msg
        assert "SSL certificate valid" in msg
        assert "Your contact form is not fully protected" in msg
        assert "Your web host" in msg
        assert "~5 minutes" in msg
        assert "Your developer" in msg
        assert "Two quick fixes" in msg

    def test_good_news_included(self):
        messages = compose_telegram(_sample_interpreted())
        assert "Cloudflare protection active" in messages[0]

    def test_no_findings(self):
        interpreted = _sample_interpreted(findings=[])
        messages = compose_telegram(interpreted)
        assert len(messages) == 1
        assert "SSL certificate valid" in messages[0]

    def test_no_good_news(self):
        interpreted = _sample_interpreted(good_news=[])
        messages = compose_telegram(interpreted)
        assert len(messages) == 1
        assert "Your contact form" in messages[0]

    def test_finding_action_with_owner(self):
        interpreted = _sample_interpreted(findings=[{
            "title": "Update plugins",
            "explanation": "Plugins are outdated.",
            "action": "Go to WordPress > Plugins > Update All",
            "who": "owner",
            "effort": "2 minutes",
        }])
        messages = compose_telegram(interpreted)
        assert "You" in messages[0]
        assert "~2 minutes" in messages[0]

    def test_finding_no_who_no_effort(self):
        interpreted = _sample_interpreted(findings=[{
            "title": "Minor issue",
            "explanation": "Not critical.",
            "action": "Consider fixing",
            "who": "",
            "effort": "",
        }])
        messages = compose_telegram(interpreted)
        assert "Consider fixing" in messages[0]

    def test_summary_separator(self):
        messages = compose_telegram(_sample_interpreted())
        assert "---" in messages[0]


# ---------------------------------------------------------------------------
# Message splitting
# ---------------------------------------------------------------------------

class TestMessageSplitting:
    def test_long_message_splits(self):
        """A message with many findings should split across multiple messages."""
        findings = []
        for i in range(50):
            findings.append({
                "title": f"Finding {i}: {'x' * 40}",
                "explanation": f"Explanation {i}: {'y' * 80}",
                "action": f"Action {i}: {'z' * 40}",
                "who": "developer",
                "effort": "1 hour",
            })
        interpreted = _sample_interpreted(findings=findings)
        messages = compose_telegram(interpreted)
        assert len(messages) > 1
        # Check numbering
        assert messages[0].startswith("(1/")
        assert messages[-1].startswith(f"({len(messages)}/")

    def test_each_message_under_limit(self):
        findings = [
            {"title": f"Issue {i}", "explanation": "x" * 200,
             "action": "Fix it", "who": "developer", "effort": "1h"}
            for i in range(30)
        ]
        interpreted = _sample_interpreted(findings=findings)
        messages = compose_telegram(interpreted)
        for msg in messages:
            assert len(msg) <= 4096, f"Message too long: {len(msg)} chars"

    def test_single_message_no_numbering(self):
        messages = compose_telegram(_sample_interpreted())
        assert not messages[0].startswith("(1/")


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_interpreted(self):
        messages = compose_telegram({
            "domain": "test.dk", "company_name": "", "scan_date": "",
            "good_news": [], "findings": [], "summary": "",
        })
        assert len(messages) == 1
        assert "test.dk" in messages[0]

    def test_missing_fields_in_finding(self):
        """Findings with missing keys should not crash."""
        interpreted = _sample_interpreted(findings=[{"title": "Oops"}])
        messages = compose_telegram(interpreted)
        assert "Oops" in messages[0]

    def test_client_name_override(self):
        messages = compose_telegram(_sample_interpreted(), client_name="Peter")
        # client_name is accepted but currently used for future personalisation
        assert len(messages) >= 1
