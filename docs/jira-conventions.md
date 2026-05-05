# Jira Conventions

Single-page reference for the `HEIM` Jira project at `project-heimdall.atlassian.net`.

---

## Project

| Field | Value |
|---|---|
| Site | `project-heimdall.atlassian.net` |
| Cloud ID | `8b5ae1b8-c844-4ac5-8667-a62d08bd916a` |
| Project key | `HEIM` |
| Project name | `Heimdall` |
| Template | Team-managed Scrum (Free plan) |
| Issue types | Epic, Story, Task, Bug, Subtask |
| Components | not used (Free plan limitation) — see `area-*` labels |
| Releases / Versions | not used — see `release-*` labels |
| Initiative | not used (Premium-only) — see `theme-*` labels |

---

## Hierarchy

```
Epic                  outcome slice, Title Case
  Story               user-value or product-facing deliverable
  Task                engineering chore, no user-visible outcome
  Bug                 defect work
    Subtask           implementation sub-step OR Test case
```

---

## Naming

| Level | Format | Example |
|---|---|---|
| Sprint | `Sprint NN — <Theme>` (zero-padded) | `Sprint 01 — Auth Plane Polish` |
| Epic | `<Outcome Noun-Phrase>`, Title Case, ≤40 chars | `Auth Plane Polish` |
| Story / Task | `<imperative verb> <concrete object>`, ≤80 chars, no period | `Add CONSOLE_READ-only role fixture and dispatch-denied test cell` |
| Subtask (impl) | Same as Story / Task | `Update tests/_console_auth_helpers.py with read-only fixture` |
| Subtask (test) | `Test: Verify <behavior> [when <condition>]`, present tense | `Test: Verify dispatch route returns 403 when role is CONSOLE_READ-only` |

---

## Story vs Task

- **Story** — the work changes something a user (operator, prospect, paying client, Federico-as-product-user) sees or interacts with.
- **Task** — engineering chore, no user-visible outcome. Hooks, tests, refactors, dep bumps, infra.

When in doubt, pick Story.

---

## Story-points scale

Fibonacci `1 / 2 / 3 / 5 / 8 / 13`. Anything `> 13` must be split before sprint commit.

---

## Labels

Free-text, auto-suggested. Apply one or more from each group as relevant:

| Group | Values | Purpose |
|---|---|---|
| Area | `area-api` `area-frontend` `area-worker` `area-scheduler` `area-signup` `area-valdi` `area-infra` `area-docs` | Maps to repo subsystem (replaces Components) |
| Theme | `theme-pilot-launch` `theme-auth-prod` `theme-onboarding` | Top-level outcome (replaces Initiative) |
| Release | `release-pilot-v1` `release-sentinel-v1` `release-watchman-v1` | Replaces Versions |
| Tier | `tier-watchman` `tier-sentinel` | Pricing tier the work touches |
| Blocked | `blocked-siri` `blocked-cvr` `blocked-wernblad` | External dependency holding the issue |

---

## Test cases

Tests live as Subtasks under their parent Story / Task / Bug. Summary prefix `Test:` makes them searchable.

```jql
parent = HEIM-12 AND issuetype = Subtask AND summary ~ "Test:"
project = HEIM AND issuetype = Subtask AND summary ~ "Test:" AND sprint in openSprints()
```

One test per acceptance criterion. Three or more on a Story is normal.

---

## Smart commits (GitHub for Jira)

Any commit message containing a ticket key auto-links the commit to the issue. Special directives:

```
feat(api): add CONSOLE_READ role fixture (HEIM-12)
HEIM-12 #close                      → transition to Done
HEIM-12 #time 30m                   → log 30 min worklog
HEIM-12 #comment shipped to dev     → add comment
```

A merged PR with a ticket key in title or commit auto-shows status on the issue page.

---

## JQL recipes

```jql
# My open work this sprint
assignee = currentUser() AND sprint in openSprints() AND statusCategory != Done

# All tests in current sprint
issuetype = Subtask AND summary ~ "Test:" AND sprint in openSprints()

# Blocked by SIRI
labels = blocked-siri AND statusCategory != Done

# Auth-plane work, ranked
labels = theme-auth-prod ORDER BY rank

# Closed in last 7 days
statusCategory = Done AND resolved >= -7d

# All work touching a subsystem
labels = area-valdi
```

---

## Sprint cadence

- 1-week sprints, Mon → Sun.
- Sprint numbering is sequential from `Sprint 01` (starts 2026-05-05).
- Historical work pre-Jira is preserved as `Done` Epics with no Sprint assignment — see backfill in `data/project-state.json`.

## Sprint container assignment (mandatory)

Every workable ticket must be assigned to a real **Sprint container** (`customfield_10020`), not merely labelled `sprint-NN`. The label is a JQL convenience; the container is the source of truth for the Board, burndown, and velocity. Working from the backlog with a label only is invisible to Sprint reporting.

- Subtasks ride their parent — `subtasks cannot be associated to a sprint` per the Jira agile API. Set the Sprint field on the parent Task/Story/Bug only.
- Sprint container ID discovery: query `project = HEIM AND sprint is not EMPTY` with `fields=["customfield_10020"]` to extract `id` from any issue already in a sprint. If none, drag one ticket into the sprint via the Backlog UI to seed the ID.
- "Done" tickets stay in their sprint — verify with `project = HEIM AND status = Done AND sprint = <ID>` after bulk-assign.

---

## Writing rules (carry over from `CLAUDE.md`)

- Imperative, terse Story / Task summaries. No period. No marketing voice.
- Description first paragraph = the why. Implementation detail goes in subtasks or comments.
- Pricing references in `kr.` not euros.
- No "Pi5" or "Raspberry Pi" in any description that could leak to a Jira-shared link — use "dedicated secure infrastructure".
- Codex-review gate still applies: any Story / Task touching `src/**/*.py` or `tests/**/*.py` must pass `/codex:review` before its commit (hook-enforced).

---

*Convention locked 2026-05-05. Convention changes go through `docs/decisions/log.md`.*
