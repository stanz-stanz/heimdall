---
name: wrap-up
description: "End-of-session wrap-up for the Heimdall project. Runs a compliance eval across Valdí routing, agent boundaries, CLAUDE.md integrity, document consistency, code hygiene, and Jira board sync — then logs decisions, flags issues, and prepares a handoff for the next session. Use this skill whenever the user says /wrap-up, asks to wrap up, wants a session summary, end-of-day review, compliance check, or wants to prepare continuity notes before closing out. Also trigger when the user asks to update the decision log, check project hygiene, or do a pre-commit review."
---

# End-of-Session Wrap-Up

End-of-session wrap-up. If a focus area is specified (e.g. `/wrap-up code hygiene`), scope the review to that area only. Otherwise, review all areas.

## Live context

Before starting the eval, gather live project state by running these commands:

1. `git status`
2. `git diff HEAD --stat`
3. `git log --oneline -5`
4. `grep -r "TODO\|FIXME" --include="*.py" --include="*.ts" --include="*.tsx" -l 2>/dev/null || echo "none found"`
5. **Jira board state** (read-only, via Atlassian MCP — `cloudId` `8b5ae1b8-c844-4ac5-8667-a62d08bd916a`, project `HEIM`). If the MCP is disconnected, skip with the note "MCP disconnected — Jira sync row defaults AMBER" and surface the reconnect ask in Step 5. If connected, run all three:
   - `project = HEIM AND sprint in openSprints() ORDER BY rank` — current sprint contents (key, status, story points, parent, customfield_10020).
   - `project = HEIM AND issuetype = Subtask AND status != Done AND parent in (project = HEIM AND status = Done AND sprint in openSprints())` — orphan Subtasks under Done parents (the pattern that blocks Complete-Sprint).
   - `project = HEIM AND labels in ("sprint-NN") AND sprint is EMPTY` (substitute the active sprint number) — tickets carrying the sprint label but missing the actual `customfield_10020` container.

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
| Jira board sync        | ?      | Active sprint container matches shipped work? No orphan Subtasks under Done parents? No `sprint-NN`-labelled tickets missing the `customfield_10020` container? |

Flag any **RED** area as **PRIORITY** before proceeding.

## Step 2 — Jira board reconciliation

If the Jira board sync row in Step 1 is AMBER or RED, drill into the discrepancy and produce a proposal. Common patterns and the canonical fix:

- **Orphan Subtasks under Done parents** (blocks `Complete Sprint` in the Jira UI). Propose: bulk-transition each Subtask → Done with a status comment naming the parent's commit hash. Per `feedback_jira_update_before_commit`, the comment + transition pair must land before any related code commit.
- **Tickets in the sprint container but still To Do at wrap-up time, with no commits referencing them** → flag as carry-over candidates for the next sprint. Do NOT auto-move; surface for Federico's call.
- **Tickets touched by commits this session but not transitioned in Jira** (smart-commit `HEIM-XX #close` was missing from the commit body) → propose transition to Done + status comment with the commit hash.
- **`sprint-NN` label set but `customfield_10020` null** — locked convention `feedback_jira_sprint_container_required` says container is the source of truth, label is JQL convenience. Propose `editJiraIssue` to set the container.
- **Historical Epics still in To Do when they describe completed work** (e.g. HEIM-5..20 in the current backfill) → propose bulk transition.
- **HEIM-3-style template-starter Bugs** (no SP, no description, no assignee) sitting in an active sprint → propose deletion (UI-only — Atlassian MCP does not expose delete).

If the MCP was disconnected during Step 0, list the queries Federico would run after reconnecting and skip to Step 3.

Do not act on any proposal yet — they land in Step 4 (checklist) for confirmation per `feedback_decision_authority`.

## Step 3 — Decision log

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

## Step 4 — Checklist

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

**Jira board**
- Orphan Subtasks to transition (key + parent + commit hash)
- Tickets needing manual Done transition (smart-commit was missing from the commit body)
- Container-vs-label mismatches to fix via `editJiraIssue`
- Historical Epics still in To Do
- Atlassian MCP disconnect (if applicable) + reconnect instruction

**Continuity**
- Open threads or unfinished tasks
- Suggested opening prompt for next session (one sentence, actionable)

## Step 5 — Confirm before acting

Do not make any edits yet. Present the checklist and ask:

> "Which items should I action now?"

Action only confirmed items. Start with RED items if any exist.
