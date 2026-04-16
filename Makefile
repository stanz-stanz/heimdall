# Heimdall — Mac dev workflow.
#
# Pi5 is PROD. Macbook is DEV. Nothing reaches Pi5 unless it has been
# exercised on the dev stack and a local dev-smoke has run green.
#
# Quick start:
#
#   make dev-up         # start the dev stack (first run pulls images)
#   make dev-seed       # populate data/dev/clients.db from the 30-site fixture
#   make dev-pytest     # run the fast unit-test suite
#   make dev-smoke      # full end-to-end: seed + pytest + integration
#
# See docs/development.md for the full workflow.

# --- Configuration ------------------------------------------------------

SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c

# A clean shell inherits COMPOSE_PROJECT_NAME from some operator setups; we
# do NOT want that. Every docker-compose invocation pins `-p` explicitly.
unexport COMPOSE_PROJECT_NAME

COMPOSE_PROD    := infra/compose/docker-compose.yml
COMPOSE_DEV     := infra/compose/docker-compose.dev.yml
COMPOSE_MON     := infra/compose/docker-compose.monitoring.yml
ENV_DEV         := infra/compose/.env.dev
ENV_DEV_EXAMPLE := infra/compose/.env.dev.example

# Git SHA is the immutable image tag. `-dirty` suffix fires if the working
# tree has uncommitted changes — stops accidental "latest"-builds of
# untracked code shipping silently to Pi5.
HEIMDALL_TAG := $(shell git rev-parse --short HEAD 2>/dev/null)$(shell git diff --quiet 2>/dev/null || echo -dirty)
export HEIMDALL_TAG

DC_DEV  := docker compose -p heimdall_dev --env-file $(ENV_DEV) \
	           -f $(COMPOSE_PROD) -f $(COMPOSE_DEV)
DC_PROD_RENDER := docker compose -p docker \
	           -f $(COMPOSE_PROD) -f $(COMPOSE_MON)

# --- Help ---------------------------------------------------------------

.PHONY: help
help: ## Show this help.
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-24s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# --- Dev stack lifecycle ------------------------------------------------

.PHONY: check-env
check-env: ## Error if infra/compose/.env.dev is missing.
	@if [ ! -f "$(ENV_DEV)" ]; then \
		echo "error: $(ENV_DEV) not found."; \
		echo "Copy $(ENV_DEV_EXAMPLE) to $(ENV_DEV) and fill in dev secrets."; \
		echo "See docs/development.md for the BotFather setup."; \
		exit 1; \
	fi

.PHONY: dev-build
dev-build: check-env ## Build dev stack images.
	$(DC_DEV) build

.PHONY: dev-up
dev-up: check-env ## Start the dev stack (detached, waits for healthchecks).
	$(DC_DEV) up -d --wait

.PHONY: dev-down
dev-down: ## Stop the dev stack (preserves named volumes).
	$(DC_DEV) down

.PHONY: dev-nuke
dev-nuke: ## Stop the dev stack AND delete dev named volumes.
	$(DC_DEV) down -v

.PHONY: dev-logs
dev-logs: ## Tail dev stack logs (ctrl-c to stop).
	$(DC_DEV) logs -f --tail=100

.PHONY: dev-ps
dev-ps: ## Show dev stack container status.
	$(DC_DEV) ps

.PHONY: dev-shell
dev-shell: ## Open a shell in the dev worker container.
	$(DC_DEV) exec worker bash

# --- Dev data -----------------------------------------------------------

.PHONY: dev-seed
dev-seed: ## Regenerate data/dev/clients.db from config/dev_dataset.json.
	python -m scripts.dev.seed_dev_db

.PHONY: dev-seed-check
dev-seed-check: ## Verify every dev-fixture brief exists on disk. No writes.
	python -m scripts.dev.seed_dev_db --check

# --- Tests --------------------------------------------------------------

.PHONY: dev-pytest
dev-pytest: ## Run the fast unit-test suite (no integration tests).
	python -m pytest -m "not integration" --no-cov

.PHONY: dev-pytest-integration
dev-pytest-integration: ## Run integration tests against the running dev stack.
	python -m pytest -m integration --no-cov

.PHONY: dev-smoke
dev-smoke: dev-up dev-seed dev-pytest-integration ## End-to-end dev verification.
	@echo "dev smoke: OK"

.PHONY: dev-ops-smoke
dev-ops-smoke: dev-up ## Exercise Pi5 operational scripts against the dev stack.
	@echo "==> backup.sh (dev stack, tmp backup dir)"
	@tmpdir=$$(mktemp -d); \
	    HEIMDALL_COMPOSE_PROJECT=heimdall_dev HEIMDALL_BACKUP_DIR=$$tmpdir \
	        bash scripts/backup.sh; \
	    rc=$$?; \
	    if [ $$rc -ne 0 ]; then \
	        echo "backup.sh failed (rc=$$rc). Log:"; \
	        cat $$tmpdir/backup.log; \
	        rm -rf $$tmpdir; \
	        exit 1; \
	    fi; \
	    if ! grep -q "OK: companies.db" $$tmpdir/backup.log; then \
	        echo "backup.sh: companies.db was not backed up. Log:"; \
	        cat $$tmpdir/backup.log; \
	        rm -rf $$tmpdir; \
	        exit 1; \
	    fi; \
	    if ! grep -q "OK: clients.db" $$tmpdir/backup.log; then \
	        echo "backup.sh: clients.db was not backed up (the PR-E regression). Log:"; \
	        cat $$tmpdir/backup.log; \
	        rm -rf $$tmpdir; \
	        exit 1; \
	    fi; \
	    rm -rf $$tmpdir
	@echo "dev ops smoke: OK"

# --- Compose lint / diff ------------------------------------------------

.PHONY: compose-lint
compose-lint: ## Validate both prod and dev compose renders parse cleanly.
	@echo "==> prod render"
	@$(DC_PROD_RENDER) config -q
	@echo "==> dev render"
	@$(DC_DEV) config -q
	@echo "==> both renders parse clean"

.PHONY: prod-render
prod-render: ## Print the full prod compose render to stdout (never deploys).
	@$(DC_PROD_RENDER) config

.PHONY: dev-render
dev-render: ## Print the full dev compose render to stdout.
	@$(DC_DEV) config
