# Runbook — Pi5 production deploys

> **The rule.** Pi5 is production. Nothing reaches Pi5 unless it has
> been exercised on the local dev stack and `make dev-smoke` ran
> green. This runbook describes the exact mechanics.

For the developer side of the loop (OrbStack, venv, BotFather, daily
edit-run-test), see `docs/development.md`.

---

## Branch model

| Branch | Purpose | Who writes | Who reads |
|---|---|---|---|
| `main` | All dev-tested work lands here. Features via PR, bug fixes direct. | Federico (laptop) | CI, Pi5 (only indirectly via `prod`) |
| `prod` | What Pi5 deploys. Only ever fast-forwarded from `main` *after* `make dev-smoke` green. | Federico (laptop) | Pi5 |

`prod` is a deliberate gate, not a long-lived divergent branch. It
tracks `main` exactly but with a manual "I tested this locally" step
in between. Rollback is `git revert -m 1 <merge-sha>` on `prod`,
followed by another deploy.

---

## One-time operator setup

After cloning the repo on the laptop:

```bash
git config core.hooksPath .githooks
```

That activates `.githooks/pre-push`, which refuses pushes to `origin
prod` unless `HEIMDALL_APPROVED=1` is set in the environment. It is
the cheap belt before GitHub branch protection. The hook is
deliberately noisy — it prints exactly why it refused and points you
here.

---

## The deploy flow

For every change going to Pi5, run these steps in order. Do not skip.
Do not batch multiple changes and skip mid-sequence "because the
previous one tested fine".

### 1. Develop on `main` (or a feature branch merged to `main`)

Standard flow. Feature branches → PR → merge to `main`. Bug fixes can
commit direct to `main` per `feedback_git_branching_rule.md`.

### 2. Verify locally on the dev stack

```bash
make dev-smoke
```

This runs `dev-up` + `dev-seed` + `dev-pytest-integration` in sequence
against the local OrbStack dev stack with the 30-site fixture. It is
the only gate that matters. If `dev-smoke` is red, Pi5 stays untouched
— fix the dev stack first.

Red dev-smoke is not a reason to skip the gate. It is a reason to
fix the bug before it reaches Pi5.

### 3. Fast-forward `prod`

```bash
git checkout main && git pull --ff-only origin main
git branch -f prod main
```

`git branch -f prod main` moves `prod` to exactly where `main` is.
Because there is never any `prod`-only work, this is always a
fast-forward — the branch names just advance together.

### 4. Push `prod` with approval

```bash
HEIMDALL_APPROVED=1 git push origin prod
```

The pre-push hook refuses this unless `HEIMDALL_APPROVED=1` is set
*in the same shell command*. Do not export the variable persistently —
that defeats the purpose. Type it on the same line, every time.

### 5. Deploy on Pi5

```bash
ssh pi5
heimdall-deploy
```

The `heimdall-deploy` alias (in `scripts/pi5-aliases.sh`) does the
full sequence: `git fetch`, `git checkout prod`, `git pull origin
prod`, rebuild affected images, force-recreate containers with the
monitoring overlay.

### 6. Verify Pi5 healthy

Run `scripts/verify_ct_rebuild.sh` (or whichever verify script is
current). All checks must be green. If anything is red, jump to the
rollback section below.

---

## Rollback

If something goes wrong on Pi5 after a deploy:

### Option A — Revert the merge on `prod`

```bash
# On the laptop:
git checkout prod
git log --oneline -5                    # find the bad merge commit
git revert -m 1 <bad-merge-sha>         # creates a revert commit
HEIMDALL_APPROVED=1 git push origin prod

# On Pi5:
heimdall-deploy
```

This is the canonical path. The revert commit is a normal commit on
`prod`, the deploy picks it up like any other change, Pi5 rolls back.
`main` is untouched so other work in flight is not affected.

### Option B — Fast-forward `prod` to a known-good older commit

```bash
git checkout prod
git branch -f prod <last-good-sha>      # destructive reset of prod
HEIMDALL_APPROVED=1 git push --force-with-lease origin prod

# On Pi5:
heimdall-deploy
```

Only use this if the revert in Option A would conflict heavily or
produce an incoherent state. `--force-with-lease` prevents clobbering
if the remote has moved since you last fetched.

### Option C — Emergency stop

If Pi5 is actively serving corrupted data or hitting rate limits:

```bash
ssh pi5
heimdall-stop
```

Stops the stack entirely. No deploy, no data corruption continues.
Fix the code on `main`, test with `make dev-smoke`, redeploy.

---

## First-time `prod` branch creation

The first deploy after this runbook ships needs a one-shot setup:

```bash
git checkout main && git pull --ff-only
git branch prod main
git push origin prod
```

Then configure Pi5 to track `prod`:

```bash
ssh pi5
cd ~/heimdall
git fetch origin
git checkout -B prod origin/prod
```

After that, every future deploy follows the normal flow above.

---

## What is NOT allowed

- **Pushing to `prod` without `HEIMDALL_APPROVED=1`.** The hook
  blocks this; do not work around it by editing `.githooks/pre-push`
  or setting `core.hooksPath` to something else. If the hook
  misfires, fix the hook.
- **Force-pushing to `main`.** A shell hook
  (`.claude/hooks/main_branch_push_guard.py`) already soft-blocks
  this.
- **Deploying a change that failed `make dev-smoke`.** Ever. This
  includes "just this once because it's urgent".
- **Direct commits to `prod`.** `prod` is only moved by fast-forward
  from `main`, never by a commit authored on `prod` itself. The only
  exception is `git revert` for rollback.
- **Running `make dev-nuke` followed by a deploy** without an
  intervening `make dev-smoke`. Nuking the dev volumes wipes fixtures
  and test state — the next smoke run is the only safe deploy gate.

---

## Troubleshooting

**Pre-push hook didn't fire**
Check `git config core.hooksPath` returns `.githooks`. If it returns
nothing or the Git global hooks dir, re-run the one-time setup
command at the top of this file.

**`heimdall-deploy` pulls from `main` instead of `prod`**
You are running the pre-Phase-C aliases. `git pull` in
`scripts/pi5-aliases.sh` on Pi5 — check it, source the updated
file, try again.

**`git push origin prod` fails with "non-fast-forward"**
Someone else (or an earlier you) pushed to `prod` and you are behind.
Fetch first, then re-check that your `prod` is a fast-forward of
`origin/prod`. If it is not, something went wrong in the flow above —
stop and investigate before forcing anything.

**Pi5 deploy hangs on build**
First cutover builds all five service images locally on ARM. Budget
10–15 min. `docker compose ps` from another ssh session shows
progress. If a specific image fails, fall back to `docker compose
build --no-cache <service>` to rule out cache corruption.

**The dev smoke passed but Pi5 is red**
This is exactly the shipping-theater pattern the dev stack exists to
prevent. Stop, open an incident entry in `docs/decisions/log.md`,
capture the delta between dev and prod that caused the divergence,
and add a regression test to the dev-stack integration suite so it
fires on the next attempt.
