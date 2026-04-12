#!/usr/bin/env python3
"""PreToolUse hook — block destructive git commands that can lose user work.

Uses shlex tokenization so dangerous patterns inside quoted arguments
(e.g. commit messages) don't false-match.
"""
import json
import shlex
import sys


def has_subseq(tokens: list, seq: list) -> bool:
    """True if `seq` appears as consecutive tokens in `tokens`."""
    n = len(seq)
    if n == 0 or n > len(tokens):
        return False
    return any(tokens[i : i + n] == seq for i in range(len(tokens) - n + 1))


def check(tokens: list) -> str | None:
    """Return a reason string if command is destructive, else None."""
    if has_subseq(tokens, ["git", "reset", "--hard"]):
        return "git reset --hard discards all uncommitted changes"
    if has_subseq(tokens, ["git", "checkout", "--"]):
        return "git checkout -- <path> discards uncommitted edits"
    if has_subseq(tokens, ["git", "checkout", "."]):
        return "git checkout . discards uncommitted edits"
    if has_subseq(tokens, ["git", "restore", "."]):
        return "git restore . discards uncommitted edits"
    if has_subseq(tokens, ["git", "restore", "--worktree"]):
        return "git restore --worktree discards uncommitted edits"
    if has_subseq(tokens, ["git", "branch", "-D"]):
        return "git branch -D force-deletes a branch"
    # git clean -f / -fd / -dfx etc
    for i, t in enumerate(tokens[:-1]):
        if t == "git" and tokens[i + 1] == "clean":
            flags = tokens[i + 2 : i + 3]
            if flags and "f" in flags[0]:
                return "git clean -f deletes untracked files permanently"
    # git push --force (but not --force-with-lease)
    for i, t in enumerate(tokens):
        if t == "git" and i + 1 < len(tokens) and tokens[i + 1] == "push":
            remainder = tokens[i + 2 :]
            if "--force" in remainder or any(
                r.startswith("--force=") for r in remainder
            ):
                return "use --force-with-lease, not --force"
    return None


def main():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    if data.get("tool_name") != "Bash":
        sys.exit(0)

    command = data.get("tool_input", {}).get("command", "")
    if not command:
        sys.exit(0)

    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        # Malformed shell — let it through rather than blocking by accident
        sys.exit(0)

    reason = check(tokens)
    if reason is None:
        sys.exit(0)

    output = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": (
                f"Destructive git command blocked: {reason}. "
                f"If you need this, ask Federico to run it manually."
            ),
        }
    }
    print(json.dumps(output))
    sys.exit(0)


if __name__ == "__main__":
    main()
