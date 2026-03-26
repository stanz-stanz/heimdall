"""Tests for brief_generator: generate_brief() and _determine_gdpr_sensitivity()."""

import pytest
from datetime import date

from src.prospecting.brief_generator import generate_brief, _determine_gdpr_sensitivity


# ---------------------------------------------------------------------------
# 1. SSL findings
# ---------------------------------------------------------------------------

class TestSSLFindings:
    """Test SSL certificate findings at different severity thresholds."""

    def test_expired_ssl_is_critical(self, sample_company, sample_scan_result):
        company = sample_company()
        scan = sample_scan_result(ssl_valid=False, ssl_days_remaining=-5)
        brief = generate_brief(company, scan, "A")
        ssl_findings = [f for f in brief["findings"] if "SSL" in f["description"] or "ssl" in f["description"].lower()]
        assert len(ssl_findings) == 1
        assert ssl_findings[0]["severity"] == "critical"
        assert "expired" in ssl_findings[0]["description"].lower()

    def test_no_ssl_certificate_is_critical(self, sample_company, sample_scan_result):
        company = sample_company()
        scan = sample_scan_result(ssl_valid=False, ssl_days_remaining=-1)
        brief = generate_brief(company, scan, "A")
        ssl_findings = [f for f in brief["findings"] if "SSL" in f["description"] or "ssl" in f["description"].lower()]
        assert len(ssl_findings) == 1
        assert ssl_findings[0]["severity"] == "critical"
        assert "No SSL" in ssl_findings[0]["description"]

    def test_ssl_expiring_under_14_days_is_high(self, sample_company, sample_scan_result):
        company = sample_company()
        scan = sample_scan_result(ssl_valid=True, ssl_days_remaining=10)
        brief = generate_brief(company, scan, "A")
        ssl_findings = [f for f in brief["findings"] if "expires in" in f["description"]]
        assert len(ssl_findings) == 1
        assert ssl_findings[0]["severity"] == "high"
        assert "10 days" in ssl_findings[0]["description"]

    def test_ssl_expiring_under_30_days_is_medium(self, sample_company, sample_scan_result):
        company = sample_company()
        scan = sample_scan_result(ssl_valid=True, ssl_days_remaining=25)
        brief = generate_brief(company, scan, "A")
        ssl_findings = [f for f in brief["findings"] if "expires in" in f["description"]]
        assert len(ssl_findings) == 1
        assert ssl_findings[0]["severity"] == "medium"
        assert "25 days" in ssl_findings[0]["description"]

    def test_ssl_valid_over_30_days_no_finding(self, sample_company, sample_scan_result):
        company = sample_company()
        scan = sample_scan_result(ssl_valid=True, ssl_days_remaining=90)
        brief = generate_brief(company, scan, "A")
        ssl_findings = [f for f in brief["findings"]
                        if "SSL" in f["description"] or "ssl" in f["description"].lower()]
        assert len(ssl_findings) == 0


# ---------------------------------------------------------------------------
# 2. Security header findings
# ---------------------------------------------------------------------------

