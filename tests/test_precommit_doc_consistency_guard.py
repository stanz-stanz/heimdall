"""HEIM-27 — `precommit_doc_consistency_guard.py` behavioural tests.

Eight tests covering the bite-2 contracts:

1. Commit touching a canonical living doc without bypass → soft-block
   (``permissionDecision: "ask"`` JSON on stdout, exit 0).
2. Commit with the ``HEIMDALL_DOC_REVIEWED=1`` bypass prefix → silent
   pass-through (no stdout, exit 0).
3. Commit not touching any canonical living doc → silent pass-through.
4. Non-Bash tool payload → silent pass-through.
5. Non-commit Bash command → silent pass-through.
6. Multi-doc commit → reason lists doc names + tail count.
7. Bypass token inside the commit message body MUST NOT self-bypass.
8. Non-object stdin JSON (null / list / scalar) → silent pass-through.

The hook is a standalone script invoked by Claude Code with a JSON
payload on stdin. We exercise it via ``subprocess.run`` against a
``tmp_path`` ``git`` working tree so the embedded
``git diff --cached --name-only`` call has something realistic to
read. No mocks of subprocess — the script runs end-to-end.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
HOOK_PATH = (
    REPO_ROOT / ".claude" / "hooks" / "precommit_doc_consistency_guard.py"
)


def _git(cmd: list[str], cwd: Path) -> None:
    """Run ``git`` in *cwd*, raise on failure."""
    subprocess.run(
        ["git", *cmd], cwd=cwd, check=True, capture_output=True, text=True
    )


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """Initialise a git repo + worktree ready to stage canonical docs.

    The hook calls ``git diff --cached --name-only`` from the project
    dir; we need a real repo with at least one commit so subsequent
    diffs produce predictable output. The project dir is also where
    ``CLAUDE.md`` and the ``docs/`` tree live in the real repo, so
    the staging tests mirror those filenames.
    """
    _git(["init", "-q"], tmp_path)
    _git(["config", "user.email", "test@example.com"], tmp_path)
    _git(["config", "user.name", "Test"], tmp_path)
    _git(["config", "commit.gpgsign", "false"], tmp_path)
    # Disable any inherited core.hooksPath — some hardened CI images
    # set this globally to enforce mandatory hooks; pointing to /dev/null
    # keeps the fixture self-contained.
    _git(["config", "core.hooksPath", "/dev/null"], tmp_path)
    # Empty initial commit so HEAD exists for staged-diff comparisons.
    _git(["commit", "--allow-empty", "-q", "-m", "init"], tmp_path)
    return tmp_path


def _invoke_hook(project_dir: Path, command: str) -> subprocess.CompletedProcess:
    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "cwd": str(project_dir),
    }
    return subprocess.run(
        [sys.executable, str(HOOK_PATH)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=10,
    )


def _stage_file(project_dir: Path, rel_path: str, content: str = "x") -> None:
    full = project_dir / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content, encoding="utf-8")
    _git(["add", rel_path], project_dir)


# ---------------------------------------------------------------------------
# Test 1 — canonical-doc commit without bypass MUST soft-block.
# ---------------------------------------------------------------------------


def test_blocks_commit_on_canonical_doc_without_bypass(project: Path) -> None:
    _stage_file(project, "docs/briefing.md", "edit\n")
    result = _invoke_hook(project, 'git commit -m "docs: tweak briefing"')

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip(), "expected JSON on stdout — got nothing"
    payload = json.loads(result.stdout)
    hook_out = payload["hookSpecificOutput"]
    assert hook_out["hookEventName"] == "PreToolUse"
    assert hook_out["permissionDecision"] == "ask"
    reason = hook_out["permissionDecisionReason"]
    assert "docs/briefing.md" in reason
    assert "HEIMDALL_DOC_REVIEWED=1" in reason
    assert "/verify-claims" in reason


# ---------------------------------------------------------------------------
# Test 2 — bypass prefix MUST allow the commit silently.
# ---------------------------------------------------------------------------


def test_bypass_envvar_allows_commit_silently(project: Path) -> None:
    _stage_file(project, "CLAUDE.md", "edit\n")
    result = _invoke_hook(
        project, 'HEIMDALL_DOC_REVIEWED=1 git commit -m "docs: lock"'
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "", (
        f"bypass must produce no stdout; got {result.stdout!r}"
    )


# ---------------------------------------------------------------------------
# Test 3 — non-canonical-doc commits MUST pass through silently.
# ---------------------------------------------------------------------------


def test_non_canonical_doc_commit_passes_through(project: Path) -> None:
    # README.md is markdown but NOT in TRACKED_PATHS; src/foo.py is
    # the codex-guard's surface, not this hook's. Both should pass.
    _stage_file(project, "README.md", "edit\n")
    _stage_file(project, "src/foo.py", "x = 1\n")
    result = _invoke_hook(project, 'git commit -m "chore: noise"')

    assert result.returncode == 0, result.stderr
    assert result.stdout == "", (
        f"non-canonical commit must produce no stdout; got {result.stdout!r}"
    )


# ---------------------------------------------------------------------------
# Test 4 — non-Bash tool calls and non-commit Bash calls MUST pass through.
# ---------------------------------------------------------------------------


def test_non_bash_tool_payload_passes_through(project: Path) -> None:
    """The hook is registered on Bash but PreToolUse fires per-tool;
    a non-Bash payload must early-exit silently rather than try to
    parse a missing ``command`` field."""
    payload = {
        "tool_name": "Edit",
        "tool_input": {"file_path": "/tmp/x", "old_string": "a", "new_string": "b"},
        "cwd": str(project),
    }
    result = subprocess.run(
        [sys.executable, str(HOOK_PATH)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""


def test_non_commit_bash_command_passes_through(project: Path) -> None:
    """``git status`` doesn't trigger the guard even though it touches
    canonical-doc paths in its output. The hook gates on the
    ``git commit`` regex, not the contents of the working tree."""
    _stage_file(project, "docs/decisions/log.md", "edit\n")
    result = _invoke_hook(project, "git status")
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""


# ---------------------------------------------------------------------------
# Test 5 — multiple canonical docs in one commit list all (up to 3) and
# tally the rest.
# ---------------------------------------------------------------------------


def test_multiple_canonical_docs_listed_in_reason(project: Path) -> None:
    _stage_file(project, "CLAUDE.md", "a\n")
    _stage_file(project, "docs/briefing.md", "b\n")
    _stage_file(project, "docs/decisions/log.md", "c\n")
    _stage_file(project, "docs/repo-map.md", "d\n")
    result = _invoke_hook(project, 'git commit -m "wip"')
    payload = json.loads(result.stdout)
    reason = payload["hookSpecificOutput"]["permissionDecisionReason"]
    # Pin both the count AND the lexically-ordered first three names so
    # a future regression that de-dupes or reorders is caught.
    assert reason.startswith(
        "Commit touches 4 canonical living doc(s): "
        "CLAUDE.md, docs/briefing.md, docs/decisions/log.md"
    )
    assert "(+1 more)" in reason
    assert "HEIMDALL_DOC_REVIEWED=1" in reason


# ---------------------------------------------------------------------------
# Test 7 — bypass token INSIDE the commit message body MUST NOT bypass.
# ---------------------------------------------------------------------------


def test_bypass_token_inside_message_body_does_not_self_bypass(
    project: Path,
) -> None:
    """Realistic case: a decision-log entry that documents the bypass
    mechanism will contain the literal string ``HEIMDALL_DOC_REVIEWED=1``
    in its commit message. The hook must NOT treat that as a bypass —
    only an env-var prefix on the command itself counts.
    """
    _stage_file(project, "docs/decisions/log.md", "edit\n")
    result = _invoke_hook(
        project,
        'git commit -m "docs: explain HEIMDALL_DOC_REVIEWED=1 bypass usage"',
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip(), (
        "bypass token inside message body must still soft-block; "
        f"got no JSON. stderr={result.stderr!r}"
    )
    payload = json.loads(result.stdout)
    assert payload["hookSpecificOutput"]["permissionDecision"] == "ask"


# ---------------------------------------------------------------------------
# Test 8 — non-object stdin JSON MUST NOT crash the hook.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("payload", ["null", "[]", "5", '"string"'])
def test_non_object_stdin_passes_through_silently(payload: str) -> None:
    """Defense-in-depth: ``json.load`` succeeds on non-object JSON
    but ``data.get(...)`` would crash. Hook must accept-and-exit
    rather than raise."""
    result = subprocess.run(
        [sys.executable, str(HOOK_PATH)],
        input=payload,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, (
        f"non-object JSON {payload!r} crashed hook with rc={result.returncode}: "
        f"stderr={result.stderr!r}"
    )
    assert result.stdout == ""
