"""Tests for src.db.clients — industries, clients, and client_domains CRUD."""

from __future__ import annotations

import sqlite3

import pytest

from src.db import init_db
from src.db.clients import (
    add_domain,
    bulk_upsert_industries,
    create_client,
    get_client,
    get_client_by_domain,
    get_domains,
    list_clients,
    update_client,
    upsert_industry,
)


@pytest.fixture()
def db(tmp_path):
    """Create a fresh in-memory-style test DB with full schema."""
    conn = init_db(tmp_path / "test.db")
    yield conn
    conn.close()


# -----------------------------------------------------------------------
# Industries
# -----------------------------------------------------------------------


class TestUpsertIndustry:
    def test_upsert_industry_insert_and_update(self, db):
        """Insert a new industry, then update name_en — verify both."""
        upsert_industry(db, "561010", name_en="Restaurants")
        row = db.execute("SELECT * FROM industries WHERE code = '561010'").fetchone()
        assert row is not None
        assert dict(row)["name_en"] == "Restaurants"
        assert dict(row)["name_da"] == ""

        # Update name_en, add name_da.
        upsert_industry(db, "561010", name_da="Restauranter", name_en="Restaurants v2")
        row = db.execute("SELECT * FROM industries WHERE code = '561010'").fetchone()
        assert dict(row)["name_en"] == "Restaurants v2"
        assert dict(row)["name_da"] == "Restauranter"

    def test_bulk_upsert_industries(self, db):
        """Bulk insert 3 rows and verify count + data."""
        rows = [
            {"code": "561010", "name_en": "Restaurants"},
            {"code": "620100", "name_en": "Computer programming"},
            {"code": "862200", "name_en": "Specialist medical practice"},
        ]
        count = bulk_upsert_industries(db, rows)
        assert count == 3

        all_rows = db.execute("SELECT * FROM industries ORDER BY code").fetchall()
        assert len(all_rows) == 3
        assert dict(all_rows[0])["code"] == "561010"
        assert dict(all_rows[1])["name_en"] == "Computer programming"

    def test_bulk_upsert_industries_empty(self, db):
        """Empty list returns 0 and writes nothing."""
        assert bulk_upsert_industries(db, []) == 0


# -----------------------------------------------------------------------
# Clients — create / get
# -----------------------------------------------------------------------


class TestCreateAndGetClient:
    def test_create_and_get_client(self, db):
        """Create a client, then retrieve by CVR — verify all fields."""
        client = create_client(
            db,
            cvr="12345678",
            company_name="Restaurant Nordlys ApS",
            plan="watchman",
            status="active",
            contact_name="Peter Nielsen",
            contact_email="peter@nordlys.dk",
            telegram_chat_id="123456",
        )

        assert client["cvr"] == "12345678"
        assert client["company_name"] == "Restaurant Nordlys ApS"
        assert client["plan"] == "watchman"
        assert client["status"] == "active"
        assert client["contact_name"] == "Peter Nielsen"
        assert client["contact_email"] == "peter@nordlys.dk"
        assert client["telegram_chat_id"] == "123456"
        assert client["consent_granted"] == 0  # default

        # get_client returns the same data.
        fetched = get_client(db, "12345678")
        assert fetched is not None
        assert fetched["cvr"] == "12345678"
        assert fetched["company_name"] == "Restaurant Nordlys ApS"

    def test_create_client_sets_timestamps(self, db):
        """Verify created_at and updated_at are set as ISO-8601."""
        client = create_client(db, cvr="11111111", company_name="Test Co")
        assert client["created_at"] is not None
        assert client["updated_at"] is not None
        # Both should be identical on creation.
        assert client["created_at"] == client["updated_at"]
        # Basic ISO-8601 shape check: YYYY-MM-DDTHH:MM:SSZ
        assert "T" in client["created_at"]
        assert client["created_at"].endswith("Z")

    def test_create_client_defaults(self, db):
        """Client with only required fields gets correct defaults."""
        client = create_client(db, cvr="22222222", company_name="Defaults Co")
        assert client["status"] == "prospect"
        assert client["plan"] is None
        assert client["consent_granted"] == 0
        assert client["gdpr_sensitive"] == 0

    def test_get_client_not_found(self, db):
        """get_client returns None for non-existent CVR."""
        assert get_client(db, "99999999") is None


# -----------------------------------------------------------------------
# Clients — validation
# -----------------------------------------------------------------------


class TestClientValidation:
    def test_create_client_invalid_plan(self, db):
        """plan='invalid' raises ValueError."""
        with pytest.raises(ValueError, match="Invalid plan"):
            create_client(db, cvr="33333333", company_name="Bad Plan Co", plan="invalid")

    def test_create_client_invalid_status(self, db):
        """status='invalid' raises ValueError."""
        with pytest.raises(ValueError, match="Invalid status"):
            create_client(db, cvr="44444444", company_name="Bad Status Co", status="invalid")

    def test_create_client_duplicate_cvr(self, db):
        """Inserting the same CVR twice raises IntegrityError."""
        create_client(db, cvr="55555555", company_name="First Co")
        with pytest.raises(sqlite3.IntegrityError):
            create_client(db, cvr="55555555", company_name="Duplicate Co")


