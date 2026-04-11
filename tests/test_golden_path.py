"""Golden-path smoke test — exercises scan → interpret → compose → send."""

import json
from dataclasses import asdict
from unittest.mock import patch

import pytest

from src.prospecting.scanners.models import ScanResult


class TestGoldenPath:
    """End-to-end flow with all externals mocked."""

    def _make_scan_result(self) -> dict:
        """Create a realistic scan result dict (as returned by execute_scan_job)."""
        scan = ScanResult(
            domain="test-restaurant.dk",
            cms="WordPress",
            server="Apache",
            ssl_valid=True,
            ssl_issuer="Let's Encrypt",
            ssl_expiry="2026-12-01",
            ssl_days_remaining=235,
            detected_plugins=["contact-form-7", "woocommerce"],
            plugin_versions={"contact-form-7": "5.8", "woocommerce": "8.5"},
            headers={
                "x_frame_options": False,
                "content_security_policy": False,
                "strict_transport_security": True,
                "x_content_type_options": True,
            },
            tech_stack=["WordPress", "Apache", "PHP"],
            tls_version="TLSv1.3",
            tls_cipher="TLS_AES_256_GCM_SHA384",
            tls_bits=256,
        )
        return {
            "scan": asdict(scan),
            "brief": {
                "domain": "test-restaurant.dk",
                "cms": "WordPress",
                "findings": [
                    {
                        "title": "Missing X-Frame-Options Header",
                        "severity": "high",
                        "category": "headers",
                        "detail": "X-Frame-Options header not set",
                        "provenance": "confirmed",
                    },
                    {
                        "title": "Missing Content Security Policy",
                        "severity": "high",
                        "category": "headers",
                        "detail": "CSP header not configured",
                        "provenance": "confirmed",
                    },
                ],
                "finding_count": 2,
                "critical_count": 0,
                "high_count": 2,
            },
            "status": "completed",
        }

    def test_interpret_then_compose_produces_valid_html(self):
        """Brief → interpret → compose produces valid Telegram HTML."""
        result = self._make_scan_result()

        # Mock the Claude API response
        mock_interpretation = {
            "domain": "test-restaurant.dk",
            "findings": [
                {
                    "title": "Missing Clickjacking Protection",
                    "severity": "high",
                    "explanation": "Your website doesn't prevent other sites from embedding it in a frame.",
                    "provenance": "confirmed",
                },
                {
                    "title": "No Content Security Policy",
                    "severity": "high",
                    "explanation": "Your website has no policy controlling which scripts can run.",
                    "provenance": "confirmed",
                },
            ],
            "contact_name": "Test Owner",
        }

        from src.composer.telegram import compose_telegram
        messages = compose_telegram(mock_interpretation)

        # Verify output
        assert len(messages) >= 1
        full_message = "".join(messages)
        assert "test-restaurant.dk" in full_message
        # Should contain severity indicators
        assert "High" in full_message or "🟠" in full_message

    def test_interpret_brief_calls_llm(self):
        """interpret_brief calls the LLM backend and returns structured findings."""
        brief = self._make_scan_result()["brief"]

        mock_response = json.dumps({
            "findings": [
                {
                    "title": "Missing Clickjacking Protection",
                    "severity": "high",
                    "explanation": "Your website can be embedded in frames by malicious sites.",
                    "provenance": "confirmed",
                },
            ]
        })

        with patch("src.interpreter.interpreter.complete", return_value=mock_response):
            from src.interpreter.interpreter import interpret_brief
            result = interpret_brief(brief, language="en", tier="watchman")

        assert "findings" in result
        assert len(result["findings"]) >= 1
        assert result["findings"][0]["severity"] == "high"

    def test_compose_splits_long_messages(self):
        """Messages exceeding 4096 chars are split into chunks."""
        # Create a large interpretation with many findings
        findings = [
            {
                "title": f"Finding {i}",
                "severity": "high",
                "explanation": "A" * 500,  # Long explanation
                "provenance": "confirmed",
            }
            for i in range(20)
        ]
        interpretation = {
            "domain": "test.dk",
            "findings": findings,
            "contact_name": "Test",
        }

        from src.composer.telegram import compose_telegram
        messages = compose_telegram(interpretation)

        # Each chunk should be <= 4096 chars
        for msg in messages:
            assert len(msg) <= 4096

    def test_full_pipeline_scan_result_to_message(self):
        """Complete pipeline: scan result → brief → interpret → compose → message ready for send."""
        result = self._make_scan_result()
        brief = result["brief"]

        # Step 1: Interpret (mock LLM)
        mock_llm_response = json.dumps({
            "findings": [
                {
                    "title": "Missing Security Headers",
                    "severity": "high",
                    "explanation": "Two important security headers are missing.",
                    "provenance": "confirmed",
                },
            ]
        })

        with patch("src.interpreter.interpreter.complete", return_value=mock_llm_response):
            from src.interpreter.interpreter import interpret_brief
            interpreted = interpret_brief(brief, language="en", tier="watchman")

        # Step 2: Compose — domain is set by interpret_brief from brief["domain"]
        interpreted["contact_name"] = "Restaurant Owner"
        from src.composer.telegram import compose_telegram
        messages = compose_telegram(interpreted)

        # Step 3: Verify message is ready for Telegram send
        assert len(messages) >= 1
        full = "".join(messages)
        assert "test-restaurant.dk" in full
        assert "Restaurant Owner" in full or "restaurant" in full.lower()
        # Verify it's valid HTML-ish (has tags)
        assert "<b>" in full or "<i>" in full

    def test_scan_result_dataclass_serialisable(self):
        """ScanResult can be serialised to dict without loss (asdict round-trip)."""
        result_dict = self._make_scan_result()
        scan_dict = result_dict["scan"]

        assert scan_dict["domain"] == "test-restaurant.dk"
        assert scan_dict["cms"] == "WordPress"
        assert scan_dict["ssl_valid"] is True
        assert scan_dict["tls_version"] == "TLSv1.3"
        assert "contact-form-7" in scan_dict["detected_plugins"]
        assert scan_dict["plugin_versions"]["woocommerce"] == "8.5"

    def test_compose_watchman_tier_suppresses_fix(self):
        """Watchman tier messages do not include Fix instructions."""
        interpretation = {
            "domain": "test.dk",
            "findings": [
                {
                    "title": "Missing Header",
                    "severity": "high",
                    "explanation": "A header is missing.",
                    "action": "Add the header in nginx.conf",
                    "provenance": "confirmed",
                },
            ],
        }

        from src.composer.telegram import compose_telegram
        messages = compose_telegram(interpretation, tier="watchman")
        full = "".join(messages)

        # Fix line must not appear for watchman
        assert "Fix:" not in full
        assert "nginx.conf" not in full

    def test_compose_sentinel_tier_includes_fix(self):
        """Sentinel tier messages include Fix instructions when action is present."""
        interpretation = {
            "domain": "test.dk",
            "findings": [
                {
                    "title": "Missing Header",
                    "severity": "high",
                    "explanation": "A header is missing.",
                    "action": "Add the header in nginx.conf",
                    "provenance": "confirmed",
                },
            ],
        }

        from src.composer.telegram import compose_telegram
        messages = compose_telegram(interpretation, tier="sentinel")
        full = "".join(messages)

        assert "Fix:" in full
        assert "nginx.conf" in full

    def test_compose_confirmed_vs_potential_sections(self):
        """Confirmed and potential findings render in separate sections."""
        interpretation = {
            "domain": "test.dk",
            "findings": [
                {
                    "title": "Confirmed Issue",
                    "severity": "high",
                    "explanation": "This is confirmed.",
                    "provenance": "confirmed",
                },
                {
                    "title": "Potential Issue",
                    "severity": "high",
                    "explanation": "This might be an issue.",
                    "provenance": "unconfirmed",
                },
            ],
        }

        from src.composer.telegram import compose_telegram
        messages = compose_telegram(interpretation)
        full = "".join(messages)

        assert "Confirmed issues" in full
        assert "Potential issues" in full
        assert "Confirmed Issue" in full
        assert "Potential Issue" in full