class TestHeaderFindings:
    """Test that each missing header produces the correct severity."""

    def test_missing_hsts_is_medium(self, sample_company, sample_scan_result):
        company = sample_company()
        scan = sample_scan_result(headers={
            "strict_transport_security": False,
            "content_security_policy": True,
            "x_frame_options": True,
            "x_content_type_options": True,
        })
        brief = generate_brief(company, scan, "A")
        hsts = [f for f in brief["findings"] if "HSTS" in f["description"]]
        assert len(hsts) == 1
        assert hsts[0]["severity"] == "medium"

    def test_missing_csp_is_low(self, sample_company, sample_scan_result):
        company = sample_company()
        scan = sample_scan_result(headers={
            "strict_transport_security": True,
            "content_security_policy": False,
            "x_frame_options": True,
            "x_content_type_options": True,
        })
        brief = generate_brief(company, scan, "A")
        csp = [f for f in brief["findings"] if "Content-Security-Policy" in f["description"]]
        assert len(csp) == 1
        assert csp[0]["severity"] == "low"

    def test_missing_x_frame_options_is_low(self, sample_company, sample_scan_result):
        company = sample_company()
        scan = sample_scan_result(headers={
            "strict_transport_security": True,
            "content_security_policy": True,
            "x_frame_options": False,
            "x_content_type_options": True,
        })
        brief = generate_brief(company, scan, "A")
        xfo = [f for f in brief["findings"] if "X-Frame-Options" in f["description"]]
        assert len(xfo) == 1
        assert xfo[0]["severity"] == "low"

    def test_missing_x_content_type_options_is_low(self, sample_company, sample_scan_result):
        company = sample_company()
        scan = sample_scan_result(headers={
            "strict_transport_security": True,
            "content_security_policy": True,
            "x_frame_options": True,
            "x_content_type_options": False,
        })
        brief = generate_brief(company, scan, "A")
        xcto = [f for f in brief["findings"] if "X-Content-Type-Options" in f["description"]]
        assert len(xcto) == 1
        assert xcto[0]["severity"] == "low"

    def test_all_headers_present_no_header_findings(self, sample_company, sample_scan_result):
        company = sample_company()
        scan = sample_scan_result(headers={
            "strict_transport_security": True,
            "content_security_policy": True,
            "x_frame_options": True,
            "x_content_type_options": True,
        })
        brief = generate_brief(company, scan, "A")
        header_findings = [f for f in brief["findings"] if "header" in f["description"].lower() or "HSTS" in f["description"]]
        assert len(header_findings) == 0


# ---------------------------------------------------------------------------
# 3. CMS version findings
# ---------------------------------------------------------------------------

class TestCMSFindings:
    """Test CMS version disclosure findings."""

    def test_wordpress_version_disclosed_is_medium(self, sample_company, sample_scan_result):
        company = sample_company()
        scan = sample_scan_result(cms="WordPress", tech_stack=["WordPress:6.9.4"])
        brief = generate_brief(company, scan, "A")
        cms_findings = [f for f in brief["findings"] if "version" in f["description"].lower() and "WordPress" in f["description"]]
        assert len(cms_findings) == 1
        assert cms_findings[0]["severity"] == "medium"
        assert "6.9.4" in cms_findings[0]["description"]

    def test_wordpress_no_version_is_low(self, sample_company, sample_scan_result):
        company = sample_company()
        scan = sample_scan_result(cms="WordPress", tech_stack=["PHP", "MySQL"])
        brief = generate_brief(company, scan, "A")
        cms_findings = [f for f in brief["findings"] if "WordPress" in f["description"] and "version not determined" in f["description"]]
        assert len(cms_findings) == 1
        assert cms_findings[0]["severity"] == "low"

    def test_no_cms_no_cms_finding(self, sample_company, sample_scan_result):
        company = sample_company()
        scan = sample_scan_result(cms="", tech_stack=["PHP", "MySQL"])
        brief = generate_brief(company, scan, "A")
        cms_findings = [f for f in brief["findings"] if "CMS" in f["description"] or "WordPress" in f["description"] or "version" in f["description"].lower()]
        assert len(cms_findings) == 0


# ---------------------------------------------------------------------------
# 4. Plugin findings
# ---------------------------------------------------------------------------

