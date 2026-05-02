"""Behavioral + structural guard for the Valdí single execution API.

The runtime invariant the codebase commits to:

    Every registered scan executes through ``valdi.run_gated_scan`` with
    a gate context established on the calling thread. Callers may not
    compose their own "lookup then call" path against the registry.

This test file enforces both halves:

  * **Behavioral** — register a sentinel scan type at the lowest layer of
    the registry (a private dispatch dict that's only meant to be touched
    in tests), then prove ``run_gated_scan`` (a) executes it under a
    matching gate decision, (b) refuses to execute it without a gate
    context, and (c) refuses to execute it when the gate decision does
    not authorise it.

  * **Structural** — assert ``runner`` and ``scan_job`` no longer expose
    a private ``_run_scan_impl`` symbol. Brittle to renaming, which is
    the point: re-introducing a local dispatch table under any name
    requires an explicit tradeoff visible in this guard.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from src.prospecting.scanners import registry
from src.valdi import (
    GateDecision,
    gated_execution,
    run_gated_scan,
)


SENTINEL_SCAN = "test_sentinel_scan"


@pytest.fixture
def sentinel_in_registry(monkeypatch):
    """Register a sentinel scan type for the duration of one test.

    The sentinel returns a recognisable marker so tests can prove the
    real registered function ran (not a mock injected at the call site).

    Implementation note: ``get_scan_function`` calls ``_init_scan_type_map``
    on every lookup, which clears + refills the level dicts from the
    canonical imports — wiping any injected sentinel. We monkeypatch
    ``_init_scan_type_map`` to a no-op for the duration of the test so the
    sentinel survives the lookup. The dispatch path under test is still
    real: ``run_gated_scan`` → ``get_scan_function`` → level dict.
    """
    registry._init_scan_type_map()

    sentinel_calls: list[tuple] = []

    def _sentinel(*args, **kwargs):
        sentinel_calls.append((args, kwargs))
        return {"sentinel": True, "args": args}

    registry._LEVEL0_SCAN_FUNCTIONS[SENTINEL_SCAN] = _sentinel
    monkeypatch.setattr(registry, "_init_scan_type_map", lambda: None)
    try:
        yield sentinel_calls
    finally:
        registry._LEVEL0_SCAN_FUNCTIONS.pop(SENTINEL_SCAN, None)


def _decision_allowing(scan_types: tuple[str, ...]) -> GateDecision:
    return GateDecision(
        decision_id=1,
        envelope_id="env-test",
        approval_token_ids=("tok",),
        scan_type="passive_domain_scan_orchestrator",
        requested_level=0,
        authorised_level=0,
        target_basis="prospect",
        decision="allowed",
        reason="test",
        forensic_path="",
        allowed_scan_types=scan_types,
    )


def test_run_gated_scan_executes_registered_sentinel_under_gate(
    sentinel_in_registry,
) -> None:
    """Positive path: sentinel registered + gate authorises → runs through registry."""
    decision = _decision_allowing((SENTINEL_SCAN,))
    with gated_execution(decision):
        result = run_gated_scan(SENTINEL_SCAN, "example.dk", port=443)

    assert result == {"sentinel": True, "args": ("example.dk",)}
    assert sentinel_in_registry == [(("example.dk",), {"port": 443})]


def test_run_gated_scan_raises_without_gate_context(
    sentinel_in_registry,
) -> None:
    """No ``gated_execution`` open on the calling thread → refuse to execute."""
    with pytest.raises(RuntimeError, match="without Valdi gate context"):
        run_gated_scan(SENTINEL_SCAN, "example.dk")
    assert sentinel_in_registry == []


def test_run_gated_scan_raises_when_scan_type_not_authorised(
    sentinel_in_registry,
) -> None:
    """Gate context open but the decision does not authorise the sentinel → refuse."""
    decision = _decision_allowing(("some_other_scan",))
    with gated_execution(decision):
        with pytest.raises(RuntimeError, match="not authorised by current Valdi"):
            run_gated_scan(SENTINEL_SCAN, "example.dk")
    assert sentinel_in_registry == []


def test_runner_module_no_longer_exposes_local_dispatch_shim() -> None:
    """Structural guard: ``runner._run_scan_impl`` must not return.

    Re-introducing a private dispatch in the runner is a regression of
    the architectural fix (see Valdí runtime hardening). If a future
    refactor needs a per-module shim, name it deliberately and update
    this guard with the rationale.
    """
    from src.prospecting.scanners import runner as runner_module

    assert not hasattr(runner_module, "_run_scan_impl"), (
        "src.prospecting.scanners.runner._run_scan_impl re-introduced. "
        "All registered-scan execution must funnel through "
        "valdi.run_gated_scan; do not compose lookup-then-call locally."
    )


def test_scan_job_module_no_longer_exposes_local_dispatch_shim() -> None:
    """Structural guard: ``scan_job._run_scan_impl`` must not return."""
    from src.worker import scan_job as scan_job_module

    assert not hasattr(scan_job_module, "_run_scan_impl"), (
        "src.worker.scan_job._run_scan_impl re-introduced. "
        "All registered-scan execution must funnel through "
        "valdi.run_gated_scan; do not compose lookup-then-call locally."
    )


def test_registry_lookup_race_free_under_concurrent_init() -> None:
    """Stress: many threads calling ``get_scan_function`` while
    ``_init_scan_type_map`` is also being called concurrently must not
    raise ``KeyError``.

    Without the registry lock, ``_init_scan_type_map``'s
    ``clear() + update()`` window lets one thread observe an empty
    dispatch dict — the runner's pool then drops domains intermittently
    with ``KeyError`` re-raised through ``as_completed``.
    """
    registry._init_scan_type_map()

    errors: list[Exception] = []

    def worker() -> None:
        try:
            for _ in range(200):
                fn = registry.get_scan_function("ssl_certificate_check")
                assert callable(fn)
                # Force a re-init concurrently — worst case for the race.
                registry._init_scan_type_map()
        except Exception as exc:
            errors.append(exc)

    with ThreadPoolExecutor(max_workers=20) as ex:
        futures = [ex.submit(worker) for _ in range(20)]
        for f in futures:
            f.result()

    assert not errors, f"Concurrent registry access raised: {errors[:3]}"
