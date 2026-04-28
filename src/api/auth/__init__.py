"""Operator-console authentication primitives (Stage A).

See ``docs/architecture/stage-a-implementation-spec.md`` §2.5 for the
module layout. Slices land in order: 2 (hashing), 3a (sessions), 3b
(audit), 3c (rate_limit), 3d (middleware), 3e (routers/auth wiring +
disabled-operator audit hook).

Submodules are imported by their fully-qualified path
(``from src.api.auth.middleware import SessionAuthMiddleware``)
rather than via this ``__init__``. Eagerly re-exporting middleware
here would pull ``src.db.console_connection`` (which middleware
needs at import time) up through the package import, creating a
cycle when ``console_connection`` itself imports
``src.api.auth.hashing`` for the seed-operator-zero path. The
direct-import discipline keeps the load graph acyclic without
needing ``importlib``-style lazy hacks.
"""
