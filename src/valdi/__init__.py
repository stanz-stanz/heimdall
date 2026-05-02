"""Valdi runtime authorization package."""

from .envelope import get_current_envelope, validate_and_persist_envelope
from .gate import (
    GateDeniedError,
    gate_or_raise,
    gated_execution,
    get_gate_execution_context,
    run_gated_scan,
)
from .models import Envelope, GateDecision, ScanRequest

__all__ = [
    "Envelope",
    "GateDecision",
    "GateDeniedError",
    "ScanRequest",
    "gate_or_raise",
    "gated_execution",
    "get_current_envelope",
    "get_gate_execution_context",
    "run_gated_scan",
    "validate_and_persist_envelope",
]
