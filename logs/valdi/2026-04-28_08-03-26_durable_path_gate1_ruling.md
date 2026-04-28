# Valdí Ruling — Compliance Asymmetry Between Prospecting Runner and Durable Worker

**Date:** 2026-04-28
**Subject:** Gate 1 (scan-type validation) parity for `src/worker/scan_job.py` (durable scanning path)
**Triggered by:** Federico, via architecture review concluding compliance asymmetry is the highest-priority issue in the scanning subsystem
**Authority:** SCANNING_RULES.md (project root, 2026-03-22 revision); `.claude/agents/valdi/SKILL.md`; project compliance model

---

## The Question, Reframed

Heimdall has two scanning-execution surfaces. The batch runner (`src/prospecting/scanners/runner.py:scan_domains`) invokes `_validate_approval_tokens()` on every call: it walks `.claude/agents/valdi/approvals.json`, recomputes `sha256(inspect.getsource(func))` for every Level 0 function (and Level 1 functions when `max_level >= 1`), validates `helper_hash` for entries that carry one, and fail-closes the entire batch on any mismatch. The runtime hash check is the mechanism by which Gate 1 is *enforced* at execution time — without it, a stored approval token is just a JSON entry, not a cryptographic binding to the code that was reviewed.

The durable worker path (`src/worker/scan_job.py:execute_scan_job`) has none of this. Robots.txt is honoured per-job (correct), Layer 2 tools are gated behind a numeric `job_level >= 1` check (insufficient — see sub-question 3), and `_validate_approval_tokens()` is never called. A worker can boot with `approvals.json` empty, malformed, or hash-mismatched against the actual scanner source, and it will happily execute scans. The token registry exists; the binding does not.

This is an inversion: the *prospecting* path (which scans third parties without consent and is therefore the higher legal-risk surface in volume terms) has stronger Gate 1 enforcement than the *Sentinel* path (which scans paying clients with written consent at Layer 1 and Layer 2). The legal risk profile is different — Sentinel work has consent and is therefore not a §263 exposure on the *target* axis — but the compliance-posture asymmetry is real, and the worker is the path that scales post-launch. Federico's proposal closes the gap by mirroring the runner's gate at process-boot time and persisting a validated envelope into per-job execution.

The question is whether boot-time hash validation + per-process envelope state + per-job policy check satisfies Gate 1 for the worker, and whether the proposed scope is the *minimum* sufficient remedy or whether refinements are required.

---

## Ruling: APPROVE WITH CONDITIONS

The proposed rule satisfies Gate 1 for the durable scanning path subject to the conditions below. The core architecture — boot-time hash validation, envelope persistence in process state, per-job policy check against that envelope — is correct. The runner's "validate per batch invocation" and the worker's "validate per process lifetime" are the correct lifecycle analogues; both fail-closed on mismatch, both reject execution rather than degrading silently, both reference `approvals.json` as the source of truth. The conceptual symmetry is sound.

What I require beyond the proposal:

### Conditions

**C1. Boot-time validation must fail-closed with a non-zero exit, not a logged warning.** The worker process MUST NOT consume from any job queue if `_validate_approval_tokens()` returns `None`. If the worker has multiple roles (e.g., scan execution + cache maintenance + retention dispatch), only the scan-execution capability is gated — but the gate must be hard. A worker that boots, fails validation, and continues running with scan execution disabled is acceptable only if "scan execution disabled" is observable to the operator via a Telegram alert or equivalent.

**C2. The envelope persisted in process memory must include the `function_hash` (and `helper_hash` where present) for each `scan_type_id`, not just the IDs.** The per-job check then has the option of cheap re-verification on a sampled basis if the operator later decides drift detection is needed (see sub-question 1). Storing only the ID set forecloses that option.

**C3. The per-job policy check must produce a forensic record equivalent to what the runner's `_write_pre_scan_check()` produces — but per-job, not per-batch.** This is the Gate 2 parity requirement. See sub-question 4 for the minimum schema.

**C4. The boot-time validation event must be logged to the Valdí forensic log directory** (`logs/valdi/YYYY-MM-DD_HH-MM-SS_worker_boot.md`) with the validated envelope, the worker process ID, the `max_level` it was authorised to handle, and the approval-token IDs in scope. This is a one-shot artifact per worker process; it makes "this worker booted under this compliance envelope" auditable. A worker boot that fails validation must also leave a forensic log entry — rejection logs are as important as approval logs (per `.claude/agents/valdi/SKILL.md`).

**C5. The `max_level` parameter at boot must be derived from worker configuration, not from per-job claims.** A Sentinel-capable worker is configured at deploy time to handle Level 0+1; a Watchman-only worker is configured to handle Level 0 only. The job's `level` field is an *input* the per-job check validates against the envelope — it is never permitted to *expand* the envelope. This is the runner's model (`max_level=0` is hardcoded for prospecting) translated into worker-config space.

---

## Sub-Question Rulings

### 1. Boot-time vs per-batch validation — is "once per process lifetime" sufficient?

