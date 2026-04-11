"""Tests for the CVR enrichment tool."""

from __future__ import annotations

import os
import sqlite3
from unittest.mock import MagicMock, patch

import openpyxl
import pytest

from src.enrichment.db import (
    get_scan_ready_domains,
    init_db,
    log_enrichment,
    populate_domains,
    set_domain_not_ready,
    update_domain,
    update_enrichments,
    upsert_companies,
)
from src.enrichment.domain_deriver import (
    extract_domain_from_email,
    validate_domain_name_match,
)
from src.enrichment.excel_reader import HeaderMismatchError, read_cvr_excel
from src.enrichment.normalizers import (
    check_gdpr_industry,
    extract_email_domain,
    is_free_webmail,
    load_company_forms,
    load_free_webmail,
    load_gdpr_industry_codes,
    lookup_industry_name,
    normalize_company_form,
)
from src.enrichment.search_fallback import SearchError, _extract_domain_from_response

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db(tmp_path):
    """Create a fresh SQLite DB."""
    db_path = tmp_path / "test.db"
    conn = init_db(db_path)
    yield conn
    conn.close()


@pytest.fixture
def sample_companies():
    """Five test companies covering key scenarios."""
    return [
        {
            "cvr": "11111111", "name": "Conrads v/Martin S. Kristensen",
            "address": "Gade 1", "postcode": "7100", "city": "Vejle",
            "company_form": "Enkeltmandsvirksomhed",
            "industry_code": "561110", "industry_name_da": "Servering af mad",
            "phone": "12345678", "email": "bogholderi@conrads.dk",
            "ad_protected": 0, "source_file": "test.xlsx", "source_row": 2,
        },
        {
            "cvr": "22222222", "name": "Restaurant Toscana v/Araz Tofek",
            "address": "Gade 2", "postcode": "7100", "city": "Vejle",
            "company_form": "Enkeltmandsvirksomhed",
            "industry_code": "561110", "industry_name_da": "Servering af mad",
            "phone": "87654321", "email": "villyh@pc.dk",
            "ad_protected": 0, "source_file": "test.xlsx", "source_row": 3,
        },
        {
            "cvr": "33333333", "name": "Casablanca",
            "address": "Gade 3", "postcode": "7100", "city": "Vejle",
            "company_form": "Anpartsselskab",
            "industry_code": "561110", "industry_name_da": "Servering af mad",
            "phone": "", "email": "kai@gmail.com",
            "ad_protected": 0, "source_file": "test.xlsx", "source_row": 4,
        },
        {
            "cvr": "44444444", "name": "Vejle Tandklinik ApS",
            "address": "Gade 4", "postcode": "7100", "city": "Vejle",
            "company_form": "Anpartsselskab",
            "industry_code": "862300", "industry_name_da": "Tandlægevirksomhed",
            "phone": "11223344", "email": "info@vejletandklinik.dk",
            "ad_protected": 1, "source_file": "test.xlsx", "source_row": 5,
        },
        {
            "cvr": "55555555", "name": "No Email Company",
            "address": "Gade 5", "postcode": "7100", "city": "Vejle",
            "company_form": "Aktieselskab",
            "industry_code": "620100", "industry_name_da": "Computerprogrammering",
            "phone": "", "email": "",
            "ad_protected": 0, "source_file": "test.xlsx", "source_row": 6,
        },
    ]


@pytest.fixture
def test_excel(tmp_path):
    """Create a small test Excel file matching CVR export format."""
    path = tmp_path / "test.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append([
        "CVR-nummer/REG-nummer", "Startdato", "Ophørsdato", "Navn",
        "Adresse", "Postnr.", "By", "Virksomhedsform",
        "Hovedbranche", "Telefonnr", "Email", "Reklamebeskyttet",
    ])
    ws.append([
        "11111111", "2020-01-01", "", "Conrads v/Martin S. Kristensen",
        "Gade 1", "7100", "Vejle", "Enkeltmandsvirksomhed",
        "561110 Servering af mad", "12345678", "bogholderi@conrads.dk", "Nej",
    ])
    ws.append([
        "22222222", "2019-05-01", "", "Restaurant Toscana v/Araz Tofek",
        "Gade 2", "7100", "Vejle", "Enkeltmandsvirksomhed",
        "561110 Servering af mad", "87654321", "villyh@pc.dk", "Nej",
    ])
    ws.append([
        "33333333", "2018-03-15", "", "Casablanca",
        "Gade 3", "7100", "Vejle", "Anpartsselskab",
        "561110 Servering af mad", "", "kai@gmail.com", "Nej",
    ])
    wb.save(path)
    return path


