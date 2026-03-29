"""Client Memory — persistent per-client state, delta detection, remediation tracking.

This module is the single writer to ``data/clients/{client_id}/`` (except
authorisation.json which Valdí owns). Other agents read from it; only
Client Memory writes.
"""

from .delta import DeltaDetector
from .history import ClientHistory
from .models import DeltaResult, FindingRecord, ScanEntry
from .profile import ClientProfile
from .remediation import RemediationTracker
from .storage import AtomicFileStore

__all__ = [
    "AtomicFileStore",
    "ClientHistory",
    "ClientProfile",
    "DeltaDetector",
    "DeltaResult",
    "FindingRecord",
    "RemediationTracker",
    "ScanEntry",
]
