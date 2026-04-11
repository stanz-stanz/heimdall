"""Tests for config.py — JSON config loading and constants."""

import json

from src.core.config import CONFIG_DIR, PROJECT_ROOT
from src.prospecting.config import (
    BUCKET_A_CMS,
    BUCKET_B_CMS,
    BUCKET_C_PLATFORMS,
    CMS_KEYWORDS,
    FREE_WEBMAIL,
    GDPR_DATA_HANDLING_PLUGINS,
    GDPR_ECOMMERCE_CMS,
    GDPR_SENSITIVE_CODES,
    GDPR_TRACKING_TECH,
    HOSTING_PROVIDERS,
    SENSITIVE_TECH,
    _load_json,
)


class TestPaths:
    def test_project_root_exists(self):
        assert PROJECT_ROOT.is_dir()

    def test_config_dir_exists(self):
        assert CONFIG_DIR.is_dir()

    def test_project_root_has_claude_md(self):
        assert (PROJECT_ROOT / "CLAUDE.md").is_file()


class TestJsonLoading:
    def test_load_buckets(self):
        data = _load_json("buckets.json")
        assert "A" in data
        assert "B" in data
        assert "C" in data
        assert "cms" in data["A"]
        assert "platforms" in data["C"]

    def test_load_gdpr_signals(self):
        data = _load_json("gdpr_signals.json")
        assert "industry_codes" in data
        assert "data_handling_plugins" in data
        assert "tracking_tech" in data
        assert "ecommerce_cms" in data
        assert "sensitive_tech" in data

    def test_load_free_webmail(self):
        data = _load_json("free_webmail.json")
        assert isinstance(data, list)
        assert "gmail.com" in data

    def test_load_hosting_providers(self):
        data = _load_json("hosting_providers.json")
        assert isinstance(data, dict)
        assert "cloudflare" in data

    def test_load_cms_keywords(self):
        data = _load_json("cms_keywords.json")
        assert isinstance(data, dict)
        assert data["wordpress"] == "WordPress"

    def test_load_missing_file_raises(self):
        import pytest
        with pytest.raises(FileNotFoundError):
            _load_json("nonexistent.json")


class TestLoadedConstants:
    def test_bucket_a_is_set(self):
        assert isinstance(BUCKET_A_CMS, set)
        assert "wordpress" in BUCKET_A_CMS

    def test_bucket_b_has_joomla(self):
        assert "joomla" in BUCKET_B_CMS

    def test_bucket_c_has_shopify(self):
        assert "shopify" in BUCKET_C_PLATFORMS

    def test_gdpr_codes_has_healthcare(self):
        assert "86" in GDPR_SENSITIVE_CODES

    def test_gdpr_plugins_is_set(self):
        assert isinstance(GDPR_DATA_HANDLING_PLUGINS, set)
        assert "gravityforms" in GDPR_DATA_HANDLING_PLUGINS

    def test_gdpr_tracking_is_set(self):
        assert isinstance(GDPR_TRACKING_TECH, set)
        assert "google analytics" in GDPR_TRACKING_TECH

    def test_gdpr_ecommerce_is_set(self):
        assert isinstance(GDPR_ECOMMERCE_CMS, set)
        assert "shopify" in GDPR_ECOMMERCE_CMS

    def test_sensitive_tech_is_set(self):
        assert isinstance(SENSITIVE_TECH, set)
        assert "php" in SENSITIVE_TECH

    def test_free_webmail_is_frozenset(self):
        assert isinstance(FREE_WEBMAIL, frozenset)
        assert "gmail.com" in FREE_WEBMAIL

    def test_hosting_providers_is_dict(self):
        assert isinstance(HOSTING_PROVIDERS, dict)
        assert HOSTING_PROVIDERS["cloudflare"] == "Cloudflare"

    def test_cms_keywords_is_dict(self):
        assert isinstance(CMS_KEYWORDS, dict)
        assert CMS_KEYWORDS["woocommerce"] == "WordPress"


class TestConfigJsonIntegrity:
    """Verify JSON files are valid and have expected structure."""

    def test_all_config_files_exist(self):
        expected = [
            "buckets.json", "cms_keywords.json", "filters.json",
            "free_webmail.json", "gdpr_signals.json", "hosting_providers.json",
            "industry_codes.json",
        ]
        for filename in expected:
            assert (CONFIG_DIR / filename).is_file(), f"Missing config file: {filename}"

    def test_all_config_files_are_valid_json(self):
        for path in CONFIG_DIR.glob("*.json"):
            with open(path) as f:
                json.load(f)  # raises on invalid JSON
