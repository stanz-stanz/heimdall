# Heimdall — Mac dev workflow

> **The rule.** Pi5 is production. Macbook is development. Nothing
> reaches Pi5 unless it has been exercised on the local dev stack and
> `make dev-smoke` ran green. No exceptions.

This document is the operator onboarding for the Mac dev loop. For the
deploy side (how changes travel from `main` → `prod` → Pi5), see
`docs/runbook-prod-deploy.md`.

---

## Prerequisites

### 1. Docker runtime (OrbStack)

Install OrbStack once:

```bash
brew install orbstack
open -a OrbStack
```

Click through the first-run dialog to grant the privileged helper. When
`which docker` returns `/usr/local/bin/docker` and `docker info` responds
without errors, OrbStack is ready.

Why OrbStack (not Docker Desktop): lower RAM/CPU overhead on arm64 Macs,
zero config, native Docker CLI.

### 2. Python virtualenv

The repo expects a venv at `.venv/` with the runtime + dev dependencies
installed.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install telethon pytest pytest-cov pytest-timeout pytest-asyncio
```

The dev dependency list lives in `pyproject.toml` under
`[dependency-groups].dev`. Treat `pyproject.toml` as the source of
truth; install manually for now (the project has no `[project]` section
so `pip install -e .` does not work).

### 3. Dev Telegram bot

The dev stack must never be able to talk to the prod bot. Create a
separate bot once:

1. Open Telegram, DM **@BotFather**.
2. `/newbot`, name it `heimdall_dev_bot` (or similar). Record the token
   that BotFather returns.
3. Send any message to the new bot from your own Telegram account. Then
   open `https://api.telegram.org/bot<TOKEN>/getUpdates` in a browser
   and extract the `chat.id` from the JSON response.
4. Store both the token and chat ID in your password manager.

If you ever see a dev-stack message land in a real client's Telegram,
the prod bot token leaked into the dev stack — stop everything and
rotate both tokens.

### 4. Pre-push hook (one-time)

Activate the pre-push hook that refuses stray pushes to the `prod`
branch:

```bash
git config core.hooksPath .githooks
```

The hook lives at `.githooks/pre-push`. It blocks `git push origin
prod` unless `HEIMDALL_APPROVED=1` is set in the same shell command,
and is a cheap belt before GitHub branch protection is wired up. See
`docs/runbook-prod-deploy.md` for the full deploy flow.

### 5. `infra/compose/.env.dev`

Copy the template and fill in the dev secrets:

```bash
cp infra/compose/.env.dev.example infra/compose/.env.dev
$EDITOR infra/compose/.env.dev
```

`infra/compose/.env.dev` is **gitignored**. It must contain at minimum:

| Key | Source |
|---|---|
| `TELEGRAM_BOT_TOKEN` | dev bot token from BotFather |
| `TELEGRAM_OPERATOR_CHAT_ID` | your own Telegram chat ID (step 3) |
| `CLAUDE_API_KEY` | a Claude API key (can reuse prod for now) |
| `CERTSPOTTER_API_KEY` | reuse prod key (daily quota far from limit) |
| `GRAYHATWARFARE_API_KEY` | reuse prod key |
| `SERPER_API_KEY` | reuse prod key |
| `CONSOLE_USER` | pick anything (e.g. `admin`) |
| `CONSOLE_PASSWORD` | pick a strong password |

All `make dev-*` targets refuse to run if this file is missing — by
design, because a dev stack with prod secrets is a prod stack.

### 6. Secrets auto-materialise on first `make dev-up`

Compose services no longer read credentials from env vars — they mount
them as files under `/run/secrets/`. The first `make dev-up` (or
`make dev-build`, or `make dev-secrets` directly) splits each secret
out of `.env.dev` into `infra/compose/secrets.dev/<name>` with `chmod
600`, backs up the original file as `.env.dev.pre-secrets`, and removes
the migrated lines from `.env.dev`.

You do not run this manually. It fires automatically, and re-runs
skip any file that already exists.

Files produced:
- `infra/compose/secrets.dev/telegram_bot_token`
- `infra/compose/secrets.dev/claude_api_key`
- `infra/compose/secrets.dev/console_password`
- `infra/compose/secrets.dev/certspotter_api_key`
- `infra/compose/secrets.dev/grayhatwarfare_api_key`

To **edit** a secret, edit the file in `secrets.dev/`. Don't put it back
in `.env.dev` — the migrator won't overwrite an existing secret file,
so the env value will be ignored. The directory is gitignored.

`SERPER_API_KEY`, `CONSOLE_USER`, `TELEGRAM_OPERATOR_CHAT_ID`,
`HEIMDALL_BACKUP_DIR`, etc. stay in `.env.dev` — they are configuration
or identifiers, not credentials, and the CLI enrichment tool that reads
`SERPER_API_KEY` runs outside any container.

---

## Daily loop

### First-time setup (one command after prerequisites)

```bash
make dev-up
make dev-seed
```

That boots the full stack (Redis, scheduler, worker, api, delivery)
under the `heimdall_dev` project, waits for every healthcheck, and
populates `data/dev/clients.db` with the 30-site fixture from
`config/dev_dataset.json`.

