"""Tests for filters: load_filters(), apply_pre_scan_filters(), apply_post_scan_filters()."""

import json
import pytest
from pathlib import Path

from src.prospecting.filters import load_filters, apply_pre_scan_filters, apply_post_scan_filters


# ---------------------------------------------------------------------------
# 1. load_filters()
# ---------------------------------------------------------------------------

class TestLoadFilters:
    def test_missing_file_returns_empty_dict(self, tmp_path):
        result = load_filters(tmp_path / "nonexistent.json")
        assert result == {}

    def test_valid_json_loads_correctly(self, tmp_path):
        filters_file = tmp_path / "filters.json"
        filters_file.write_text(json.dumps({
            "industry_code": ["86", "69"],
            "contactable": True,
        }))
        result = load_filters(filters_file)
        assert result == {"industry_code": ["86", "69"], "contactable": True}

    def test_unknown_keys_ignored(self, tmp_path):
        filters_file = tmp_path / "filters.json"
        filters_file.write_text(json.dumps({
            "industry_code": ["86"],
            "bogus_key": "should_be_ignored",
            "another_unknown": 42,
        }))
        result = load_filters(filters_file)
        assert "bogus_key" not in result
        assert "another_unknown" not in result
        assert result == {"industry_code": ["86"]}


# ---------------------------------------------------------------------------
# 2. apply_pre_scan_filters()
# ---------------------------------------------------------------------------

class TestPreScanFilters:
    def test_industry_code_filter_includes_matching(self, sample_company):
        companies = [
            sample_company(cvr="1", industry_code="8610"),
            sample_company(cvr="2", industry_code="561110"),
        ]
        filters = {"industry_code": ["86"]}
        apply_pre_scan_filters(companies, filters)
        assert not companies[0].discarded  # 8610 starts with 86
        assert companies[1].discarded      # 561110 does not start with 86

    def test_industry_code_filter_excludes_non_matching(self, sample_company):
        companies = [
            sample_company(cvr="1", industry_code="4711"),
        ]
        filters = {"industry_code": ["86", "69"]}
        apply_pre_scan_filters(companies, filters)
        assert companies[0].discarded
        assert companies[0].discard_reason == "filtered:industry_code"

    def test_contactable_filter_keeps_non_ad_protected(self, sample_company):
        companies = [
            sample_company(cvr="1", ad_protected=False),
            sample_company(cvr="2", ad_protected=True),
        ]
        filters = {"contactable": True}
        apply_pre_scan_filters(companies, filters)
        assert not companies[0].discarded
        assert companies[1].discarded
        assert companies[1].discard_reason == "filtered:contactable"

    def test_empty_industry_code_list_means_no_filter(self, sample_company):
        """Empty industry_code list should be treated as no filter (the bug we fixed)."""
        companies = [
            sample_company(cvr="1", industry_code="561110"),
            sample_company(cvr="2", industry_code="8610"),
        ]
        filters = {"industry_code": []}
        apply_pre_scan_filters(companies, filters)
        assert not companies[0].discarded
        assert not companies[1].discarded

    def test_no_filters_returns_all(self, sample_company):
        companies = [
            sample_company(cvr="1"),
            sample_company(cvr="2"),
        ]
        apply_pre_scan_filters(companies, {})
        assert not any(c.discarded for c in companies)


# ---------------------------------------------------------------------------
# 3. apply_post_scan_filters()
# ---------------------------------------------------------------------------

class TestPostScanFilters:
    def test_bucket_filter_keeps_a_and_b(self, sample_company):
        companies = [
            sample_company(cvr="1"),
            sample_company(cvr="2"),
            sample_company(cvr="3"),
            sample_company(cvr="4"),
            sample_company(cvr="5"),
        ]
        buckets = {
            "1": "A",
            "2": "B",
            "3": "C",
            "4": "D",
            "5": "E",
        }
        filters = {"bucket": ["A", "B"]}
        apply_post_scan_filters(companies, buckets, filters)

        assert not companies[0].discarded  # A — kept
        assert not companies[1].discarded  # B — kept
        assert companies[2].discarded      # C — discarded
        assert companies[3].discarded      # D — discarded
        assert companies[4].discarded      # E — discarded

    def test_no_bucket_filter_keeps_all(self, sample_company):
        companies = [
            sample_company(cvr="1"),
            sample_company(cvr="2"),
        ]
        buckets = {"1": "D", "2": "E"}
        apply_post_scan_filters(companies, buckets, {})
        assert not any(c.discarded for c in companies)

    def test_already_discarded_companies_not_re_filtered(self, sample_company):
        companies = [sample_company(cvr="1")]
        companies[0].discard_reason = "filtered:industry_code"
        buckets = {"1": "D"}
        filters = {"bucket": ["A"]}
        apply_post_scan_filters(companies, buckets, filters)
        # Should still have the original discard reason, not overwritten
        assert companies[0].discard_reason == "filtered:industry_code"
