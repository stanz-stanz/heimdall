"""Per-context router package for the operator console.

Stage A spec §6.1 + §6.5. The carve splits ``src/api/console.py`` into
six bounded-context modules (tenant, findings, onboarding, billing,
retention, liveops) plus the ``auth`` module. A seventh
``notifications`` context is reserved but NOT created in Stage A —
CT-change alerts, retention-failure alerts, and Message 0 magic-link
emails continue running from their current modules until the
post-V2 Notifications carve sprint.

Slice 3e ships the ``auth`` module (login / logout / whoami).
Subsequent slices land the remaining six. ``app.py`` includes each
router by name; there is no central registry.
"""

from src.api.routers.auth import router as auth_router

__all__ = ["auth_router"]