@pytest.fixture
def bad_excel(tmp_path):
    """Create an Excel file with wrong column headers."""
    path = tmp_path / "bad.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Wrong", "Headers", "Here"])
    wb.save(path)
    return path


# ---------------------------------------------------------------------------
# Database tests
# ---------------------------------------------------------------------------


class TestDatabase:
    def test_init_creates_tables(self, db):
        tables = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = {t["name"] for t in tables}
        assert "companies" in table_names
        assert "domains" in table_names
        assert "enrichment_log" in table_names

    def test_upsert_companies(self, db, sample_companies):
        count = upsert_companies(db, sample_companies)
        assert count == 5

        row = db.execute("SELECT * FROM companies WHERE cvr = '11111111'").fetchone()
        assert row["name"] == "Conrads v/Martin S. Kristensen"
        assert row["email"] == "bogholderi@conrads.dk"

    def test_upsert_idempotent(self, db, sample_companies):
        upsert_companies(db, sample_companies)
        upsert_companies(db, sample_companies)
        count = db.execute("SELECT COUNT(*) as c FROM companies").fetchone()["c"]
        assert count == 5

    def test_update_enrichments(self, db, sample_companies):
        upsert_companies(db, sample_companies)
        updates = [
            {"cvr": "11111111", "company_form_short": "ENK", "contactable": 1},
            {"cvr": "44444444", "company_form_short": "ApS", "contactable": 0},
        ]
        updated = update_enrichments(db, updates)
        assert updated == 2

        row = db.execute("SELECT * FROM companies WHERE cvr = '11111111'").fetchone()
        assert row["company_form_short"] == "ENK"
        assert row["contactable"] == 1

    def test_update_domain(self, db, sample_companies):
        upsert_companies(db, sample_companies)
        update_domain(db, "11111111", "conrads.dk", "email", 1)
        row = db.execute("SELECT * FROM companies WHERE cvr = '11111111'").fetchone()
        assert row["domain"] == "conrads.dk"
        assert row["domain_source"] == "email"
        assert row["domain_verified"] == 1

    def test_enrichment_log(self, db):
        log_enrichment(db, "11111111", "email_extract", "info@x.dk", "x.dk", True)
        log_enrichment(db, "11111111", "name_match", "x.dk vs X", "0.9", True)
        logs = db.execute("SELECT * FROM enrichment_log WHERE cvr = '11111111'").fetchall()
        assert len(logs) == 2
        assert logs[0]["step"] == "email_extract"
        assert logs[1]["step"] == "name_match"

    def test_populate_domains(self, db, sample_companies):
        upsert_companies(db, sample_companies)
        update_domain(db, "11111111", "conrads.dk", "email", 1)
        update_domain(db, "22222222", "pc.dk", "email", 0)
        count = populate_domains(db)
        assert count == 2

        domains = get_scan_ready_domains(db)
        assert "conrads.dk" in domains
        assert "pc.dk" in domains

    def test_set_domain_not_ready(self, db, sample_companies):
        upsert_companies(db, sample_companies)
        update_domain(db, "11111111", "conrads.dk", "email", 1)
        populate_domains(db)
        set_domain_not_ready(db, "conrads.dk", "filtered:test")

        domains = get_scan_ready_domains(db)
        assert "conrads.dk" not in domains


# ---------------------------------------------------------------------------
# Excel reader tests
# ---------------------------------------------------------------------------


class TestExcelReader:
    def test_read_valid_excel(self, test_excel):
        rows = read_cvr_excel(test_excel)
        assert len(rows) == 3
        assert rows[0]["cvr"] == "11111111"
        assert rows[0]["industry_code"] == "561110"
        assert rows[0]["email"] == "bogholderi@conrads.dk"
        assert rows[0]["ad_protected"] == 0

    def test_header_validation_rejects_bad_excel(self, bad_excel):
        with pytest.raises(HeaderMismatchError, match="do not match"):
            read_cvr_excel(bad_excel)

    def test_industry_code_parsed(self, test_excel):
        rows = read_cvr_excel(test_excel)
        assert rows[0]["industry_code"] == "561110"
        assert rows[0]["industry_name_da"] == "Servering af mad"

    def test_source_tracking(self, test_excel):
        rows = read_cvr_excel(test_excel)
        assert rows[0]["source_file"] == "test.xlsx"
        assert rows[0]["source_row"] == 2


