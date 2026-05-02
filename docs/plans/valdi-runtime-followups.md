# Valdí Runtime Hardening — Architect S1/S2/S3 Follow-ups

**Status:** Scaffolding — plan only, no implementation yet.
**Source:** Architect verdict on `feat/valdi-runtime-hardening` (PR #57). PR landed `994fd8d` on `main` 2026-05-02. Three "should-fix-soon" items were deferred out of PR scope; this doc collects them for a follow-up PR.

---

## S1 — Per-job DB I/O on the worker hot path

### Problem

`src/valdi/gate.py::gate_or_raise` calls `_persist_decision`, which calls `init_db(req.db_path)` on every gate decision (i.e. per scan job). `src/db/connection.py::init_db` runs the full DDL via `executescript`, calls `apply_pending_migrations`, and does `PRAGMA wal_checkpoint(TRUNCATE)` on every call.

In a busy worker BRPOP loop this is O(jobs) × DDL re-execution + WAL checkpoint. For one row insert per job, the overhead is significant. The WAL checkpoint also serialises against any concurrent reader (e.g. the API container mounting `client-data:/data/clients:ro`).

### Fix sketch

- Open one writer connection at worker boot (after `validate_and_persist_envelope`) and pass it into `gate_or_raise` via the `ScanRequest` (or via a worker-scoped accessor).
- `_persist_decision` accepts the connection rather than calling `init_db` itself.
- Alternative: add a lightweight `open_writer(db_path)` in `src/db/connection.py` that skips DDL + checkpoint when the file already exists and was recently initialised.

### Acceptance criteria

- `init_db` is called at most once per worker process per `db_path`.
- `gate_or_raise` writes a `valdi_gate_decisions` row without re-executing the DDL.
- New test asserts that running `gate_or_raise` ten times in a row triggers exactly one `executescript` call (mock).
- Existing `tests/test_valdi_runtime.py::test_gate_first_pass_emitted_once` still passes.

### Files likely touched

- `src/valdi/gate.py` — `_persist_decision` signature change.
- `src/valdi/models.py` — `ScanRequest` may gain a `conn` or `writer` attribute (optional, default None).
- `src/worker/main.py` — open one connection at boot, thread it into the BRPOP loop.
- `src/db/connection.py` — optional lightweight `open_writer` helper.
- `tests/test_valdi_runtime.py` — new test for one-shot init.

---

## S2 — Forensic-log volume in `logs/valdi/`

### Problem

`src/valdi/gate.py::_write_forensic_log` writes one markdown file per decision, including allowed decisions. `src/valdi/envelope.py::_write_boot_log` writes one boot envelope per worker start. No rotation. At 200 domains/run × weekly cron × N clients, the directory grows unbounded.

The structured row in `valdi_gate_decisions` already carries the same provenance info; the markdown is human-readable forensic backup but is pure overhead for the common allowed-Layer-1 path.

### Fix sketch

- Reserve markdown writes for: (a) blocked decisions, (b) first-pass conversion events (`valdi_gate2_first_pass`), (c) Level escalations (Layer 2 approvals), (d) worker boot envelopes.
- Allowed routine Layer 1 / Level 0 decisions emit only the DB row.
- Optional: time-based directory split (`logs/valdi/2026-05/...`) so even the markdown that does land doesn't grow into a single flat dir.
- Optional: `logrotate`-style cap on total markdown count (`max 1000 most-recent files`) wired into a cron or worker startup sweep.

### Acceptance criteria

- A 200-domain Layer-1 batch produces exactly one boot envelope markdown + one `valdi_gate2_first_pass` markdown per first-time prospect, not 200 individual decision markdowns.
- Blocked decisions still write a markdown.
- Existing `tests/test_valdi_runtime.py::test_gate_first_pass_emitted_once` still passes.
- New test asserts that allowed routine Level 0 decisions do NOT write a markdown.

### Files likely touched

- `src/valdi/gate.py` — `_write_forensic_log` becomes conditional on `decision != "allowed"` OR `target_basis != "consented_client"` OR equivalent.
- `tests/test_valdi_runtime.py` — new test asserting no markdown for routine allowed Level 0.

---

## S3 — Fail-loud invariant on `scan_history.gate_decision_id`

### Problem

`docs/architecture/client-db-schema.sql` declares `scan_history.gate_decision_id` as nullable for legacy compatibility. `src/db/worker_hook.py::save_scan_to_db` reads `job.get("gate_decision_id")` and `src/db/scans.py::create_scan_entry` accepts `gate_decision_id=None`. Nothing fails loudly when a future bug drops `job["gate_decision_id"] = decision.decision_id` in `src/worker/main.py`. The provenance link is silently optional; a regression would erode the audit trail without any test or runtime alarm.

### Fix sketch

- Add a fail-loud check in `save_scan_to_db` (or `create_scan_entry`) for worker-surface writes: if the surface is `worker` and `gate_decision_id is None`, raise `RuntimeError` with a clear message.
- Synthetic targets / non-Valdí writes (if any exist) are exempted via an explicit allow flag.
- Schema stays nullable for legacy rows; the runtime invariant is what guards new writes.

### Acceptance criteria

- A test that calls `save_scan_to_db` without `gate_decision_id` (worker surface) raises a clear `RuntimeError`.
- Existing `save_scan_to_db` callers (verified to pass `gate_decision_id`) continue to work.
- Legacy rows already in `scan_history` (with `gate_decision_id IS NULL`) are unaffected.

### Files likely touched

- `src/db/worker_hook.py` — the assert / raise.
- `tests/test_db_worker_hook.py` — new negative test.

---

## Sequencing for the follow-up PR

1. **S1 first** (highest impact, smallest test surface). Catches per-call DDL re-exec on the hot path.
2. **S3 second** (smallest code change, complements S1's audit-trail integrity goal).
3. **S2 last** (most operational, needs decisions about the conditional-write predicate).

Each step gets its own commit with Codex review per `feedback_codex_before_commit`. Single PR that bundles all three; if any one stalls, split into two PRs.

---

## Out of scope for this follow-up

- Change to the schema (`gate_decision_id NOT NULL`) — not done because it would block legacy rows. Runtime invariant is sufficient.
- Migration of existing forensic markdowns to a structured store — keep on disk as historical record; only changes the new-write rules.
- Architect's "approve-as-is" items from PR #57 (envelope dataclass, conversion-event idempotency, etc.) — those are stable and stay.
