"""Retention-execution cron: claim, dispatch, and apply offboarding actions.

This package is the executor side of D16's tiered retention policy. The
DB layer (``src/db/retention.py``) schedules jobs at churn; this package
picks them up via the scheduler daemon timer, claims them atomically,
dispatches to the right action handler, and writes the audit trail.

Modules:
    runner   — :func:`tick` is the single entry point the scheduler calls.
               Handles reap, claim, dispatch, backoff, alerting.
    actions  — :func:`anonymise_client`, :func:`purge_client`,
               :func:`purge_bookkeeping`. All pure DB + filesystem
               mutations; caller controls the transaction.

See ``docs/architecture/retention-cron-options.md`` for the design
proposal, ``docs/architecture/retention-cron-client-memory-review.md``
for the row-level semantics, and the 2026-04-24 retention-cron decision
memo for the locked calls.
"""