class TestPluginFindings:
    """Test plugin detection findings."""

    def test_data_handling_plugin_is_medium(self, sample_company, sample_scan_result):
        company = sample_company()
        scan = sample_scan_result(
            detected_plugins=["gravity-forms"],
            tech_stack=["WordPress:6.9.4"],
        )
        brief = generate_brief(company, scan, "A")
        plugin_findings = [f for f in brief["findings"] if "Data-handling" in f["description"]]
        assert len(plugin_findings) == 1
        assert plugin_findings[0]["severity"] == "medium"

    def test_non_data_plugin_is_info(self, sample_company, sample_scan_result):
        company = sample_company()
        scan = sample_scan_result(
            detected_plugins=["jetpack", "yoast-seo"],
            tech_stack=["WordPress:6.9.4"],
        )
        brief = generate_brief(company, scan, "A")
        info_findings = [f for f in brief["findings"] if "plugin" in f["description"].lower() and f["severity"] == "info"]
        assert len(info_findings) == 1

    def test_no_plugins_no_finding(self, sample_company, sample_scan_result):
        company = sample_company()
        scan = sample_scan_result(detected_plugins=[], tech_stack=["WordPress:6.9.4"])
        brief = generate_brief(company, scan, "A")
        plugin_findings = [f for f in brief["findings"] if "plugin" in f["description"].lower()]
        assert len(plugin_findings) == 0


# ---------------------------------------------------------------------------
# 5. Backend technology findings
# ---------------------------------------------------------------------------

class TestBackendTechFindings:
    """Test backend technology exposure findings."""

    def test_php_mysql_exposed_is_low(self, sample_company, sample_scan_result):
        company = sample_company()
        scan = sample_scan_result(tech_stack=["PHP", "MySQL"])
        brief = generate_brief(company, scan, "A")
        tech_findings = [f for f in brief["findings"] if "Backend technology" in f["description"]]
        assert len(tech_findings) == 1
        assert tech_findings[0]["severity"] == "low"
        assert "PHP" in tech_findings[0]["description"]
        assert "MySQL" in tech_findings[0]["description"]

    def test_no_sensitive_tech_no_finding(self, sample_company, sample_scan_result):
        company = sample_company()
        scan = sample_scan_result(tech_stack=["jQuery", "Bootstrap"])
        brief = generate_brief(company, scan, "A")
        tech_findings = [f for f in brief["findings"] if "Backend technology" in f["description"]]
        assert len(tech_findings) == 0


# ---------------------------------------------------------------------------
# 6. Cloud storage findings
# ---------------------------------------------------------------------------

class TestCloudStorageFindings:
    """Test exposed cloud storage findings."""

    def test_exposed_bucket_is_high(self, sample_company, sample_scan_result):
        company = sample_company()
        scan = sample_scan_result(
            exposed_cloud_storage=[{"bucket_name": "test-bucket", "file_count": 42}],
        )
        brief = generate_brief(company, scan, "A")
        cloud_findings = [f for f in brief["findings"] if "cloud storage" in f["description"].lower()]
        assert len(cloud_findings) == 1
        assert cloud_findings[0]["severity"] == "high"

    def test_no_cloud_exposure_no_finding(self, sample_company, sample_scan_result):
        company = sample_company()
        scan = sample_scan_result(exposed_cloud_storage=[])
        brief = generate_brief(company, scan, "A")
        cloud_findings = [f for f in brief["findings"] if "cloud storage" in f["description"].lower()]
        assert len(cloud_findings) == 0


# ---------------------------------------------------------------------------
# 7. Subdomain findings
# ---------------------------------------------------------------------------

class TestSubdomainFindings:
    """Test subdomain detection findings."""

    def test_subdomains_found_is_info(self, sample_company, sample_scan_result):
        company = sample_company()
        scan = sample_scan_result(
            subdomains=["mail.test.dk", "dev.test.dk", "staging.test.dk"],
        )
        brief = generate_brief(company, scan, "A")
        sub_findings = [f for f in brief["findings"] if "subdomain" in f["description"].lower()]
        assert len(sub_findings) == 1
        assert sub_findings[0]["severity"] == "info"
        assert "3" in sub_findings[0]["description"]

    def test_no_subdomains_no_finding(self, sample_company, sample_scan_result):
        company = sample_company()
        scan = sample_scan_result(subdomains=[])
        brief = generate_brief(company, scan, "A")
        sub_findings = [f for f in brief["findings"] if "subdomain" in f["description"].lower()]
        assert len(sub_findings) == 0


# ---------------------------------------------------------------------------
# 8. GDPR — industry code sensitivity
# ---------------------------------------------------------------------------

