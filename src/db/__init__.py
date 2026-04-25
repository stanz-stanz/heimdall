"""Client database connection factory and schema initialization."""

from src.db.connection import _now, init_db, open_readonly
from src.db.onboarding import (
    WATCHMAN_TRIAL_DAYS,
    InvalidSignupToken,
    activate_watchman_trial,
)

__all__ = [
    "_now",
    "init_db",
    "open_readonly",
    # Onboarding — signup → Watchman-trial activation
    "activate_watchman_trial",
    "InvalidSignupToken",
    "WATCHMAN_TRIAL_DAYS",
]
