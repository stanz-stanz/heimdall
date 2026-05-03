# CLAUDE.md

MANDATORY: Identify which agent in `.claude/agents/` owns this task and read its SKILL.md before proceeding.

---

## Workflow rules

- **Plan mode** for non-trivial tasks (3+ steps or architectural). If it goes sideways, stop and re-plan — don't push through.
- **Verification before done.** Run the tests. Prove it works. "Would a staff engineer approve this?"
- **Demand balanced sophistication.** For non-trivial changes, pause: "is there a simpler way?"
- **Codex review before the commit.** Any commit touching `src/**/*.py` or `tests/**/*.py` runs `/codex:review` first. Hook-enforced; bypass with `HEIMDALL_CODEX_REVIEWED=1` only after a real review.
- **Graph before Grep.** Try `code-review-graph` MCP tools (`semantic_search_nodes`, `query_graph`, `get_impact_radius`, `get_affected_flows`) before Grep / Glob / Read.
- Features → branch + PR. Bug fixes → direct to `main`. No monolithic commits.
- `git pull` before modifying code.
- **One git op per Bash call.** Never bundle `checkout`, `add`, `commit`, `push`, `branch`, `reset`, `rebase`, `merge`, `fetch`, or `cherry-pick` in a multi-statement Bash script. Each in its own call so the PreToolUse hook fires per command and any failure halts visibly. `set -e` does not propagate from piped commands without `set -o pipefail` — never rely on it as substitute for explicit error handling.

---

## Do not

- Write or run scanning code without a valid Valdí approval token.
- Scan / probe / automate requests to a domain whose `robots.txt` denies automation. Hard skip, all layers, no exceptions.
- Restate scanning rules outside `SCANNING_RULES.md` — reference the source.
- Duplicate business data (pricing, stats, policy figures) already in `docs/briefing.md`.
- Modify files in `.claude/agents/` without explicit instruction.
- Commit secrets, API keys, or tokens.
- Mention Raspberry Pi or specific hardware in client-facing text — use "dedicated secure infrastructure".
- Add or remove a scanning tool without updating the tool table in `docs/briefing.md` in the same commit.
- Make business / architecture / technical decisions. Present options with trade-offs; Federico decides.
- **Touch the prod branch in any way** — no checkout, no commit, no merge, no fast-forward, no reset, no fetch-into-prod, no `update-ref` on `refs/heads/prod`. Federico operates prod exclusively. If a workflow requires prod, present the manual steps for him to run and stop.

---

## Document precedence

1. `SCANNING_RULES.md` — authoritative on scanning.
2. `.claude/agents/valdi/SKILL.md` — enforces SCANNING_RULES.
3. `CLAUDE.md` — this file.
4. `docs/briefing.md` — business / strategy / architecture.

If this file conflicts with `SCANNING_RULES.md`, follow `SCANNING_RULES.md`.

---

## Layer terminology

- **Layer 1** — passive (browser-equivalent reads). Allowed by default.
- **Layer 2** — active probing (crafted requests, port scans). Requires Sentinel consent in scope.
- **Layer 3** — exploitation. Always blocked.

Full definition: `SCANNING_RULES.md`.

---

## Pointers

| File | Why |
|---|---|
| `docs/briefing.md` | Read first. Business + architecture + Danish policy. |
| `SCANNING_RULES.md` | Authoritative scanning rules. |
| `.claude/agents/valdi/SKILL.md` | Compliance enforcer — Gate 1 / Gate 2 procedure, approval tokens, forensic logs. |
| `docs/decisions/log.md` | What was decided when, and why. |
| `docs/repo-map.md` | Repo directory index — what each file / module does. |

For current sprint state, branch, and next-step: `git log --oneline`, `data/project-state.json`, and the latest entry in `docs/decisions/log.md`. **Don't put status in this file.**

---

## Hook contracts (`.claude/hooks/`)

Hooks defined in `.claude/settings.json`. Mechanical enforcement for rules that repeatedly failed as passive memory. They run in the harness, cannot be bypassed by model intent, and take precedence over anything in this file.

