"""Tests for the Telegram message composer."""

import pytest

from src.composer.telegram import compose_telegram, compose_celebration, _MESSAGE_BUDGET


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _sample_interpreted(**overrides):
    """Build an interpreted brief matching interpreter output."""
    base = {
        "domain": "example.dk",
        "company_name": "Test Restaurant ApS",
        "contact_name": "Martin",
        "scan_date": "2026-03-27",
        "findings": [
            {
                "title": "Your contact form is not fully protected",
                "severity": "high",
                "explanation": "Gravity Forms collects data but HSTS is missing.",
                "action": "enable HSTS",
                "provenance": "confirmed",
            },
            {
                "title": "WordPress version is visible",
                "severity": "high",
                "explanation": "Version 6.9.4 is exposed in page source.",
                "action": "install a security plugin to hide it",
                "provenance": "confirmed",
            },
        ],
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
        assert "Your contact form is not fully protected" in msg
        assert "enable HSTS" in msg
        assert "Heimdall team" in msg

    def test_greeting_with_contact_name(self):
        messages = compose_telegram(_sample_interpreted())
        assert "Hi Martin" in messages[0]

    def test_greeting_without_contact_name(self):
        messages = compose_telegram(_sample_interpreted(contact_name=""))
        assert "Hi " not in messages[0].split(",")[0]
        assert "Heimdall has a security alert" in messages[0]

    def test_no_findings(self):
        interpreted = _sample_interpreted(findings=[])
        messages = compose_telegram(interpreted)
        assert len(messages) == 1
        assert "example.dk" in messages[0]

    def test_finding_action_with_owner(self):
        interpreted = _sample_interpreted(findings=[{
            "title": "Update plugins",
            "severity": "high",
            "explanation": "Plugins are outdated.",
            "action": "Go to WordPress > Plugins > Update All",
            "provenance": "confirmed",
        }])
        messages = compose_telegram(interpreted)
        assert "Update plugins" in messages[0]

    def test_finding_no_who(self):
        interpreted = _sample_interpreted(findings=[{
            "title": "Minor issue",
            "severity": "high",
            "explanation": "Not critical.",
            "action": "Consider fixing",
            "provenance": "confirmed",
        }])
        messages = compose_telegram(interpreted)
        assert "Consider fixing" in messages[0]

    def test_html_formatting(self):
        messages = compose_telegram(_sample_interpreted())
        msg = messages[0]
        assert "<b>" in msg
        assert "</b>" in msg
        assert "<i>" in msg

    def test_severity_label(self):
        interpreted = _sample_interpreted(findings=[{
            "title": "Critical issue",
            "severity": "critical",
            "explanation": "Bad.",
            "action": "Fix now",
            "provenance": "confirmed",
        }])
        messages = compose_telegram(interpreted)
        assert "\U0001f534 Critical:" in messages[0]

    def test_footer(self):
        messages = compose_telegram(_sample_interpreted())
        assert "Heimdall team" in messages[0]
        assert "keep watching" in messages[0]
        assert "keep watching" in messages[0]

    def test_twin_derived_separate_section(self):
        interpreted = _sample_interpreted(findings=[
            {
                "title": "Confirmed issue",
                "severity": "high",
                "explanation": "Found by scan.",
                "action": "Fix it",
                "provenance": "confirmed",
            },
            {
                "title": "Potential issue",
                "severity": "high",
                "explanation": "Version-based.",
                "action": "Check it",
                "provenance": "unconfirmed",
            },
        ])
        messages = compose_telegram(interpreted)
        msg = messages[0]
        assert "Potential issues" in msg
        assert "Confirmed issue" in msg
        assert "Potential issue" in msg

    def test_html_escapes_special_chars(self):
        interpreted = _sample_interpreted(
            domain="test<script>.dk",
            contact_name="Martin & Co",
        )
        messages = compose_telegram(interpreted)
        msg = messages[0]
        assert "&lt;script&gt;" in msg
        assert "&amp;" in msg


# ---------------------------------------------------------------------------
# Celebration messages
# ---------------------------------------------------------------------------

class TestComposeCelebration:
    def test_celebration_message(self):
        messages = compose_celebration(
            domain="restaurant-martin.dk",
            celebration_text="The booking plugin vulnerability is now fixed!",
            contact_name="Martin",
        )
        assert len(messages) == 1
        msg = messages[0]
        assert "Hi Martin" in msg
        assert "restaurant-martin.dk" in msg
        assert "booking plugin" in msg
        assert "\u2705" in msg  # ✅
        assert "Heimdall team" in msg

    def test_celebration_without_name(self):
        messages = compose_celebration(
            domain="test.dk",
            celebration_text="Issue fixed!",
        )
        assert "Hi " not in messages[0].split(",")[0]


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
                "severity": "high",
                "explanation": f"Explanation {i}: {'y' * 80}",
                "action": f"Action {i}: {'z' * 40}",
                "provenance": "confirmed",
            })
        interpreted = _sample_interpreted(findings=findings)
        messages = compose_telegram(interpreted)
        assert len(messages) > 1
        # Check numbering
        assert messages[0].startswith("(1/")
        assert messages[-1].startswith(f"({len(messages)}/")

    def test_each_message_under_limit(self):
        findings = [
            {"title": f"Issue {i}", "severity": "high",
             "explanation": "x" * 200,
             "action": "Fix it", "provenance": "confirmed"}
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
            "contact_name": "", "findings": [],
        })
        assert len(messages) == 1
        assert "test.dk" in messages[0]

    def test_missing_fields_in_finding(self):
        """Findings with missing keys should not crash."""
        interpreted = _sample_interpreted(findings=[{"title": "Oops"}])
        messages = compose_telegram(interpreted)
        assert "Oops" in messages[0]

    def test_minimal_finding_dict(self):
        """Finding with only a title should not crash."""
        interpreted = _sample_interpreted(findings=[
            {"title": "Minor thing"},
        ])
        messages = compose_telegram(interpreted)
        assert "Minor thing" in messages[0]


# ---------------------------------------------------------------------------
# Tier-aware rendering
# ---------------------------------------------------------------------------

class TestTierRendering:
    def test_watchman_no_fix_line(self):
        """Watchman tier suppresses the Fix: line even when action is present."""
        interpreted = _sample_interpreted(findings=[{
            "title": "Missing security header",
            "severity": "high",
            "explanation": "Connection not enforced.",
            "action": "Enable HSTS on the server",
            "provenance": "confirmed",
        }])
        messages = compose_telegram(interpreted, tier="watchman")
        assert "Fix:" not in messages[0]

    def test_sentinel_renders_fix_line(self):
        """Sentinel tier renders the Fix: line when action is present."""
        interpreted = _sample_interpreted(findings=[{
            "title": "Missing security header",
            "severity": "high",
            "explanation": "Connection not enforced.",
            "action": "Enable HSTS on the server",
            "provenance": "confirmed",
        }])
        messages = compose_telegram(interpreted, tier="sentinel")
        assert "Fix:" in messages[0]

    def test_default_tier_renders_fix_line(self):
        """Default tier (no tier argument) renders the Fix: line for backward compat."""
        interpreted = _sample_interpreted(findings=[{
            "title": "Missing security header",
            "severity": "high",
            "explanation": "Connection not enforced.",
            "action": "Enable HSTS on the server",
            "provenance": "confirmed",
        }])
        messages = compose_telegram(interpreted)
        assert "Fix:" in messages[0]
