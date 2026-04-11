"""Client profile — CRUD for per-client profile.json."""

from __future__ import annotations

from loguru import logger

from .storage import AtomicFileStore

_VALID_TIERS = {"watchman", "sentinel", "guardian"}


class ClientProfile:
    """Manages client profile.json files."""

    def __init__(self, store: AtomicFileStore) -> None:
        self.store = store

    def create_profile(
        self,
        client_id: str,
        company_name: str,
        domain: str,
        tier: str = "watchman",
        **kwargs,
    ) -> dict:
        """Create a new client profile. Raises if already exists."""
        if self.store.exists(client_id, "profile.json"):
            raise FileExistsError(f"Profile already exists for {client_id}")

        if tier not in _VALID_TIERS:
            raise ValueError(f"Invalid tier '{tier}'. Must be one of: {_VALID_TIERS}")

        profile = {
            "client_id": client_id,
            "company_name": company_name,
            "domain": domain,
            "tier": tier,
            "onboarded_date": kwargs.get("onboarded_date", ""),
            "technical_context": kwargs.get("technical_context", ""),
            "has_developer": kwargs.get("has_developer", False),
            "scan_schedule": _tier_to_schedule(tier),
            "last_scan_date": None,
            "next_scan_date": None,
        }

        self.store.write_json(profile, client_id, "profile.json")
        logger.bind(context={
            "client_id": client_id, "tier": tier, "domain": domain,
        }).info("profile_created")
        return profile

    def load_profile(self, client_id: str) -> dict | None:
        """Load a client profile, or None if not found."""
        return self.store.read_json(client_id, "profile.json")

    def update_profile(self, client_id: str, updates: dict) -> dict:
        """Partial update of a client profile. Returns updated profile."""
        profile = self.store.read_json(client_id, "profile.json")
        if profile is None:
            raise FileNotFoundError(f"No profile found for {client_id}")

        _IMMUTABLE = {"client_id", "domain", "onboarded_date"}
        for key in _IMMUTABLE:
            if key in updates:
                raise ValueError(f"Cannot update immutable field: {key}")

        if "tier" in updates and updates["tier"] not in _VALID_TIERS:
            raise ValueError(f"Invalid tier '{updates['tier']}'")

        profile.update(updates)

        # Keep scan_schedule in sync with tier
        if "tier" in updates:
            profile["scan_schedule"] = _tier_to_schedule(updates["tier"])

        self.store.write_json(profile, client_id, "profile.json")
        logger.bind(context={
            "client_id": client_id, "fields": list(updates.keys()),
        }).info("profile_updated")
        return profile


def _tier_to_schedule(tier: str) -> str:
    return {"watchman": "weekly", "sentinel": "daily", "guardian": "daily"}.get(tier, "weekly")
