from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class EnvelopeScanType:
    function_hash: str
    helper_hash: str | None
    level: int
    approval_token: str


@dataclass(frozen=True)
class Envelope:
    envelope_id: str
    validated_at: str
    max_level: int
    instance_id: str
    pid: int
    code_version: str
    registry_hash: str
    approval_token_ids: tuple[str, ...]
    scan_types: dict[str, EnvelopeScanType]


@dataclass(frozen=True)
class ScanRequest:
    surface: str
    requested_level: int
    scan_type: str
    domain: str = ""
    domains: tuple[str, ...] = ()
    client_id: str | None = None
    job_id: str | None = None
    run_id: str | None = None
    confirmed: bool = True
    client_data_dir: str | None = None
    db_path: str | None = None
    envelope: Envelope | None = None
    robots_allowed: bool | None = None


@dataclass(frozen=True)
class GateDecision:
    decision_id: int | None
    envelope_id: str
    approval_token_ids: tuple[str, ...]
    scan_type: str
    requested_level: int
    authorised_level: int
    target_basis: str
    decision: str
    reason: str
    forensic_path: str
    allowed_scan_types: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class GateExecutionContext:
    decision: GateDecision
