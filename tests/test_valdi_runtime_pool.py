"""Regression test: Valdí gate context across ThreadPoolExecutor.

Reproduces the bug in this branch where ``gated_execution`` opens the
gate-decision ContextVar on the orchestrator thread but
``src/prospecting/scanners/runner.py`` dispatches per-domain scans through
a ``ThreadPoolExecutor`` whose worker threads do **not** inherit the
parent's contextvars (PEP 567 + concurrent.futures: each ``threading.Thread``
starts with an empty Context — only asyncio's task factory copies).

Contract under test (mirrors ``runner.scan_domains``):
    with gated_execution(decision):
        with ThreadPoolExecutor(...) as executor:
            future = executor.submit(<callable that calls a registered scan>)
            future.result()  # must not raise

Currently fails with::
    RuntimeError: Registered scan ssl_certificate_check executed
                  without Valdí gate context

The runner swallows that exception per-future and silently returns ``{}``
in production (``runner.py`` ``as_completed`` loop catches ``Exception``
and only logs), so the failure is **silent data loss**, not a crash.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from src.prospecting.scanners.registry import (
    _SCAN_TYPE_FUNCTIONS,
    _init_scan_type_map,
)
from src.prospecting.scanners.runner import SSL_SCAN, _run_scan_impl
from src.valdi import GateDecision, gated_execution
from src.valdi.gate import get_gate_execution_context


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
        allowed_scan_types=tuple(sorted(_SCAN_TYPE_FUNCTIONS.keys())),
    )


def test_gate_context_visible_on_orchestrator_thread() -> None:
    """Sanity baseline: synchronous reads on the same thread see the decision."""
    decision = _make_decision()
    with gated_execution(decision):
        ctx = get_gate_execution_context()
    assert ctx is not None
    assert ctx.decision.envelope_id == "env-test"


def test_run_scan_impl_inside_thread_pool_sees_gate_context() -> None:
    """Runner production path: ``_run_scan_impl`` invoked from a pool worker.

    Mirrors ``src/prospecting/scanners/runner.py:248–260`` where
    ``_scan_single_domain`` is submitted to ``ThreadPoolExecutor`` and
    immediately calls ``_run_scan_impl(SSL_SCAN, domain)``.

    With the ContextVar strategy as currently implemented, the worker
    thread does not inherit the orchestrator's gate context, so the
    gate guard at ``src/prospecting/scanners/runner.py:51`` raises
    ``RuntimeError("... executed without Valdí gate context")``.

    After the fix this test must pass — regardless of which strategy
    the fix uses (``copy_context().run`` on submit, per-thread
    ``gated_execution``, or explicit decision passthrough). The contract
    is: a registered scan submitted from the orchestrator inside an
    open ``gated_execution`` block must execute, not raise.
    """
    decision = _make_decision()

    # Mock the underlying scanner so the test fails for the gate-guard
    # reason, not network. If the gate context propagates, check_ssl is
    # called and the test passes; if it doesn't, the gate guard raises
    # before check_ssl is touched.
    ssl_stub = {
        "valid": True,
        "issuer": "Test CA",
        "expiry": "2099-01-01",
        "days_remaining": 9999,
        "tls_version": "TLSv1.3",
        "tls_cipher": "TLS_AES_256_GCM_SHA384",
        "tls_bits": 256,
    }
    with patch(
        "src.prospecting.scanners.runner.check_ssl",
        return_value=ssl_stub,
    ) as mock_ssl:
        with gated_execution(decision):
            with ThreadPoolExecutor(max_workers=2) as executor:
                future = executor.submit(_run_scan_impl, SSL_SCAN, "example.dk")
                # `.result()` re-raises the worker exception on this thread.
                result = future.result()

    assert result == ssl_stub
    mock_ssl.assert_called_once_with("example.dk")