# ---------------------------------------------------------------------------
# Normalizer tests
# ---------------------------------------------------------------------------


class TestNormalizers:
    def test_company_form_normalization(self):
        form_map = load_company_forms()
        assert normalize_company_form("Anpartsselskab", form_map) == "ApS"
        assert normalize_company_form("Aktieselskab", form_map) == "A/S"
        assert normalize_company_form("Enkeltmandsvirksomhed", form_map) == "ENK"
        assert normalize_company_form("Unknown Form", form_map) == "Unknown Form"

    def test_industry_code_prefix_fallback(self):
        industry_map = {"56": "Food service", "561110": "Restaurants"}
        assert lookup_industry_name("561110", industry_map) == "Restaurants"
        assert lookup_industry_name("561200", industry_map) == "Food service"
        assert lookup_industry_name("999999", industry_map) == ""

    def test_gdpr_flagging_positive(self):
        gdpr_codes = load_gdpr_industry_codes()
        is_gdpr, reason = check_gdpr_industry("862300", gdpr_codes)
        assert is_gdpr

    def test_gdpr_flagging_negative(self):
        gdpr_codes = load_gdpr_industry_codes()
        is_gdpr, _ = check_gdpr_industry("561110", gdpr_codes)
        assert not is_gdpr

    def test_gdpr_prefix_match(self):
        gdpr_codes = {"86": "Healthcare"}
        is_gdpr, reason = check_gdpr_industry("861234", gdpr_codes)
        assert is_gdpr
        assert reason == "Healthcare"

    def test_free_webmail_detection(self):
        webmail = load_free_webmail()
        assert is_free_webmail("gmail.com", webmail)
        assert is_free_webmail("hotmail.com", webmail)
        assert not is_free_webmail("conrads.dk", webmail)

    def test_email_domain_extraction(self):
        assert extract_email_domain("info@conrads.dk") == "conrads.dk"
        assert extract_email_domain("") == ""
        assert extract_email_domain("noemail") == ""


# ---------------------------------------------------------------------------
# Domain deriver tests
# ---------------------------------------------------------------------------


class TestDomainDeriver:
    def test_extract_domain_from_email(self):
        assert extract_domain_from_email("info@conrads.dk") == "conrads.dk"
        assert extract_domain_from_email("") == ""
        assert extract_domain_from_email("no-at-sign") == ""

    def test_name_match_conrads(self):
        is_match, ratio = validate_domain_name_match("conrads.dk", "Conrads v/Martin S. Kristensen")
        assert is_match
        assert ratio == 1.0

    def test_name_match_jellingkro(self):
        is_match, _ = validate_domain_name_match("jellingkro.dk", "Jelling Kro v/Dorthe Madsen")
        assert is_match

    def test_name_mismatch_pc(self):
        is_match, ratio = validate_domain_name_match("pc.dk", "Restaurant Toscana v/Araz Tofek")
        assert not is_match

    def test_name_mismatch_accountant(self):
        is_match, _ = validate_domain_name_match("vejleskat.dk", "Casablanca")
        assert not is_match

    def test_name_match_empty_inputs(self):
        is_match, _ = validate_domain_name_match("", "Some Company")
        assert not is_match
        is_match, _ = validate_domain_name_match("example.dk", "")
        assert not is_match


# ---------------------------------------------------------------------------
# Search fallback tests
# ---------------------------------------------------------------------------