class TestGDPRIndustryCode:
    """Test GDPR sensitivity determination from industry codes."""

    def test_healthcare_code_86_is_sensitive(self, sample_company, sample_scan_result):
        company = sample_company(industry_code="86")
        scan = sample_scan_result(detected_plugins=[], tech_stack=[])
        result = _determine_gdpr_sensitivity(company, scan)
        assert result["sensitive"] is True
        assert any("Healthcare" in r for r in result["reasons"])

    def test_restaurant_code_561110_not_sensitive_from_code_alone(self, sample_company, sample_scan_result):
        company = sample_company(industry_code="561110")
        scan = sample_scan_result(detected_plugins=[], tech_stack=[])
        result = _determine_gdpr_sensitivity(company, scan)
        assert result["sensitive"] is False
        assert len(result["reasons"]) == 0


# ---------------------------------------------------------------------------
# 9. GDPR — scan evidence
# ---------------------------------------------------------------------------

class TestGDPRScanEvidence:
    """Test GDPR sensitivity from scan evidence (plugins, tracking)."""

    def test_gravity_forms_and_recaptcha_is_sensitive(self, sample_company, sample_scan_result):
        company = sample_company(industry_code="561110")
        scan = sample_scan_result(
            detected_plugins=["gravity-forms"],
            tech_stack=["reCAPTCHA"],
        )
        result = _determine_gdpr_sensitivity(company, scan)
        assert result["sensitive"] is True
        assert any("Data-handling" in r for r in result["reasons"])
        assert any("tracking" in r.lower() or "Visitor" in r for r in result["reasons"])

    def test_no_plugins_no_tracking_not_sensitive(self, sample_company, sample_scan_result):
        company = sample_company(industry_code="561110")
        scan = sample_scan_result(detected_plugins=[], tech_stack=["jQuery"])
        result = _determine_gdpr_sensitivity(company, scan)
        assert result["sensitive"] is False


# ---------------------------------------------------------------------------
# 10. GDPR — combined (evidence overrides industry code)
# ---------------------------------------------------------------------------

class TestGDPRCombined:
    """Test that scan evidence can make a non-sensitive industry sensitive."""

    def test_restaurant_with_booking_plugin_is_sensitive(self, sample_company, sample_scan_result):
        company = sample_company(industry_code="561110")
        scan = sample_scan_result(
            detected_plugins=["booket-bord"],
            tech_stack=["WordPress:6.9.4"],
        )
        result = _determine_gdpr_sensitivity(company, scan)
        assert result["sensitive"] is True
        assert any("Data-handling" in r for r in result["reasons"])


# ---------------------------------------------------------------------------
# 11. Brief schema completeness
# ---------------------------------------------------------------------------

class TestBriefSchema:
    """Test that generate_brief output has all required fields."""

    def test_brief_has_all_required_fields(self, sample_company, sample_scan_result):
        company = sample_company()
        scan = sample_scan_result()
        brief = generate_brief(company, scan, "A")

        required_fields = [
            "domain", "cvr", "findings", "gdpr_sensitive",
            "gdpr_reasons", "technology", "subdomains", "dns",
            "cloud_exposure",
        ]
        for field in required_fields:
            assert field in brief, f"Missing required field: {field}"

        # Verify types
        assert isinstance(brief["findings"], list)
        assert isinstance(brief["gdpr_sensitive"], bool)
        assert isinstance(brief["gdpr_reasons"], list)
        assert isinstance(brief["technology"], dict)
        assert isinstance(brief["subdomains"], dict)
        assert isinstance(brief["cloud_exposure"], list)

    def test_brief_domain_matches_company(self, sample_company, sample_scan_result):
        company = sample_company(website_domain="example.dk")
        scan = sample_scan_result(domain="example.dk")
        brief = generate_brief(company, scan, "B")
        assert brief["domain"] == "example.dk"
        assert brief["cvr"] == company.cvr
        assert brief["bucket"] == "B"
        assert brief["scan_date"] == date.today().isoformat()
