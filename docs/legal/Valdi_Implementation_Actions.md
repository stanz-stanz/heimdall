# Valdí Implementation — Claude Code Action List

**Context:** Valdí is Heimdall's legal compliance agent. Its definition, forensic log format, approval token mechanism, and scan-type registry are specified in the Valdí specification document. This document lists the implementation actions required to make Valdí operational.

**Environment:** Claude Code. Pi infrastructure comes later.

---

## Actions to Request from Claude Code

### 1. Create the project file structure

Create the storage structure Valdí expects:

- **Forensic log store** — one entry per validation (approval or rejection)
- **Approval token store** — currently valid approval tokens (initialized empty)
- **Scan type registry** — registered and validated scan types (initialized empty)
- **Client authorisation store** — per-client authorisation files
- **Compliance audit trail** — per-target pre-scan check outputs
- **Compliance checklist** — operational checklist for legal compliance

---

### 2. Backfill: validate all existing scanning code

Before running any further scans, submit every existing scanning function to Valdí for Gate 1 review. This includes:

- Every function in the scanner module(s)
- Any utility functions that make outbound requests
- Any tool wrapper functions (httpx calls, webanalyze calls, etc.)

Each function gets its own forensic log entry. Functions that pass are registered in the scan type registry with approval tokens. Functions that fail are logged as rejections with full reasoning and suggested remediation.

No scans execute until this backfill is complete.

---

### 3. Modify the scanner workflow

The current flow is: Claude Code writes scanning code → code runs.

The new flow is:

1. A scanning function is written or modified
2. The function is submitted to Valdí for Gate 1 review
3. Valdí evaluates against the scanning rules at the declared authorisation level
4. If REJECTED — Valdí writes forensic log with full reasoning. The function must be rewritten. No execution.
5. If APPROVED — Valdí writes forensic log, generates approval token, updates the approval token store, registers the scan type in the scan type registry
6. Federico reviews the Valdí log entry and gives final go-ahead
7. Scanner executes, referencing the approval token

**Enforcement:** The scanning code must check the approval token store for a valid token matching its scan type before executing. If no valid token exists, it refuses to run and logs the failed attempt.

---

### 4. Implement the function hash check

Each approval token in the approval token store is linked to a function hash (SHA-256 of the function source). Before execution, the scanner must:

1. Compute the current hash of the function it is about to run
2. Compare it to the hash stored in the approval token
3. If they do not match → the token is invalid. Execution is blocked. A new Valdí review is required.

This ensures any modification to scanning code — regardless of how minor — invalidates the existing approval and requires fresh validation.

---

### 5. Add a pre-scan batch check (Gate 2)

Before any scan batch runs (even if the scan type is already approved), the scanner must call Valdí for a lightweight authorisation check:

1. Confirm the scan type's approval token is valid and hash matches
2. Look up the target domain's consent state (default: no consent on file if no file exists)
3. Confirm the scan type's required Layer does not exceed what the target's consent state permits
4. Log the check to the compliance audit trail

For a batch of targets using the same scan type at the same level, this is one check covering the batch — not one per target. The log entry notes the batch scope.

---

### 6. Create a rejection handler

When Valdí rejects a scan type:

1. Forensic log is written (rejection logs are never deleted or modified)
2. The scan type is not added to the scan type registry
3. No approval token is generated
4. Claude Code receives the violation report with specific line references, rule citations, and suggested remediation
5. After rewriting, the function must go through a fresh Gate 1 review — no shortcut

---

### 7. Wire up the operator notification

After each Valdí validation (Gate 1 or Gate 2), surface the result to Federico. In Claude Code this means printing the forensic log path and a summary. Federico's review is the final human gate before execution — Valdí reduces the review from "read every line of scanning code for legal compliance" to "read Valdí's reasoning and confirm."

---

## Build Order

| Order | Action | Why First |
|-------|--------|-----------|
| 1 | File structure | Everything else writes to these paths |
| 2 | Backfill existing code | Validates current codebase before anything else runs |
| 3 | Scanner workflow modification | Enforces review-before-execution going forward |
| 4 | Function hash check | Prevents unreviewed modifications to approved code |
| 5 | Pre-scan batch check (Gate 2) | Per-target authorisation for scan execution |
| 6 | Rejection handler | Handles the rewrite loop cleanly |
| 7 | Operator notification | Surfaces results for human review |

---

## What This Does NOT Cover (Yet)

- **Runtime request interception** — comes when you move to Pi infrastructure. For now, the control is pre-execution.
- **Network-level enforcement (iptables)** — same, infrastructure-level control for later.
- **Consent document management** — the authorisation registry structure is defined in the Valdí specification, but the workflow for collecting and storing signed consent documents is a separate task once pilot clients are onboarding.
