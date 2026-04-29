# Repo Invariants

This file is intentionally narrow. It documents the small set of repository
facts that repeatedly matter for CI, Docker image assembly, and deploy safety.

## Canonical Checks

- Fast Python tests: `make dev-pytest`
- Frontend tests: `make frontend-test` and `make signup-test`
- Dev integration smoke: `make dev-smoke`
- Compose render validation: `make compose-lint`
- Local Docker image smoke, one service: `make image-smoke SERVICE=api`
- Local Docker image smoke, all services: `make image-smoke-all`

## Image Build Invariants

- The published service matrix is `api`, `delivery`, `scheduler`, `worker`, and `twin`.
- Docker build context is the repo root, with per-service Dockerfiles in `infra/compose/`.
- PR-time Docker smoke coverage should target `linux/amd64` for speed. Main publish remains `linux/arm64`.
- The root `.dockerignore` is part of the runtime contract. Regressions often come from broad excludes plus narrow allowlist exceptions.

## Files Intentionally Copied Into Images

- Shared Python dependency input: `requirements.txt`
- Shared app code: `src/`
- Shared config: `config/`
- Runtime schemas: `docs/architecture/client-db-schema.sql`, `docs/architecture/console-db-schema.sql`
- Delivery runtime scripts: `scripts/`
- Worker runtime assets: `tools/`, `scripts/`, `.claude/agents/`
- Twin runtime assets: `tools/`

## Path Filter Guidance

Changes in these areas can change Docker build success and should normally
exercise Docker smoke CI:

- `infra/compose/**`
- `.dockerignore`
- `requirements.txt`
- `src/**`
- `config/**`
- `scripts/**`
- `tools/**`
- `.claude/agents/**`
- `docs/architecture/client-db-schema.sql`
- `docs/architecture/console-db-schema.sql`

## Drift Rules

- If a Dockerfile adds a new `COPY` input, update the Docker smoke path filter and this document.
- If `.dockerignore` changes, run `make image-smoke-all` before merge.
- If a workflow changes image matrix membership, keep local smoke helpers aligned.
