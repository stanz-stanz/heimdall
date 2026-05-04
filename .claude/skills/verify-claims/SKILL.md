---
name: verify-claims
description: "Source-grounded verification of factual assertions via Codex. Reduces Claude's failure mode of asserting unverified state ('X is on Pi5', 'N tests passing', 'PR #N is open', 'function Y does Z') as fact in synthesis prose. Three modes: pre-draft (gather verified facts before writing), post-draft (verify a draft you have already written), doc-pass (stale-ref / count / cross-section sweep on a long living doc). Invoke as /verify-claims <mode> [args]. Use whenever the response will assert state about Pi5, prod, test counts, PR/branch state, file existence, function behavior, schema state, merged-vs-open status, or counts — and on every TPMO / status / planning / decision-log / briefing turn."
---

# Verify Claims

Routes factual assertions through Codex for source-grounded confirmation before they land in user-facing prose. Backstops the inference-as-fact pattern that Claude exhibits under synthesis load.

## Modes

| Mode | When | Input | Output |
|---|---|---|---|
| `pre-draft` | BEFORE writing synthesis prose | List of claims about to assert + files to ground them in | Per-claim verification report |
| `post-draft` | AFTER writing synthesis prose, BEFORE sending | The draft prose + cited files | Per-claim verification report + revision guidance |
| `doc-pass` | On long living docs with cross-refs / counts | Target doc path | List of stale §X.Y refs, count mismatches, broken paths |

## Mandatory triggers

Run this skill (default mode: `pre-draft`) on every:

- TPMO / project-status / planning / "what's next" / kanban / backlog answer
- Decision-log entry draft
- `CLAUDE.md`, `docs/briefing.md`, `docs/repo-map.md`, spec or architecture-doc edit
- Cross-reference fixup pass on any long doc
- Any prose paragraph that asserts state about Pi5, prod, test counts, PR or branch state, file existence, function behavior, schema state, or counts of anything

If the answer is small enough to be a one-line fact derived from a single command output that just ran in this conversation, the skill is optional. If the answer synthesizes across multiple sources or relies on memory of files read earlier, the skill is mandatory.

## How to invoke (Claude-side procedure)

1. Identify the mode (`pre-draft`, `post-draft`, `doc-pass`).
2. Build a tight Codex prompt of the shape below.
3. Dispatch via `Agent(subagent_type="codex:codex-rescue", prompt=<the prompt>)`. Do not invoke as `Skill(codex:rescue)` — that re-enters the slash command and hangs.
4. Receive structured output. If Codex returns prose instead of the schema, re-prompt requesting the schema.
5. Apply the result. For `pre-draft`: draft on top of the verified facts. For `post-draft`: revise the draft per `rewrite_guidance`. For `doc-pass`: fix the flagged refs/counts.

### Prompt template

```
Read-only review. Do not edit any files.

Mode: <pre-draft | post-draft | doc-pass>

Claims (one per line, every state assertion — including ones I am confident in):
1. <claim>
2. <claim>
...

Files / paths to consult:
- <file:line range or whole file>
- <file>

For each claim, return JSON of this shape:

{
  "claims": [
    {
      "claim": "<exact assertion verbatim>",
      "status": "confirmed | refuted | unknown",
      "evidence": "<file:line, command output, or 'no source consulted'>",
      "rewrite_guidance": "<concrete revision text>"
    }
  ],
  "missing_coverage": ["<state assertion that should have been in the claim list but wasn't, if any>"]
}

Status semantics:
- confirmed = source reviewed, claim matches source verbatim
- refuted = source reviewed, claim contradicts source
- unknown = no source available, source ambiguous, or claim is about external state (Pi5, prod, network) that cannot be checked from the repo

Rewrite guidance must be concrete revision text, not advice. For unknown: provide the uncertainty-marked sentence.
For doc-pass mode: claims are stale §X.Y refs, count mismatches, broken paths, dangling sections.
```

## Required output schema

Codex MUST return JSON of this shape. If it returns prose, re-prompt:

```json
{
  "claims": [
    {
      "claim": "<exact assertion>",
      "status": "confirmed | refuted | unknown",
      "evidence": "<file:line OR command:output OR 'no source consulted'>",
      "rewrite_guidance": "<concrete revision text>"
    }
  ],
  "missing_coverage": ["<claim that should have been in the claim list but wasn't>"]
}
```

## Hard rule: `unknown` survives to final prose

If Codex returns `status: unknown` for any claim, the final user-facing prose MUST carry that uncertainty explicitly. Examples:

- ✅ "Pi5 may not be on the latest cutover (unverified — last decision-log entry says cutover pending)."
- ❌ "Pi5 is not on the latest cutover."
- ❌ Silently dropping the claim from the response.

Smoothing `unknown` into a confident sentence reintroduces the failure this skill exists to prevent. Re-state the claim with an inline uncertainty marker; do not omit and do not collapse to confidence.

## Hard rule: `missing_coverage` is non-negotiable

If Codex flags `missing_coverage` items — claims that should have been in the verification list but weren't — those claims are added to a fresh verification round before the response goes out. Do not write prose that includes any claim outside the verified set.

## Anti-patterns (do not do)

- Skipping the skill on a synthesis-class turn because "I am sure of these facts." Confidence is exactly the failure mode.
- Submitting an incomplete claim list. Include every state assertion the response will make, even ones that feel obvious.
- Treating `unknown` as a soft confirmation. It is not.
- Generalizing Codex's findings beyond the claims it ruled on (per `feedback_codex_finding_scope`).
- Writing prose that re-introduces an unverified claim that wasn't in the submitted list (the failure mode returns through the back door).
- Dispatching with `--write` for review work. This skill is read-only — pass that explicitly in the Codex prompt.

## Cost (per invocation)

| Mode | Claude tokens | Codex tokens |
|---|---|---|
| `pre-draft` | ~3k | ~10–15k |
| `post-draft` | ~2k | ~5–10k |
| `doc-pass` | ~3k | ~15–25k |

Coding-only sessions: zero cost (skill not invoked). Synthesis-heavy sessions: 2–5 invocations is typical. See `docs/decisions/log.md` 2026-05-04 entry for the projection rationale.

## Bites 2 and 3 (deferred)

Two complementary changes are deferred until this bite has session-evidence behind it:

- **Docs commit guard hook** — pre-commit soft-block on `CLAUDE.md`, `docs/briefing.md`, `docs/decisions/log.md`, `docs/repo-map.md` unless `HEIMDALL_DOC_REVIEWED=1` is set. Mirrors `precommit_codex_review_guard.py`.
- **Eval set / measurement baseline** — small corpus of past hallucinated assertions to measure whether this skill actually reduces the failure rate.

Per Codex review 2026-05-04: do not graduate either bite without session data.