**Yes, with one refinement.** Process restarts on deploy are the natural re-validation cadence. Periodic re-validation while the process runs (every N hours, on a Redis-published trigger) is *not* required by SCANNING_RULES.md and adds operational complexity for marginal compliance gain. The runner re-validates per batch because batches are externally triggered events with operator confirmation; the worker is a daemon, and "validate at the boundary" is the natural analogue.

**Refinement:** The deploy pipeline must restart workers when `approvals.json` changes. This is a deployment-discipline requirement, not a runtime requirement. The decision-log entry that records this ruling should call out: *if `scripts/valdi/regenerate_approvals.py --apply` runs in production, workers must be restarted before the next scan batch is dispatched*. If that's already implicit in the `heimdall-deploy` flow, document it; if not, the operator (Federico) decides whether to add it to `docs/runbook-prod-deploy.md` or to add a SIGHUP path. I do not require SIGHUP — see sub-question 2.

### 2. Envelope mutation between boot and job execution

**Acceptable until next restart.** No watch/SIGHUP required. The compliance model is "the worker executes scans under the envelope it validated at boot"; if `approvals.json` is regenerated mid-process, the in-memory envelope is now stale relative to disk, but it remains *sound* (it represents what was reviewed and approved — just an older approved set). The worst case is that a newly-approved scan type isn't yet executable in this worker, which is a feature-availability problem, not a compliance problem.

The asymmetric case — `approvals.json` is regenerated *removing* a scan type, and the worker continues executing it — is the only scenario where staleness is a compliance concern. This is also the scenario where SIGHUP would help. I'm not requiring it because: (a) approval revocation is rare and operator-initiated, (b) the operator regenerating approvals is the same operator with deploy authority, and (c) restart-on-regen is a simpler discipline than implementing+testing a watch path. If the operator later observes this scenario in practice, escalate to me and we'll add SIGHUP — for v1 of the durable-path gate, restart-on-regen is sufficient.

### 3. `max_level` parameterisation

**Validate at the configured level; let per-job consent be the gate within the envelope.** A Sentinel-capable worker boots with `max_level=1`, validates Level 0 + Level 1 scan-type hashes, and persists both sets in the envelope. The per-job check then enforces:

- `job.level` ≤ envelope's `max_level` (envelope ceiling)
- For `job.level == 1`: target has Sentinel tier *and* current written consent for the requested domain *and* the consent agreement covers Layer 2 — this is the Gate 2 logic that already lives in the consent validator, not new
- For `job.level == 0`: target's robots.txt allows automated access (already enforced) and no consent check required

The alternative — Watchman-only worker pool boots with `max_level=0`, Sentinel worker pool boots with `max_level=1` — is also acceptable and is in fact the cleaner deployment model. Either is compliant. The deployment topology is Federico's choice; from a Gate 1 perspective both topologies satisfy SCANNING_RULES.md.

**What is NOT acceptable:** a single worker that boots with `max_level=0` and then accepts Level 1 jobs by re-validating mid-process. That collapses boot-time validation into per-job validation and re-introduces the runtime overhead the proposal was designed to avoid. If a worker is going to handle Layer 2, it must validate Layer 2 hashes at boot.

### 4. Per-job policy check scope — Gate 2 parity

**Required per-job checks (minimum):**

1. `job.scan_type_id` (or the implied scan-type set for a multi-tool job) is in the envelope's approved set
2. `job.level` ≤ envelope's `max_level`
3. Robots.txt allows automated access for `job.domain` (already enforced — keep it)
4. For `job.level >= 1`: consent record exists for `job.domain`, is current (not expired), covers the requested domain in scope, and authorises Layer 2 — delegate to `src/consent/validator.py` if it already implements this; do not duplicate
5. For `job.client_id`: tier matches the requested level (Watchman cannot request Level 1 even with a stale consent record on file)
6. For synthetic targets (digital twins): the target is registered in `config/synthetic_targets.json`, and Gate 2 consent is bypassed per SCANNING_RULES.md "Synthetic Target Registry" section — but Gate 1 envelope check still applies (the twin exempts the *target* from consent, not the *tool* from validation)

**Per-job forensic artifact requirement:** every accepted job must produce a per-job forensic record. The runner writes one batch-level pre-scan check covering N domains; the worker writes N per-job records, one per execution. Schema (minimum):

```json
{
  "scan_request_id": "<job_id>",
  "client_id": "<job.client_id>",
  "target": "<job.domain>",
  "scan_type_ids": ["..."],
  "scan_level": 0,
  "approval_token_ids": ["..."],
  "envelope_max_level": 0,
  "envelope_validated_at": "<worker boot timestamp>",
  "checks": {
    "scan_types_in_envelope": true,
    "level_within_envelope": true,
    "robots_txt_allows": true,
    "consent_current": null,
    "consent_covers_layer": null,
    "synthetic_target": false
  },
  "result": "APPROVED|BLOCKED",
  "block_reason": "...",
  "checked_at": "<job-execution timestamp>"
}
```

