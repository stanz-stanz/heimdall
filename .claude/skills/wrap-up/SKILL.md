---
name: wrap-up
description: "End-of-session wrap-up for the Heimdall project. Runs a compliance eval across Valdí routing, agent boundaries, CLAUDE.md integrity, document consistency, and code hygiene — then logs decisions, flags issues, and prepares a handoff for the next session. Use this skill whenever the user says /wrap-up, asks to wrap up, wants a session summary, end-of-day review, compliance check, or wants to prepare continuity notes before closing out. Also trigger when the user asks to update the decision log, check project hygiene, or do a pre-commit review."
---

# End-of-Session Wrap-Up

End-of-session wrap-up. If a focus area is specified (e.g. `/wrap-up code hygiene`), scope the review to that area only. Otherwise, review all areas.

## Live context

Before starting the eval, gather live project state by running these commands:

1. `git status`
2. `git diff HEAD --stat`
3. `git log --oneline -5`
4. `grep -r "TODO\|FIXME" --include="*.py" --include="*.ts" --include="*.tsx" -l 2>/dev/null || echo "none found"`

Use the outputs as evidence for the ratings below.

## Step 1 — Eval

Rate each area **RED** / **AMBER** / **GREEN** with one line of reasoning. Base ratings on the live context gathered above.

| Area                   | Status | Reason |
|------------------------|--------|--------|
| Valdí compliance       | ?      | All new scan functions routed through Valdí gate? |
| Agent boundaries       | ?      | Did work stay within SKILL.md boundaries for each agent used? |
| CLAUDE.md integrity    | ?      | Does CLAUDE.md still accurately describe the project state? |
| Document consistency   | ?      | Are CLAUDE.md, SCANNING_RULES.md, and agent SKILL.md files in sync? |
| Code hygiene           | ?      | Debug flags, hardcoded values, or test credentials left in? |

Flag any **RED** area as **PRIORITY** before proceeding.

## Step 2 — Decision log

Always produce this step, regardless of scope. Format as a dated entry and append to `docs/decisions/log.md`. Create the file (and parent directories) if they do not exist.

```
## YYYY-MM-DD

**Decided**
- ...

**Rejected**
- ...

**Unresolved**
- ...
```

## Step 3 — Checklist

Report only items that need action. Skip GREEN items entirely. Do not fix anything yet.

**Documentation**
- Which parts of CLAUDE.md no longer reflect reality
- Where SCANNING_RULES.md and CLAUDE.md conflict
- Which agent SKILL.md files are stale
- Any project phase or status labels that are outdated

**Code hygiene**
- TODOs/FIXMEs introduced this session (file:line)
- New env vars missing from `.env.example`
- New packages not yet documented

**Continuity**
- Open threads or unfinished tasks
- Suggested opening prompt for next session (one sentence, actionable)

## Step 4 — Confirm before acting

Do not make any edits yet. Present the checklist and ask:

> "Which items should I action now?"

Action only confirmed items. Start with RED items if any exist.