"""Shared fixtures for integration tests.

Integration tests run against the live dev stack (`make dev-up`). They
must NEVER silently skip when the stack is down — a silent skip hides the
exact class of bug this directory exists to catch. Instead, a session-
scoped autouse fixture probes the required services and calls
``pytest.fail`` with a helpful message if any are unreachable.
"""

from __future__ import annotations

import os
import socket
from collections.abc import Iterator

import pytest

_DEFAULT_REDIS_HOST = "localhost"
_DEFAULT_REDIS_PORT = 6379
_PROBE_TIMEOUT_SECONDS = 1.0


def _tcp_reachable(host: str, port: int, timeout: float) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


@pytest.fixture(scope="session", autouse=True)
def dev_stack_reachable() -> Iterator[None]:
    """Fail loud if the dev stack isn't running before any integration test.

    Every integration test in this directory implicitly depends on this
    fixture (autouse + session scope). The probe runs once per session.
    """
    host = os.environ.get("HEIMDALL_DEV_REDIS_HOST", _DEFAULT_REDIS_HOST)
    port = int(os.environ.get("HEIMDALL_DEV_REDIS_PORT", _DEFAULT_REDIS_PORT))

    if not _tcp_reachable(host, port, _PROBE_TIMEOUT_SECONDS):
        pytest.fail(
            "dev stack Redis unreachable at "
            f"{host}:{port} — run `make dev-up` on the host first. "
            "Integration tests must run against the live dev stack.",
            pytrace=False,
        )
    yield


@pytest.fixture(scope="session")
def dev_redis_url() -> str:
    """Resolve the Redis URL the dev stack publishes on the host."""
    host = os.environ.get("HEIMDALL_DEV_REDIS_HOST", _DEFAULT_REDIS_HOST)
    port = int(os.environ.get("HEIMDALL_DEV_REDIS_PORT", _DEFAULT_REDIS_PORT))
    return f"redis://{host}:{port}/0"