### Inner loop: fast unit tests

```bash
make dev-pytest          # ~15 seconds, 977+ tests, no Docker needed
```

This runs `pytest -m "not integration"` in your venv. It is the
default loop you run after every code edit. No Docker dependency.

### Integration loop: real Redis, real wire format

```bash
make dev-up              # if not already running
make dev-pytest-integration
```

Integration tests live in `tests/integration/` and are marked
`@pytest.mark.integration`. They run ONLY against a live dev stack
(Redis on `localhost:6379`). If the stack isn't up, the session-autouse
fixture in `tests/integration/conftest.py` **fails loud** with the
command to run. It never silently skips — silent skips hide exactly the
class of bug integration tests exist to catch.

### End-to-end smoke

```bash
make dev-smoke
```

Runs `dev-up` + `dev-seed` + `dev-pytest-integration` in sequence.
This is the gate you must run green before merging any branch to `main`
and ultimately to `prod`. If `dev-smoke` is red, Pi5 stays untouched.

### Compose lint

```bash
make compose-lint
```

Validates that both prod and dev compose renders parse without error.
Fast, deterministic. Run it before committing any compose file change.

### Stack lifecycle

| Command | What it does |
|---|---|
| `make dev-up` | start (detached, wait for health) |
| `make dev-down` | stop, preserve dev volumes |
| `make dev-nuke` | stop AND delete dev volumes (destructive — wipes dev DB state) |
| `make dev-logs` | tail all services |
| `make dev-ps` | list containers + health |
| `make dev-shell` | bash in the worker container |

### Regenerating the dev dataset

The dev DB is rebuilt from scratch each time you run `make dev-seed`.
If you want to verify the fixture without touching the DB:

```bash
make dev-seed-check
```

The 30-site list is committed to `config/dev_dataset.json` and is not
meant to change often. If you add or remove domains:

1. Edit `config/dev_dataset.json`.
2. Make sure a brief exists for each new domain under
   `data/output/briefs/`. `make dev-seed-check` will fail loud if any
   are missing.
3. Re-run `make dev-seed`.
4. Commit both the dataset change and any new briefs.

---

## Isolation guarantees

The dev stack cannot collide with prod. Every layer of isolation:

- **Docker project**: pinned to `heimdall_dev` via `-p heimdall_dev`.
  All containers, networks, and volumes are prefixed accordingly.
- **Host ports**: dev api is on `8001`, prod is on `8000`. Dev redis
  publishes `6379` to the host for integration tests; prod never does.
- **Secrets**: dev stack reads `infra/compose/.env.dev`, prod reads
  `infra/compose/.env`. Both are gitignored. Both require manual setup
  on their respective machines.
- **Database**: dev uses `data/dev/clients.db`; prod uses the Pi5
  named volume `docker_client-data`. Different files on different
  machines.
- **Telegram**: separate dev bot with its own token and chat ID
  allowlist. The dev bot cannot message a real client even by accident.
- **Scan targets**: the dev dataset is a curated 30-site list
  (`config/dev_dataset.json`). Real Layer 1 scans run the same code
  path as prod but against the same domains every time, so you can
  reproduce bugs.

---

## Troubleshooting

**`make dev-up` hangs at "waiting for healthcheck"**
Inspect the stuck service: `make dev-ps`, then `make dev-logs`. Most
common: a Dockerfile change broke the healthcheck, or a container is
crash-looping on a missing env var — check `infra/compose/.env.dev`
against the example file.

**`pytest -m integration` errors with "dev stack Redis unreachable"**
The autouse fixture is doing its job — the stack isn't running. Run
`make dev-up` first.

**`make dev-seed` reports missing briefs**
A domain in `config/dev_dataset.json` has no corresponding JSON file
in `data/output/briefs/`. Either add the brief or remove the domain
from the dataset.

**OrbStack says "Docker daemon not responding"**
Quit OrbStack from the menu bar and relaunch. First-run on some Macs
sometimes needs a second launch after the helper install.

**Port 6379 already in use**
Another Redis is running on the host. Common cause: a Homebrew Redis
service. Stop it: `brew services stop redis`.

**Tests pass locally but CI fails**
CI installs test tools inline in `.github/workflows/ci.yml` and does
not read `[dependency-groups].dev` from `pyproject.toml`. If you add a
new test dependency locally, also add it to the CI workflow's
`Install test tools` step. This is a known gap we have not yet unified.

---

## Do not

- Do not commit `infra/compose/.env.dev` or any file under `secrets/`.
- Do not commit `data/dev/clients.db` or its WAL/SHM siblings — they
  are rebuilt on demand from the JSON fixture.
- Do not point the dev stack at real client domains. The dev dataset
  is 30 specific domains, all chosen from the existing
  `data/output/briefs/` set. Scanning from both Pi5 and Mac against
  the same live targets doubles Valdí's consent-gate work for no
  benefit.
- Do not run `make dev-nuke` lightly — it wipes your local dev DB and
  all cached dev state.
- Do not deploy to Pi5 without running `make dev-smoke` first. If the
  smoke fails, fix the dev stack before shipping.
