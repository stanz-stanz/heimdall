"""Shared pytest fixtures for Heimdall tests."""
import pytest

from src.prospecting.cvr import Company
from src.prospecting.scanners import registry as _scanner_registry
from src.prospecting.scanners.models import ScanResult


# ---------------------------------------------------------------------------
# Dev-stack integration test gating
# ---------------------------------------------------------------------------
#
# Tests under `tests/integration/` need the live dev stack (`make dev-up`)
# and gitignored secret files (`infra/compose/secrets.dev/console_password`,
# …) that do not exist in fresh git worktrees. Default `pytest -q` runs
# used to error there; opt in via `--run-integration` instead. When the
# flag is given, the existing fail-loud fixtures inside
# `tests/integration/conftest.py` still apply — they refuse to silently
# skip if the stack is opted-into but unreachable.
#
# The skip is scoped to the `tests/integration/` directory rather than the
# `integration` pytest marker, because the marker is also used by
# self-contained local-HTTP tests (e.g. `test_twin_regression.py`) that
# do **not** need `make dev-up` and should keep running by default.

import os as _os


def pytest_addoption(parser):
    parser.addoption(
        "--run-integration",
        action="store_true",
        default=False,
        help=(
            "Run dev-stack integration tests under `tests/integration/` "
            "(require `make dev-up` and `infra/compose/secrets.dev/`)."
        ),
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-integration"):
        return
    dev_stack_dir = _os.path.join("tests", "integration") + _os.sep
    skip_dev_stack = pytest.mark.skip(
        reason=(
            "dev-stack integration test — needs live dev stack + secrets; "
            "opt in with --run-integration"
        )
    )
    for item in items:
        if dev_stack_dir in str(item.fspath):
            item.add_marker(skip_dev_stack)


@pytest.fixture(autouse=True)
def _refresh_scanner_registry_each_test():
    """Refresh the scan-type registry before every test.

    ``_init_scan_type_map`` is one-shot per process for production
    hot-path performance. That means a level dict patched by an earlier
    test (via ``_force_reinit_scan_type_map`` while a
    ``unittest.mock.patch`` was active) leaks its mock references into
    subsequent tests after the patch context unwinds. Calling
    ``_force_reinit_scan_type_map`` here rebuilds the dispatch from
    canonical imports so each test starts against the real scanner
    functions; tests that need patches still call
    ``_force_reinit_scan_type_map`` themselves while their patch is
    active.
    """
    _scanner_registry._force_reinit_scan_type_map()
    yield


@pytest.fixture
def sample_company():
    def _make(cvr="12345678", name="Test Restaurant ApS", industry_code="561110", ad_protected=False, website_domain="test-restaurant.dk", email="info@test-restaurant.dk"):
        return Company(cvr=cvr, name=name, address="Testvej 1", postcode="7100", city="Vejle", company_form="ApS", industry_code=industry_code, industry_name="Servering af mad", phone="12345678", email=email, ad_protected=ad_protected, website_domain=website_domain, discard_reason="")
    return _make

@pytest.fixture
def sample_scan_result():
    def _make(domain="test-restaurant.dk", cms="WordPress", server="Apache/2.4.54", hosting="one.com", ssl_valid=True, ssl_issuer="Let's Encrypt", ssl_expiry="2026-06-01", ssl_days_remaining=60, detected_plugins=None, plugin_versions=None, detected_themes=None, headers=None, tech_stack=None, subdomains=None, dns_records=None, exposed_cloud_storage=None, tls_version="TLSv1.3", tls_cipher="TLS_AES_256_GCM_SHA384", tls_bits=256):
        return ScanResult(domain=domain, cms=cms, server=server, hosting=hosting, ssl_valid=ssl_valid, ssl_issuer=ssl_issuer, ssl_expiry=ssl_expiry, ssl_days_remaining=ssl_days_remaining, detected_plugins=detected_plugins or [], plugin_versions=plugin_versions or {}, detected_themes=detected_themes or [], headers=headers or {"x_frame_options": False, "content_security_policy": False, "strict_transport_security": False, "x_content_type_options": False, "permissions_policy": False, "referrer_policy": False, "server_value": "", "x_powered_by": ""}, tech_stack=tech_stack or ["WordPress:6.9.4", "PHP", "MySQL", "jQuery"], meta_author="", footer_credit="", raw_httpx={}, subdomains=subdomains or [], dns_records=dns_records or {}, ct_certificates=[], tls_version=tls_version, tls_cipher=tls_cipher, tls_bits=tls_bits, exposed_cloud_storage=exposed_cloud_storage or [])
    return _make
