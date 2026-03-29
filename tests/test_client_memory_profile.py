"""Tests for client profile CRUD."""

from __future__ import annotations

import pytest

from src.client_memory.profile import ClientProfile
from src.client_memory.storage import AtomicFileStore


@pytest.fixture
def store(tmp_path):
    return AtomicFileStore(str(tmp_path))


@pytest.fixture
def profile(store):
    return ClientProfile(store)


# --- Create ---


def test_create_profile(profile):
    result = profile.create_profile("client-001", "Restaurant Nordlys", "nordlys.dk", "watchman")
    assert result["client_id"] == "client-001"
    assert result["tier"] == "watchman"
    assert result["scan_schedule"] == "weekly"


def test_create_profile_sentinel_daily(profile):
    result = profile.create_profile("client-002", "Test Co", "test.dk", "sentinel")
    assert result["scan_schedule"] == "daily"


def test_create_profile_already_exists(profile):
    profile.create_profile("client-001", "Restaurant Nordlys", "nordlys.dk")
    with pytest.raises(FileExistsError):
        profile.create_profile("client-001", "Duplicate", "duplicate.dk")


def test_create_profile_invalid_tier(profile):
    with pytest.raises(ValueError, match="Invalid tier"):
        profile.create_profile("client-001", "Test", "test.dk", "premium")


# --- Load ---


def test_load_profile(profile):
    profile.create_profile("client-001", "Test Co", "test.dk")
    result = profile.load_profile("client-001")
    assert result is not None
    assert result["company_name"] == "Test Co"


def test_load_profile_not_found(profile):
    result = profile.load_profile("nonexistent")
    assert result is None


# --- Update ---


def test_update_profile(profile):
    profile.create_profile("client-001", "Test Co", "test.dk")
    result = profile.update_profile("client-001", {"last_scan_date": "2026-03-28"})
    assert result["last_scan_date"] == "2026-03-28"
    assert result["company_name"] == "Test Co"  # unchanged fields preserved


def test_update_profile_tier_change(profile):
    profile.create_profile("client-001", "Test Co", "test.dk", "watchman")
    result = profile.update_profile("client-001", {"tier": "guardian"})
    assert result["tier"] == "guardian"
    assert result["scan_schedule"] == "daily"


def test_update_profile_invalid_tier(profile):
    profile.create_profile("client-001", "Test Co", "test.dk")
    with pytest.raises(ValueError):
        profile.update_profile("client-001", {"tier": "invalid"})


def test_update_profile_not_found(profile):
    with pytest.raises(FileNotFoundError):
        profile.update_profile("nonexistent", {"tier": "sentinel"})
