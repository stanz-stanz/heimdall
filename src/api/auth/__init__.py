"""Operator-console authentication primitives (Stage A).

See ``docs/architecture/stage-a-implementation-spec.md`` §2.5 for the
module layout. Slices land in order: 2 (hashing), 3a (sessions), 3b
(audit), 3c (rate_limit), 3d (middleware). Wiring into
``src/api/app.py`` lands with slice 3e alongside the
login/logout/whoami router.
"""

from src.api.auth.middleware import SessionAuthMiddleware

__all__ = ["SessionAuthMiddleware"]
