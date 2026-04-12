#!/usr/bin/env python3
"""PreToolUse hook — block destructive git commands that can lose user work.

Fires on Bash. If the command matches a destructive pattern, denies the
tool call so the user must run it manually.
"""
import json
import re
import sys

DESTRUCTIVE_PATTERNS = [
    (r"\bgit\s+checkout\s+--\s", "git checkout -- <path> discards uncommitted edits"),
    (r"\bgit\s+checkout\s+\.\s*$", "git checkout . discards uncommitted edits"),
    (r"\bgit\s+checkout\s+\.\s*;", "git checkout . discards uncommitted edits"),
    (r"\bgit\s+restore\s+\.(\s|;|&|\||$)", "git restore . discards uncommitted edits"),
    (r"\bgit\s+restore\s+--worktree\b", "git restore --worktree discards uncommitted edits"),
    (r"\bgit\s+reset\s+--hard\b", "git reset --hard discards all uncommitted changes"),
    (r"\bgit\s+clean\s+-[a-z]*f", "git clean -f deletes untracked files permanently"),
    (r"\bgit\s+branch\s+-D\b", "git branch -D force-deletes a branch"),
    (r"\bgit\s+push\s+.*--force(?!-with-lease)", "use --force-with-lease, not --force"),
]


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

    for pattern, reason in DESTRUCTIVE_PATTERNS:
        if re.search(pattern, command):
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

    sys.exit(0)


if __name__ == "__main__":
    main()