class TestSearchFallback:
    def test_extract_domain_simple(self):
        assert _extract_domain_from_response("toscanavejle.dk") == "toscanavejle.dk"

    def test_extract_domain_with_protocol(self):
        assert _extract_domain_from_response("https://toscanavejle.dk") == "toscanavejle.dk"

    def test_extract_domain_with_path(self):
        assert _extract_domain_from_response("https://toscanavejle.dk/menu") == "toscanavejle.dk"

    def test_extract_domain_from_sentence(self):
        assert _extract_domain_from_response("The website is toscanavejle.dk") == "toscanavejle.dk"

    def test_extract_domain_none_response(self):
        assert _extract_domain_from_response("NONE") == ""
        assert _extract_domain_from_response("none") == ""

    def test_extract_domain_empty(self):
        assert _extract_domain_from_response("") == ""

    @patch("src.enrichment.search_fallback._get_anthropic_client")
    @patch("src.enrichment.search_fallback._serper_search")
    def test_search_company_domain_success(self, mock_serper, mock_claude):
        from src.enrichment.search_fallback import search_company_domain

        # Serper returns 3 results
        mock_serper.return_value = [
            {"title": "Restaurant Toscana - TripAdvisor", "link": "https://tripadvisor.com/toscana", "snippet": "Reviews", "position": 1},
            {"title": "Toscana Vejle - Italian Restaurant", "link": "https://toscanavejle.dk/", "snippet": "Welcome", "position": 2},
            {"title": "Toscana Vejle - Google Maps", "link": "https://maps.google.com/...", "snippet": "Map", "position": 3},
        ]

        # Claude picks the right one
        mock_client = MagicMock()
        mock_claude.return_value = mock_client
        mock_block = MagicMock()
        mock_block.text = "toscanavejle.dk"
        mock_response = MagicMock()
        mock_response.content = [mock_block]
        mock_response.usage.input_tokens = 200
        mock_response.usage.output_tokens = 10
        mock_client.messages.create.return_value = mock_response

        os.environ["SERPER_API_KEY"] = "test-key"
        try:
            domain, detail = search_company_domain("Restaurant Toscana", "Vejle", delay=0)
            assert domain == "toscanavejle.dk"
            mock_serper.assert_called_once()
            mock_client.messages.create.assert_called_once()
        finally:
            os.environ.pop("SERPER_API_KEY", None)

    @patch("src.enrichment.search_fallback._serper_search")
    def test_search_company_domain_no_results(self, mock_serper):
        from src.enrichment.search_fallback import search_company_domain

        mock_serper.return_value = []

        os.environ["SERPER_API_KEY"] = "test-key"
        try:
            domain, detail = search_company_domain("Unknown Company XYZ", "Vejle", delay=0)
            assert domain == ""
            assert "0 results" in detail
        finally:
            os.environ.pop("SERPER_API_KEY", None)

    def test_search_missing_env_vars(self):
        from src.enrichment.search_fallback import search_company_domain

        # Ensure env vars are not set
        os.environ.pop("SERPER_API_KEY", None)

        with pytest.raises(SearchError, match="SERPER_API_KEY"):
            search_company_domain("Test", "Vejle", delay=0)


# ---------------------------------------------------------------------------
# Integration: full pipeline (search mocked)
# ---------------------------------------------------------------------------


class TestFullPipeline:
    @patch("src.enrichment.pipeline.search_company_domain")
    def test_pipeline_skip_search(self, mock_search, tmp_path, test_excel):
        from src.enrichment.pipeline import run_pipeline

        db_path = tmp_path / "test.db"
        stats = run_pipeline(
            input_path=test_excel,
            db_path=db_path,
            skip_search=True,
        )

        assert stats["total_ingested"] == 3
        assert stats["email_derived"] >= 1
        mock_search.assert_not_called()

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        count = conn.execute("SELECT COUNT(*) as c FROM companies").fetchone()["c"]
        assert count == 3
        conn.close()

    @patch("src.enrichment.pipeline.search_company_domain")
    def test_pipeline_with_search(self, mock_search, tmp_path, test_excel):
        from src.enrichment.pipeline import run_pipeline

        mock_search.return_value = ("toscanavejle.dk", "mocked response")

        db_path = tmp_path / "test.db"
        stats = run_pipeline(
            input_path=test_excel,
            db_path=db_path,
            skip_search=False,
            search_delay=0,
        )

        assert stats["total_ingested"] == 3
        assert stats["search_derived"] >= 1

    @patch("src.enrichment.pipeline.search_company_domain")
    def test_pipeline_idempotent(self, mock_search, tmp_path, test_excel):
        from src.enrichment.pipeline import run_pipeline

        mock_search.return_value = ("toscanavejle.dk", "mocked")
        db_path = tmp_path / "test.db"

        run_pipeline(test_excel, db_path,
                     skip_search=False, search_delay=0)
        stats = run_pipeline(test_excel, db_path,
                             skip_search=False, search_delay=0)

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        count = conn.execute("SELECT COUNT(*) as c FROM companies").fetchone()["c"]
        assert count == 3
        conn.close()

        assert stats["search_skipped"] >= 1