This MAY be written to a per-job file (`data/compliance/{client_id}/pre-scan-{job_id}.json`) OR emitted as a structured loguru event with `event=valdi_pre_scan_check` and aggregated to a daily rollup file by a separate process. Federico's call on the storage strategy — what I require is that the artifact is *produced for every job* and is *queryable per job*. Loguru-only with no aggregation fails this.

**Operator-confirmation prompt:** NOT required for the worker path. The runner prompts because batches are operator-initiated against new prospects with no prior consent. Worker jobs are either (a) recurring Sentinel scans against consenting clients — consent is the prompt-equivalent, signed once at onboarding — or (b) trial Watchman scans against a domain the client supplied at signup, where the magic-link signup flow + subscription activation are the consent-equivalent. Per-job operator prompts would be operationally infeasible at scale and add no compliance value.

### 5. Scope confirmation — what this ruling does NOT cover

**Confirmed: Priority 3–5 are out of scope for this ruling.**

- **Priority 3 (bucket filter per-job load)** — performance/code-hygiene refactor; bucket filter outcomes don't change what's permitted under §263, only what gets executed. Out of jurisdiction.
- **Priority 4 (evidence-normalisation layer)** — data-shape consolidation; doesn't change scanning posture. Out of jurisdiction.
- **Priority 5 (scan-plan abstraction)** — architectural refactor; if it ever crosses into "the worker decides which scan types to run based on plan inputs that aren't in the envelope," it re-enters my jurisdiction. As described (envelope is still validated at boot; plan selects from within), it does not.

If any of #3–5 *does* end up changing how scan-type selection or level-determination happens at runtime, re-submit for a fresh ruling. As currently scoped per the architecture review, they don't.

---

## Forensic-Log Directives for Priority 2 Implementation

When the implementation of this ruling lands:

1. **Boot-time validation must produce `logs/valdi/{timestamp}_worker_boot.md`** with the envelope contents, validation result, and worker process metadata. This is a Gate 1 artifact, schema modelled on the existing scan-type validation log structure in `.claude/agents/valdi/SKILL.md`.

2. **Boot-time validation failures must produce `logs/valdi/{timestamp}_worker_boot_REJECTED.md`** with the specific mismatch (which `scan_type_id`, expected hash vs. computed hash, helper-hash mismatch if applicable). Name `python scripts/valdi/regenerate_approvals.py --apply` as the remediation, consistent with `_validate_helper_hash` log lines.

3. **Per-job pre-scan checks** as specified in sub-question 4 above. Schema and storage location operator's choice within the constraints stated.

4. **The decision-log entry recording this ruling** ("2026-04-28 — Scanning subsystem priority order (compliance asymmetry first)") should reference this ruling by its forensic-log filename once the ruling itself is logged. Convention: `logs/valdi/2026-04-28_<HH-MM-SS>_durable_path_gate1_ruling.md`. This file does not yet exist — Federico or the implementing agent creates it from the text of this ruling. I am not generating or modifying approval tokens as part of this ruling, per the request constraints.

5. **No approval token is issued by this ruling.** This is a compliance-architecture ruling, not a scan-type approval. The 14 entries in `.claude/agents/valdi/approvals.json` continue to be the source of truth for scan-type approvals; what changes is *where* and *when* those tokens are validated.

---

## Summary

Approve-with-conditions. The boot-time validation + envelope-persistence + per-job policy check architecture is the correct shape and satisfies Gate 1 for the durable scanning path. The five conditions (C1–C5) are required for the implementation to actually deliver Gate 1 parity rather than the appearance of it. The boundary between this ruling (Priority 2) and the downstream refactors (Priority 3–5) is correctly drawn — those don't cross my jurisdiction unless their final implementations change runtime scan-type selection, in which case re-submit.

The asymmetry, once closed, will leave the durable path with stronger end-to-end compliance posture than the prospecting path (boot-time validation + per-job pre-scan record vs. per-batch validation + per-batch pre-scan record). That's the correct end-state — the durable path is what scales post-launch, and Sentinel clients deserve the more granular audit trail their consent agreement implies.

---

**Relevant file paths:**

- `SCANNING_RULES.md`
- `.claude/agents/valdi/SKILL.md`
- `.claude/agents/valdi/approvals.json`
- `src/prospecting/scanners/registry.py` (current `_validate_approval_tokens` + `_validate_helper_hash`)
- `src/prospecting/scanners/runner.py` (current Gate 1 + Gate 2 batch enforcement — reference implementation)
- `src/prospecting/scanners/compliance.py` (current `_write_pre_scan_check` — schema reference for sub-question 4)
- `src/worker/scan_job.py` (target of Priority 2 work)
- `src/consent/validator.py` (per-job consent check — delegate, do not duplicate)
- `scripts/valdi/regenerate_approvals.py` (the remedy command referenced in failure logs)
- `config/synthetic_targets.json` (twin registry — Gate 2 bypass for synthetic targets)
- `docs/runbook-prod-deploy.md` (where the "restart workers after `approvals.json` regen" discipline is documented)
