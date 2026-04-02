"""Shared pytest fixtures for Heimdall tests."""
import pytest
from src.prospecting.cvr import Company
from src.prospecting.scanner import ScanResult

@pytest.fixture
def sample_company():
    def _make(cvr="12345678", name="Test Restaurant ApS", industry_code="561110", ad_protected=False, website_domain="test-restaurant.dk", email="info@test-restaurant.dk"):
        return Company(cvr=cvr, name=name, address="Testvej 1", postcode="7100", city="Vejle", company_form="ApS", industry_code=industry_code, industry_name="Servering af mad", phone="12345678", email=email, ad_protected=ad_protected, website_domain=website_domain, discard_reason="")
    return _make

@pytest.fixture
def sample_scan_result():
    def _make(domain="test-restaurant.dk", cms="WordPress", server="Apache/2.4.54", hosting="one.com", ssl_valid=True, ssl_issuer="Let's Encrypt", ssl_expiry="2026-06-01", ssl_days_remaining=60, detected_plugins=None, plugin_versions=None, detected_themes=None, headers=None, tech_stack=None, subdomains=None, dns_records=None, exposed_cloud_storage=None):
        return ScanResult(domain=domain, cms=cms, server=server, hosting=hosting, ssl_valid=ssl_valid, ssl_issuer=ssl_issuer, ssl_expiry=ssl_expiry, ssl_days_remaining=ssl_days_remaining, detected_plugins=detected_plugins or [], plugin_versions=plugin_versions or {}, detected_themes=detected_themes or [], headers=headers or {"x_frame_options": False, "content_security_policy": False, "strict_transport_security": False, "x_content_type_options": False}, tech_stack=tech_stack or ["WordPress:6.9.4", "PHP", "MySQL", "jQuery"], meta_author="", footer_credit="", raw_httpx={}, subdomains=subdomains or [], dns_records=dns_records or {}, ct_certificates=[], exposed_cloud_storage=exposed_cloud_storage or [])
    return _make
