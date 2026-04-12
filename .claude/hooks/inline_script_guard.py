#!/usr/bin/env python3
"""PreToolUse hook — soft-block large inline python/node scripts.

Trivial one-liners (version checks, short prints) pass through. Anything
longer than 150 chars or containing a newline triggers an 'ask' decision —
the user approves explicitly or writes a proper script file instead.
"""
import json
import re
import sys

# Captures 'python -c', 'python3 -c', 'node -e' with single or double quotes
INLINE_SINGLE = re.compile(r"\b(python3?|node)\s+-[ce]\s+'([^']*)'", re.DOTALL)
INLINE_DOUBLE = re.compile(r'\b(python3?|node)\s+-[ce]\s+"([^"]*)"', re.DOTALL)

THRESHOLD_CHARS = 150


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

    match = INLINE_SINGLE.search(command) or INLINE_DOUBLE.search(command)
    if not match:
        sys.exit(0)

    script_content = match.group(2)
    if len(script_content) <= THRESHOLD_CHARS and "\n" not in script_content:
        sys.exit(0)

    output = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": (
                f"Inline script is {len(script_content)} chars. "
                f"Per feedback_no_inline_scripts_ever, anything beyond a trivial "
                f"one-liner belongs in a test file or script. Approve only if this "
                f"is genuinely one-off and won't be needed again."
            ),
        }
    }
    print(json.dumps(output))
    sys.exit(0)


if __name__ == "__main__":
    main()