# -----------------------------------------------------------------------
# Clients — update
# -----------------------------------------------------------------------


class TestUpdateClient:
    def test_update_client(self, db):
        """Update contact_name — verify change + updated_at changed."""
        create_client(db, cvr="66666666", company_name="Update Co")
        original = get_client(db, "66666666")
        assert original is not None

        updated = update_client(db, "66666666", {"contact_name": "New Name"})
        assert updated["contact_name"] == "New Name"
        assert updated["updated_at"] >= original["updated_at"]

    def test_update_client_immutable_cvr(self, db):
        """Attempting to update cvr raises ValueError."""
        create_client(db, cvr="77777777", company_name="Immutable CVR Co")
        with pytest.raises(ValueError, match="Cannot change the 'cvr' column"):
            update_client(db, "77777777", {"cvr": "88888888"})

    def test_update_client_invalid_plan(self, db):
        """Updating plan to invalid value raises ValueError."""
        create_client(db, cvr="88888888", company_name="Plan Update Co")
        with pytest.raises(ValueError, match="Invalid plan"):
            update_client(db, "88888888", {"plan": "enterprise"})

    def test_update_client_invalid_status(self, db):
        """Updating status to invalid value raises ValueError."""
        create_client(db, cvr="99999999", company_name="Status Update Co")
        with pytest.raises(ValueError, match="Invalid status"):
            update_client(db, "99999999", {"status": "deleted"})

    def test_update_client_not_found(self, db):
        """Updating a non-existent client raises KeyError."""
        with pytest.raises(KeyError, match="not found"):
            update_client(db, "00000000", {"contact_name": "Ghost"})


# -----------------------------------------------------------------------
# Clients — list
# -----------------------------------------------------------------------


class TestListClients:
    def test_list_clients_all(self, db):
        """Create 3 clients, list returns all 3."""
        create_client(db, cvr="10000001", company_name="Alpha Co")
        create_client(db, cvr="10000002", company_name="Beta Co")
        create_client(db, cvr="10000003", company_name="Gamma Co")

        clients = list_clients(db)
        assert len(clients) == 3

    def test_list_clients_by_status(self, db):
        """Create 2 prospect + 1 active, filter by status."""
        create_client(db, cvr="20000001", company_name="Prospect A")
        create_client(db, cvr="20000002", company_name="Prospect B")
        create_client(db, cvr="20000003", company_name="Active C", status="active")

        prospects = list_clients(db, status="prospect")
        assert len(prospects) == 2

        actives = list_clients(db, status="active")
        assert len(actives) == 1
        assert actives[0]["company_name"] == "Active C"

    def test_list_clients_empty(self, db):
        """Empty database returns empty list."""
        assert list_clients(db) == []


# -----------------------------------------------------------------------
# Client domains
# -----------------------------------------------------------------------


class TestClientDomains:
    def test_add_and_get_domains(self, db):
        """Add 2 domains to a client, get returns both."""
        create_client(db, cvr="30000001", company_name="Multi Domain Co")
        add_domain(db, "30000001", "primary.dk", is_primary=1)
        add_domain(db, "30000001", "secondary.dk", is_primary=0)

        domains = get_domains(db, "30000001")
        assert len(domains) == 2
        # Primary domain should sort first.
        assert domains[0]["domain"] == "primary.dk"
        assert domains[0]["is_primary"] == 1
        assert domains[1]["domain"] == "secondary.dk"
        assert domains[1]["is_primary"] == 0
        # added_at should be set.
        assert domains[0]["added_at"] is not None

    def test_domain_unique_constraint(self, db):
        """Adding same (cvr, domain) twice raises IntegrityError."""
        create_client(db, cvr="30000002", company_name="Unique Domain Co")
        add_domain(db, "30000002", "example.dk")
        with pytest.raises(sqlite3.IntegrityError):
            add_domain(db, "30000002", "example.dk")

    def test_get_domains_empty(self, db):
        """Client with no domains returns empty list."""
        create_client(db, cvr="30000003", company_name="No Domain Co")
        assert get_domains(db, "30000003") == []

    def test_get_client_by_domain(self, db):
        """Reverse lookup: domain -> client works."""
        create_client(db, cvr="40000001", company_name="Lookup Co")
        add_domain(db, "40000001", "lookup.dk")

        client = get_client_by_domain(db, "lookup.dk")
        assert client is not None
        assert client["cvr"] == "40000001"
        assert client["company_name"] == "Lookup Co"

    def test_get_client_by_domain_not_found(self, db):
        """Reverse lookup for unknown domain returns None."""
        assert get_client_by_domain(db, "nonexistent.dk") is None
