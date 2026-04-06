"""Tests for interpretation cache (src/interpreter/cache.py)."""

from __future__ import annotations

import pytest

from src.interpreter.cache import (
    compute_finding_hash,
    get_cached,
    store,
    cache_stats,
    PROMPT_VERSION,
)


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test_cache.db")


SAMPLE_FINDINGS = [
    {"severity": "critical", "description": "No SSL", "risk": "Bad", "provenance": "confirmed"},
    {"severity": "high", "description": "Missing HSTS", "risk": "Risky", "provenance": "confirmed"},
]

SAMPLE_INTERPRETATION = {
    "findings": [{"title": "No encryption", "severity": "critical", "explanation": "Your site is unprotected"}],
    "summary": "Your site needs attention",
    "good_news": [],
}


class TestFindingHash:
    def test_same_findings_same_hash(self):
        h1 = compute_finding_hash(SAMPLE_FINDINGS, "watchman", "en")
        h2 = compute_finding_hash(SAMPLE_FINDINGS, "watchman", "en")
        assert h1 == h2

    def test_order_independent(self):
        reversed_findings = list(reversed(SAMPLE_FINDINGS))
        h1 = compute_finding_hash(SAMPLE_FINDINGS, "watchman", "en")
        h2 = compute_finding_hash(reversed_findings, "watchman", "en")
        assert h1 == h2

    def test_different_tier_different_hash(self):
        h1 = compute_finding_hash(SAMPLE_FINDINGS, "watchman", "en")
        h2 = compute_finding_hash(SAMPLE_FINDINGS, "sentinel", "en")
        assert h1 != h2

    def test_different_language_different_hash(self):
        h1 = compute_finding_hash(SAMPLE_FINDINGS, "watchman", "en")
        h2 = compute_finding_hash(SAMPLE_FINDINGS, "watchman", "da")
        assert h1 != h2

    def test_different_findings_different_hash(self):
        other = [{"severity": "high", "description": "Other issue", "risk": "X", "provenance": "confirmed"}]
        h1 = compute_finding_hash(SAMPLE_FINDINGS, "watchman", "en")
        h2 = compute_finding_hash(other, "watchman", "en")
        assert h1 != h2


class TestCacheRoundtrip:
    def test_store_and_retrieve(self, db_path):
        store(SAMPLE_FINDINGS, "watchman", "en", SAMPLE_INTERPRETATION, db_path=db_path)
        result = get_cached(SAMPLE_FINDINGS, "watchman", "en", db_path=db_path)
        assert result is not None
        assert result["findings"][0]["title"] == "No encryption"

    def test_miss_returns_none(self, db_path):
        result = get_cached(SAMPLE_FINDINGS, "watchman", "en", db_path=db_path)
        assert result is None

    def test_different_tier_is_separate(self, db_path):
        store(SAMPLE_FINDINGS, "watchman", "en", SAMPLE_INTERPRETATION, db_path=db_path)
        result = get_cached(SAMPLE_FINDINGS, "sentinel", "en", db_path=db_path)
        assert result is None

    def test_different_language_is_separate(self, db_path):
        store(SAMPLE_FINDINGS, "watchman", "en", SAMPLE_INTERPRETATION, db_path=db_path)
        result = get_cached(SAMPLE_FINDINGS, "watchman", "da", db_path=db_path)
        assert result is None

    def test_overwrite_on_replace(self, db_path):
        store(SAMPLE_FINDINGS, "watchman", "en", SAMPLE_INTERPRETATION, db_path=db_path)
        updated = {**SAMPLE_INTERPRETATION, "summary": "Updated"}
        store(SAMPLE_FINDINGS, "watchman", "en", updated, db_path=db_path)
        result = get_cached(SAMPLE_FINDINGS, "watchman", "en", db_path=db_path)
        assert result["summary"] == "Updated"


class TestCacheStats:
    def test_empty_cache(self, db_path):
        stats = cache_stats(db_path=db_path)
        assert stats["entries"] == 0

    def test_populated_cache(self, db_path):
        store(SAMPLE_FINDINGS, "watchman", "en", SAMPLE_INTERPRETATION,
              input_tokens=500, output_tokens=200, db_path=db_path)
        stats = cache_stats(db_path=db_path)
        assert stats["entries"] == 1
        assert stats["prompt_version"] == PROMPT_VERSION
