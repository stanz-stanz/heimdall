"""Regression test: Valdí gate context across ThreadPoolExecutor.

Pinned bug: ``gated_execution()`` opens the gate-decision ContextVar on the
orchestrator thread but ``ThreadPoolExecutor`` workers start with an empty
Context (PEP 567 + concurrent.futures: each ``threading.Thread`` starts with
an empty Context — only asyncio's task factory copies). Before the fix
``runner.scan_domains`` submitted per-domain scans into a pool, and every
worker observed ``get_gate_execution_context() is None``, raising
``RuntimeError("...without Valdí gate context")``. The runner's
``as_completed`` loop swallowed the exception per-future and silently
returned ``{}`` — silent data loss in production, not a hard crash.

Contract under test (mirrors ``runner.scan_domains`` after the fix):
    decision = gate_or_raise(...)
    with ThreadPoolExecutor(...) as executor:
        future = executor.submit(<callable that opens its own gate scope
                                  and calls run_gated_scan(...)>)
        future.result()  # must not raise

The fix establishes the gate context **on the worker thread**, not on the
orchestrator. This file's tests are strategy-agnostic — they assert the
contract, not the mechanism.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from src.prospecting.scanners.registry import (
    _init_scan_type_map,
    iter_registered_scan_types,
)
from src.valdi import GateDecision, gated_execution, run_gated_scan
from src.valdi.gate import get_gate_execution_context

SSL_SCAN = "ssl_certificate_check"


def _make_decision() -> GateDecision:
    _init_scan_type_map()
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
        allowed_scan_types=iter_registered_scan_types(1),
    )


def test_gate_context_visible_on_orchestrator_thread() -> None:
    """Sanity baseline: synchronous reads on the same thread see the decision."""
    decision = _make_decision()
    with gated_execution(decision):
        ctx = get_gate_execution_context()
    assert ctx is not None
    assert ctx.decision.envelope_id == "env-test"


def _scan_in_worker(decision: GateDecision, domain: str):
    """Callable submitted to the pool — opens its own gate scope on the worker thread."""
    with gated_execution(decision):
        return run_gated_scan(SSL_SCAN, domain)


def test_run_gated_scan_inside_thread_pool_under_per_thread_gate() -> None:
    """Production path: a registered scan executed from a pool worker.

    Mirrors the post-fix runner pattern: the orchestrator submits work to
    ``ThreadPoolExecutor``; the worker callable opens its own
    ``gated_execution(decision)`` scope before calling ``run_gated_scan``.

    Before the fix, the runner relied on ContextVar inheritance from the
    orchestrator and crashed in every worker. After the fix, the gate
    scope is established on the execution thread itself, so this test
    passes regardless of the cross-thread propagation rules.
    """
    decision = _make_decision()
    ssl_stub = {
        "valid": True,
        "issuer": "Test CA",
        "expiry": "2099-01-01",
        "days_remaining": 9999,
        "tls_version": "TLSv1.3",
        "tls_cipher": "TLS_AES_256_GCM_SHA384",
        "tls_bits": 256,
    }
    # Patch at the source module — `_init_scan_type_map` re-imports each
    # call, so patches at the source path propagate to the registry's
    # dispatch.
    with patch(
        "src.prospecting.scanners.tls.check_ssl",
        return_value=ssl_stub,
    ) as mock_ssl:
        with ThreadPoolExecutor(max_workers=2) as executor:
            future = executor.submit(_scan_in_worker, decision, "example.dk")
            result = future.result()

    assert result == ssl_stub
    mock_ssl.assert_called_once_with("example.dk")


def test_orchestrator_gate_does_not_leak_into_pool_workers() -> None:
    """Document the cross-thread invariant: ContextVar does NOT propagate.

    A ``gated_execution`` opened on the orchestrator thread is invisible
    to ``ThreadPoolExecutor`` workers. This is the root cause of the
    original B1 bug. Every pool worker that needs a gate context must
    open its own.
    """
    decision = _make_decision()
    with gated_execution(decision):
        with ThreadPoolExecutor(max_workers=2) as executor:
            future = executor.submit(get_gate_execution_context)
            ctx_in_worker = future.result()
    assert ctx_in_worker is None, (
        "ContextVar leaked into pool worker — invariant changed. "
        "Review whether per-thread gated_execution() is still required."
    )
