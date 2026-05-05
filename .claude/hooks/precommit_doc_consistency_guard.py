#!/usr/bin/env python3
"""PreToolUse hook — soft-block git commits touching canonical living docs
without `/verify-claims doc-pass` first.

Per ``feedback_jira_update_before_commit`` and the 2026-05-04
decision-log entry on `/verify-claims` bite 2 (HEIM-27): any commit
touching one of the four canonical living docs must run a
`/verify-claims doc-pass` review BEFORE the commit lands. Without
the gate, stale-ref / count-drift bugs in the docs accumulate
silently.

The hook does NOT validate that the review actually happened — that
is a self-attestation pattern (mirroring
``precommit_codex_review_guard.py`` and ``HEIMDALL_APPROVED=1`` for
prod pushes). The friction itself is the safety net: the commit
goes through only after the operator consciously types the bypass
prefix.

Canonical living docs (exact filename match):
- ``CLAUDE.md``
- ``docs/briefing.md``
- ``docs/decisions/log.md``
- ``docs/repo-map.md``

Bypass:
    HEIMDALL_DOC_REVIEWED=1 git commit -m "..."

Commits that don't touch any canonical living doc are not affected —
the hook exits silently.

Returns the standard PreToolUse ``permissionDecision: "ask"`` shape so
Claude Code surfaces the reason and the operator (or model) can
confirm. The hook never hard-blocks; it always offers the bypass.
"""

import json
import os
import re
import shlex
import subprocess
import sys

GIT_COMMIT_RE = re.compile(r"\bgit\s+commit\b")
BYPASS_TOKEN = "HEIMDALL_DOC_REVIEWED=1"
TRACKED_PATHS = frozenset(
    {
        "CLAUDE.md",
        "docs/briefing.md",
        "docs/decisions/log.md",
        "docs/repo-map.md",
    }
)


def run(cmd, cwd):
    try:
        return subprocess.check_output(
            cmd, cwd=cwd, stderr=subprocess.DEVNULL, text=True, timeout=5
        ).strip()
    except (subprocess.SubprocessError, OSError):
        # Catch all subprocess-layer faults (CalledProcessError /
        # TimeoutExpired) AND OS-layer faults (FileNotFoundError /
        # PermissionError / BrokenPipeError / etc.). The hook's
        # contract is "exit silently on any error" — fail-safe is
        # more important than diagnostics here, since stderr is
        # suppressed anyway.
        return ""


def _has_bypass_prefix(command: str) -> bool:
    """True iff ``HEIMDALL_DOC_REVIEWED=1`` appears as an env-var prefix
    of the actual command, NOT as a substring inside a quoted commit
    message body.

    Tokenises with :func:`shlex.split` so quoted strings stay grouped;
    iterates leading tokens that look like ``NAME=value`` env-var
    assignments and matches the bypass exactly. The first non-env-var
    token (e.g. ``git``) ends the prefix region. A literal
    ``HEIMDALL_DOC_REVIEWED=1`` inside the commit message body lands
    inside one quoted token and is correctly ignored.
    """
    try:
        tokens = shlex.split(command)
    except ValueError:
        # Malformed quoting — be conservative, refuse to bypass.
        return False
    for tok in tokens:
        if "=" not in tok:
            return False
        name = tok.split("=", 1)[0]
        if not (name and name[0].isupper() and name.replace("_", "").isalnum()):
            return False
        if tok == BYPASS_TOKEN:
            return True
    return False


def _staged_canonical_docs(project_dir: str) -> list[str]:
    """Return canonical-living-doc paths in the staged or working diff.

    Prefers ``--cached`` (staged) so the list reflects what would
    actually land in the next commit. Falls back to the unstaged
    working-tree diff when nothing is staged — common during
    ``git commit -a`` flows. Exact filename match against
    :data:`TRACKED_PATHS`; no glob, no prefix.
    """
    staged = run(["git", "diff", "--cached", "--name-only"], project_dir)
    if not staged:
        staged = run(["git", "diff", "--name-only"], project_dir)

    return [f for f in staged.split("\n") if f in TRACKED_PATHS]


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    if not isinstance(data, dict):
        # Non-object JSON (null / list / scalar) — accept silently.
        sys.exit(0)

    if data.get("tool_name") != "Bash":
        sys.exit(0)

    command = data.get("tool_input", {}).get("command", "")
    if not GIT_COMMIT_RE.search(command):
        sys.exit(0)

    # Self-attestation bypass — Federico or the model has already
    # run /verify-claims doc-pass and is consciously asserting that.
    # Mirrors HEIMDALL_CODEX_REVIEWED=1 in
    # precommit_codex_review_guard.py, but with shlex-based detection
    # so the bypass token inside a quoted commit message body cannot
    # self-trigger the gate (realistic for a decision-log entry that
    # documents the bypass mechanism).
    if _has_bypass_prefix(command):
        sys.exit(0)

    project_dir = os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or "."

    docs = _staged_canonical_docs(project_dir)
    if not docs:
        # Commit doesn't touch any canonical living doc.
        sys.exit(0)

    sample = ", ".join(docs[:3])
    more = f" (+{len(docs) - 3} more)" if len(docs) > 3 else ""
    reason = (
        f"Commit touches {len(docs)} canonical living doc(s): "
        f"{sample}{more}. Run `/verify-claims doc-pass` first so "
        f"stale-ref / count-drift bugs in the canonical living docs "
        f"are caught at commit-time. If you have already reviewed and "
        f"intentionally want to bypass, prefix the command with "
        f"`HEIMDALL_DOC_REVIEWED=1 git commit ...`."
    )

    output = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": reason,
        }
    }
    print(json.dumps(output))
    sys.exit(0)


if __name__ == "__main__":
    main()
