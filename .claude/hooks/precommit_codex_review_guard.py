#!/usr/bin/env python3
"""PreToolUse hook — soft-block git commits without Codex review.

Per ``feedback_codex_before_commit`` (and Federico's directive
2026-04-25): any commit touching ``src/**/*.py`` or ``tests/**/*.py``
must be Codex-reviewed *before* the commit lands. After-the-fact
review is theatre — by the time the bug surfaces post-commit, the
bad code is in branch history and a fix is a separate cycle.

The hook does not validate that the review actually happened — that
is a self-attestation pattern (mirroring ``HEIMDALL_APPROVED=1`` for
prod pushes via ``.githooks/pre-push``). The friction itself is the
safety net: the commit goes through only after the operator
consciously types the bypass prefix.

Bypass:
    HEIMDALL_CODEX_REVIEWED=1 git commit -m "..."

Pure-docs / config commits (no Python diff) are not affected —
the hook exits silently.

Returns the standard PreToolUse ``permissionDecision: "ask"`` shape so
Claude Code surfaces the reason and the operator (or model) can
confirm. The hook never hard-blocks; it always offers the bypass.
"""

import json
import os
import re
import subprocess
import sys

GIT_COMMIT_RE = re.compile(r"\bgit\s+commit\b")
BYPASS_RE = re.compile(r"\bHEIMDALL_CODEX_REVIEWED=1\b")
TRACKED_PATH_PREFIXES = ("src/", "tests/")


def run(cmd, cwd):
    try:
        return subprocess.check_output(
            cmd, cwd=cwd, stderr=subprocess.DEVNULL, text=True, timeout=5
        ).strip()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return ""


def _staged_python_files(project_dir: str) -> list[str]:
    """Return Python files under src/ or tests/ in the staged or working diff.

    Prefers ``--cached`` (staged) so the list reflects what would actually
    land in the next commit. Falls back to the unstaged working-tree
    diff when nothing is staged — common during ``git commit -a`` flows.
    """
    staged = run(["git", "diff", "--cached", "--name-only"], project_dir)
    if not staged:
        staged = run(["git", "diff", "--name-only"], project_dir)

    return [
        f
        for f in staged.split("\n")
        if f.endswith(".py")
        and any(f.startswith(p) for p in TRACKED_PATH_PREFIXES)
    ]


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    if data.get("tool_name") != "Bash":
        sys.exit(0)

    command = data.get("tool_input", {}).get("command", "")
    if not GIT_COMMIT_RE.search(command):
        sys.exit(0)

    # Self-attestation bypass — Federico or the model has already run
    # Codex and is consciously asserting that. The pre-push prod hook
    # uses the same HEIMDALL_APPROVED=1 pattern.
    if BYPASS_RE.search(command):
        sys.exit(0)

    project_dir = os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or "."

    py_files = _staged_python_files(project_dir)
    if not py_files:
        # Pure-docs / config / .claude/hook commits — nothing to review.
        sys.exit(0)

    sample = ", ".join(py_files[:3])
    more = f" (+{len(py_files) - 3} more)" if len(py_files) > 3 else ""
    reason = (
        f"Commit touches {len(py_files)} Python file(s) under src/ or tests/: "
        f"{sample}{more}. Per feedback_codex_before_commit: run "
        f"`/codex:review` (or `node "
        f"~/.claude/plugins/cache/openai-codex/codex/1.0.4/scripts/"
        f"codex-companion.mjs review \"\"`) and read the result BEFORE "
        f"committing. If you have already reviewed and intentionally "
        f"want to bypass, prefix the command with "
        f"`HEIMDALL_CODEX_REVIEWED=1 git commit ...`."
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