| Hook | Event | Behaviour |
|------|-------|-----------|
| `infra_danger_zone.py` | PreToolUse / `Edit\|Write` | Injects decision-log matches when editing infra files (`.gitignore`, `.env*`, compose, `Dockerfile*`, `infra/`, `.github/`, `pyproject.toml`, `requirements.txt`, `CLAUDE.md`, `SCANNING_RULES.md`, `.pre-commit-config.yaml`, `scripts/*.sh`). Non-blocking. |
| `destructive_git_guard.py` | PreToolUse / `Bash` | Blocks `git reset --hard`, `git checkout --`, `git restore .`, `git clean -f`, `git branch -D`, `git push --force`. Shlex-tokenized. |
| `secret_exposure_guard.py` | PreToolUse / `Bash` | Blocks `source .env`, `cat .env`, bare `env`/`printenv`, `echo $*_KEY/*_TOKEN/*_SECRET/*_PASSWORD`. |
| `inline_script_guard.py` | PreToolUse / `Bash` | Soft-blocks inline `python -c` / `node -e` > 150 chars or multi-line. |
| `main_branch_push_guard.py` | PreToolUse / `Bash` | Soft-blocks `git push origin main` when local commits include `src/**/*.py`. |
| `precommit_codex_review_guard.py` | PreToolUse / `Bash` | Soft-blocks `git commit` when staged diff includes `src/**/*.py` or `tests/**/*.py` and the command lacks `HEIMDALL_CODEX_REVIEWED=1`. |
| `prod_branch_commit_guard.py` | PreToolUse / `Bash` | Soft-blocks `git commit` when current branch is `prod`. Bypass `HEIMDALL_PROD_COMMIT=1` for deliberate hotfixes. Branching rule: features → branch + PR; bug fixes → main; prod only ever fast-forwards from main. |
| `ci_config_reminder.py` | PostToolUse / `Edit\|Write` | Reminds to push + `gh run watch` after editing CI/dep files. |
| `session_start_context.py` | SessionStart | Injects branch, status, recent commits, latest decision-log headline. |

**Permissions deny (project `settings.json`).** `permissions.deny` hard-blocks `Bash(git push:*)` and `Bash(gh push:*)` for the model. Federico runs all pushes himself in his own shell. Layered with `prod_branch_commit_guard.py` to make the 2026-05-02 prod-commit accident impossible to repeat.

**Limitation.** shlex doesn't read shell heredocs — `git commit -F - <<'EOF'` with dangerous text in the body can false-fire the destructive/secret guards. Workaround: write the message to a tempfile, `git commit -F /tmp/msg.txt`.

**Limitation 2 (`permissionDecision: "ask"` is silenced by `skipAutoPermissionPrompt: true`).** The Claude Code harness silently auto-approves `permissionDecision: "ask"` when `skipAutoPermissionPrompt: true` is set in `~/.claude/settings.json` (Federico's setup). Use `"deny"` for any hook that must actually block — `"ask"` becomes a no-op and the hook fires invisibly with no consequence. Audited 2026-05-03 after `prod_branch_commit_guard.py` was bypassed this way and recreated the 2026-05-02 prod-commit accident; the guard is now `deny` mode. The other three `ask`-mode hooks (`inline_script_guard.py`, `main_branch_push_guard.py`, `precommit_codex_review_guard.py`) remain bypassable by this user setting.

**Git-level hook (`infra/git-hooks/pre-commit`).** Second-layer defence at the git layer: hard-blocks `git commit` on the prod branch regardless of any Claude Code harness config (immune to `skipAutoPermissionPrompt`, multi-statement Bash, `set -e` without `pipefail`, etc.). Bypass with `HEIMDALL_PROD_COMMIT=1`. Per-clone install (one-time after clone): `git config core.hooksPath infra/git-hooks`.

**When a hook misfires:** the hook is right (reconsider) or the hook has a bug (fix the script + commit the fix). Never phrase around it.

---

## Content & copywriting

- Pricing in **kr.** (Danish kroner), not euros.
- Recurring example: **"restaurant with online booking system"** — not "bakery owner".
- No phrases like "stated honestly", "to be honest", "full transparency" — confidence is implicit.
- Citations: numbered superscripts → References section at end (not inline "Source: …").
- Scanning tool references include the GitHub repo link.
- Policy data, statistics, pricing — pull from `docs/briefing.md`, not memory.
- Default user-facing copy to English. Danish is a per-client override (`clients.preferred_language='da'`), never the fallback. For unknown-language fallback paths (e.g. bare `/start` with no client row), reply in EN.

---

## Operational facts

- **Pi5 prod admin:** user `stan_stan` (underscore, NOT hyphen). LAN IP `192.168.87.200`. SSH as `stan_stan@192.168.87.200`. The hyphenated form fails with `Permission denied (publickey)` and looks like a key problem when it isn't.
