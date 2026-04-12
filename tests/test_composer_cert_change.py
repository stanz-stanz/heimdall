"""Unit tests for compose_cert_change — Sentinel-tier cert change messages."""

from __future__ import annotations

from src.composer.telegram import TELEGRAM_MAX_CHARS, compose_cert_change


def test_new_cert_en_contains_domain_and_issuer() -> None:
    msgs = compose_cert_change(
        {
            "change_type": "new_cert",
            "domain": "foo.dk",
            "details": {
                "issuer_name": "Let's Encrypt",
                "not_before": "2026-04-12T00:00:00Z",
                "dns_names": ["foo.dk"],
            },
        },
        lang="en",
        contact_name="Federico",
    )
    assert len(msgs) == 1
    body = msgs[0]
    assert "<b>foo.dk</b>" in body
    assert "Let&#x27;s Encrypt" in body  # html-escaped
    assert "Hi Federico" in body
    assert "2026-04-12" in body


def test_new_san_en_lists_only_new_hostnames() -> None:
    msgs = compose_cert_change(
        {
            "change_type": "new_san",
            "domain": "foo.dk",
            "details": {
                "issuer_name": "Let's Encrypt",
                "dns_names": ["foo.dk", "admin.foo.dk"],
                "prior_sans": ["foo.dk"],
            },
        },
        lang="en",
    )
    body = msgs[0]
    assert "admin.foo.dk" in body
    assert "New hostname" in body


def test_ca_change_en_shows_both_issuers() -> None:
    msgs = compose_cert_change(
        {
            "change_type": "ca_change",
            "domain": "foo.dk",
            "details": {"issuer_name": "DigiCert"},
        },
        lang="en",
        prior_issuer="Let's Encrypt",
    )
    body = msgs[0]
    assert "Let&#x27;s Encrypt" in body
    assert "DigiCert" in body


def test_new_cert_da_uses_danish_template() -> None:
    msgs = compose_cert_change(
        {
            "change_type": "new_cert",
            "domain": "foo.dk",
            "details": {"issuer_name": "Let's Encrypt", "not_before": "2026-04-12"},
        },
        lang="da",
    )
    body = msgs[0]
    assert "Udsteder" in body
    assert "SSL-certifikat" in body


def test_unknown_language_falls_back_to_english() -> None:
    msgs = compose_cert_change(
        {"change_type": "new_cert", "domain": "foo.dk", "details": {"issuer_name": "LE"}},
        lang="fr",
    )
    assert "SSL certificate" in msgs[0]  # English fallback


def test_unknown_change_type_falls_back_to_new_cert() -> None:
    msgs = compose_cert_change(
        {"change_type": "weird_thing", "domain": "foo.dk", "details": {"issuer_name": "LE"}},
        lang="en",
    )
    assert "SSL certificate" in msgs[0]


def test_message_under_telegram_max() -> None:
    msgs = compose_cert_change(
        {
            "change_type": "new_san",
            "domain": "foo.dk",
            "details": {
                "issuer_name": "Let's Encrypt",
                "dns_names": [f"sub{i}.foo.dk" for i in range(100)],
                "prior_sans": [],
            },
        },
        lang="en",
    )
    assert len(msgs[0]) <= TELEGRAM_MAX_CHARS
