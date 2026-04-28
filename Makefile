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
SECRETS_DEV     := infra/compose/secrets.dev

# Git SHA is the immutable image tag. `-dirty` suffix fires if the working
# tree has uncommitted changes — stops accidental "latest"-builds of
# untracked code shipping silently to Pi5.
HEIMDALL_TAG := $(shell git rev-parse --short HEAD 2>/dev/null)$(shell git diff --quiet 2>/dev/null || echo -dirty)
export HEIMDALL_TAG

# env -u on both DC_DEV and DC_PROD_RENDER strips the four *_HOST_DIR vars
# from the docker compose process environment so neither inherits them from
# an interactive shell that has them exported. DC_DEV then re-populates them
# from --env-file infra/compose/.env.dev (Compose env-file precedence kicks in
# only when the var is unset), guaranteeing dev binds always come from the
# committed dev fixture path. DC_PROD_RENDER lets the ${VAR:-default}
# fallbacks in docker-compose.yml take over (no env-file).
DC_DEV  := env -u INPUT_HOST_DIR -u ENRICHED_HOST_DIR \
	           -u RESULTS_HOST_DIR -u BRIEFS_HOST_DIR \
	           docker compose -p heimdall_dev --env-file $(ENV_DEV) \
	           -f $(COMPOSE_PROD) -f $(COMPOSE_DEV)
DC_PROD_RENDER := env -u INPUT_HOST_DIR -u ENRICHED_HOST_DIR \
	           -u RESULTS_HOST_DIR -u BRIEFS_HOST_DIR \
	           docker compose -p docker \
	           -f $(COMPOSE_PROD) -f $(COMPOSE_MON)

# --- Help ---------------------------------------------------------------

.PHONY: help
help: ## Show this help.
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-24s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# --- Dev stack lifecycle ------------------------------------------------

.PHONY: check-env
check-env: ## Error if infra/compose/.env.dev is missing or lacks required overrides.
	@if [ ! -f "$(ENV_DEV)" ]; then \
		echo "error: $(ENV_DEV) not found."; \
		echo "Copy $(ENV_DEV_EXAMPLE) to $(ENV_DEV) and fill in dev secrets."; \
		echo "See docs/development.md for the BotFather setup."; \
		exit 1; \
	fi
	@missing=""; \
	for var in INPUT_HOST_DIR ENRICHED_HOST_DIR RESULTS_HOST_DIR BRIEFS_HOST_DIR; do \
		line=$$(grep -E "^[[:space:]]*$$var[[:space:]]*=" $(ENV_DEV) | tail -1); \
		if [ -z "$$line" ]; then missing="$$missing $$var"; continue; fi; \
		val=$${line#*=}; \
		val=$$(printf '%s' "$$val" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$$//'); \
		val=$$(printf '%s' "$$val" | sed -e 's/^"\(.*\)"$$/\1/' -e "s/^'\(.*\)'$$/\1/"); \
		case "$$val" in ""|'#'*) missing="$$missing $$var" ;; esac; \
	done; \
	if [ -n "$$missing" ]; then \
		echo "error: $(ENV_DEV) is missing or has empty values for required dev/prod isolation overrides:$$missing"; \
		echo ""; \
		echo "Compose expands \$${VAR:-default} to the PROD default when VAR is empty,"; \
		echo "so any of these forms still leak prod paths into DEV:"; \
		echo "  BRIEFS_HOST_DIR="; \
		echo "  BRIEFS_HOST_DIR=\"\""; \
		echo "  BRIEFS_HOST_DIR=''"; \
		echo "  BRIEFS_HOST_DIR= # comment"; \
		echo "Copy the '--- Dev/prod data isolation ---' block from $(ENV_DEV_EXAMPLE)"; \
		echo "into $(ENV_DEV) and re-run."; \
		exit 1; \
	fi

.PHONY: dev-secrets
dev-secrets: check-env ## Materialise $(SECRETS_DEV)/* from .env.dev (idempotent).
	@bash scripts/migrate_env_to_secrets.sh --env $(ENV_DEV) --out $(SECRETS_DEV)

.PHONY: dev-build
dev-build: check-env dev-secrets ## Build dev stack images.
	$(DC_DEV) build

.PHONY: dev-up
dev-up: check-env dev-secrets dev-fixture-bootstrap ## Start the dev stack (detached, waits for healthchecks). Auto-refreshes data/dev/* fixture before bringing the stack up.
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

.PHONY: dev-fixture-bootstrap
dev-fixture-bootstrap: ## Populate the bind-mounted data/dev/{briefs,enriched,input,results}/ paths from prod sources + 30-domain fixture. Does NOT seed the dev stack's clients.db (lives in the heimdall_dev_client-data named volume) — use `make dev-seed` for the host-only data/dev/clients.db.
	@mkdir -p data/dev/briefs data/dev/enriched data/dev/input data/dev/results
	@python -m scripts.dev.seed_dev_briefs
	@python -m scripts.dev.seed_dev_enriched

.PHONY: dev-fixture-refresh
dev-fixture-refresh: dev-fixture-bootstrap ## Re-run all dev fixture seeds (call after prod briefs / enriched DB change).
	@echo "dev fixture refreshed"

.PHONY: dev-fixture-check
dev-fixture-check: ## Verify dev fixture sources exist (briefs + enriched companies). No writes.
	@python -m scripts.dev.seed_dev_briefs --check
	@python -m scripts.dev.seed_dev_enriched --check

.PHONY: dev-seed-console
dev-seed-console: dev-up ## Seed DRYRUN-CONSOLE-* rows for V1 (trial-expiring) + V6 (retention-queue) inside the dev delivery container.
	@docker cp scripts/dev/seed_dev_console.py heimdall_dev-delivery-1:/app/scripts/dev/seed_dev_console.py
	@docker exec heimdall_dev-delivery-1 python scripts/dev/seed_dev_console.py

.PHONY: dev-seed-console-clean
dev-seed-console-clean: dev-up ## Wipe DRYRUN-CONSOLE-* rows from the dev clients DB (no re-seed).
	@docker cp scripts/dev/seed_dev_console.py heimdall_dev-delivery-1:/app/scripts/dev/seed_dev_console.py
	@docker exec heimdall_dev-delivery-1 python scripts/dev/seed_dev_console.py --clean

.PHONY: dev-verify-seed-console
dev-verify-seed-console: dev-up ## End-to-end verify: seed → assert shape → clean → assert empty. One command, explicit pass/fail.
	@$(MAKE) dev-seed-console
	@echo "==> verify post-seed shape"
	@python -m scripts.dev.verify_dev_console_seed
	@$(MAKE) dev-seed-console-clean
	@echo "==> verify post-clean empty"
	@python -m scripts.dev.verify_dev_console_seed --post-clean
	@echo "dev console seed verify: OK"

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

.PHONY: dev-verify-api-write
dev-verify-api-write: dev-up ## Probe whether the api container has RW on clients.db. Guards against the PR #46 :ro-mount regression.
	@bash scripts/dev/verify_api_clients_db_write.sh

.PHONY: dev-cert-dry-run
dev-cert-dry-run: dev-up ## End-to-end cert-change alert dry run (synthetic target, no Telegram send).
	@docker cp scripts/dev/cert_change_dry_run.py heimdall_dev-delivery-1:/app/scripts/dev/cert_change_dry_run.py
	@docker cp config/ct_dry_run.json heimdall_dev-delivery-1:/app/config/ct_dry_run.json
	@docker exec heimdall_dev-delivery-1 python scripts/dev/cert_change_dry_run.py

.PHONY: dev-interpret-dry-run
dev-interpret-dry-run: dev-up ## Interpreter operational dry run (MODE=observe|send-to-operator, default observe; send mode costs ~0.02 USD).
	@docker cp scripts/dev/interpret_dry_run.py heimdall_dev-delivery-1:/app/scripts/dev/interpret_dry_run.py
	@docker cp config/interpret_dry_run.json heimdall_dev-delivery-1:/app/config/interpret_dry_run.json
	@docker exec heimdall_dev-delivery-1 python scripts/dev/interpret_dry_run.py --mode=$(or $(MODE),observe)

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
	@echo "==> backup.sh under default project 'docker' should SKIP clients.db (guards 2489905 regression)"
	@tmpdir=$$(mktemp -d); \
	    default_count=$$(docker compose -p docker -f $(COMPOSE_PROD) ps -q 2>/dev/null | wc -l | tr -d ' '); \
	    if [ "$$default_count" -ne 0 ]; then \
	        echo "    skipping — 'docker' project has $$default_count containers locally, cannot isolate"; \
	        rm -rf $$tmpdir; \
	    else \
	        env -u HEIMDALL_COMPOSE_PROJECT HEIMDALL_BACKUP_DIR=$$tmpdir \
	            bash scripts/backup.sh >/dev/null 2>&1 || true; \
	        if grep -q "OK: clients.db" $$tmpdir/backup.log 2>/dev/null; then \
	            echo "REGRESSION: clients.db backed up under default project 'docker' — project-name coupling is broken"; \
	            cat $$tmpdir/backup.log; \
	            rm -rf $$tmpdir; \
	            exit 1; \
	        fi; \
	        if ! grep -q "SKIP: clients.db" $$tmpdir/backup.log 2>/dev/null; then \
	            echo "REGRESSION: backup.sh did not emit 'SKIP: clients.db' under default project 'docker'"; \
	            cat $$tmpdir/backup.log 2>/dev/null || echo "(no log written)"; \
	            rm -rf $$tmpdir; \
	            exit 1; \
	        fi; \
	        rm -rf $$tmpdir; \
	    fi
	@echo "==> project-name coupling: dev stack resolves under 'heimdall_dev'"
	@count=$$($(DC_DEV) ps -q 2>/dev/null | wc -l | tr -d ' '); \
	    if [ "$$count" -lt 5 ]; then \
	        echo "FAIL: 'heimdall_dev' project resolves $$count containers, expected >=5"; \
	        exit 1; \
	    fi
	@echo "==> /run/secrets populated in every service that mounts them"
	@fail=0; \
	    for pair in scheduler:claude_api_key scheduler:telegram_bot_token scheduler:certspotter_api_key \
	                worker:grayhatwarfare_api_key \
	                api:telegram_bot_token api:claude_api_key api:console_password \
	                delivery:telegram_bot_token delivery:claude_api_key delivery:certspotter_api_key; do \
	        svc=$${pair%:*}; secret=$${pair#*:}; \
	        if ! $(DC_DEV) exec -T $$svc test -s /run/secrets/$$secret 2>/dev/null; then \
	            echo "FAIL: /run/secrets/$$secret missing or empty in $$svc"; \
	            fail=1; \
	        fi; \
	    done; \
	    if [ $$fail -ne 0 ]; then exit 1; fi
	@echo "==> no env-var fallback for the 5 file-backed credentials"
	@fail=0; \
	    for pair in scheduler:CLAUDE_API_KEY scheduler:TELEGRAM_BOT_TOKEN scheduler:CERTSPOTTER_API_KEY \
	                worker:GRAYHATWARFARE_API_KEY \
	                api:TELEGRAM_BOT_TOKEN api:CLAUDE_API_KEY api:CONSOLE_PASSWORD \
	                delivery:TELEGRAM_BOT_TOKEN delivery:CLAUDE_API_KEY delivery:CERTSPOTTER_API_KEY; do \
	        svc=$${pair%:*}; var=$${pair#*:}; \
	        value=$$($(DC_DEV) exec -T $$svc printenv $$var 2>/dev/null || true); \
	        if [ -n "$$value" ]; then \
	            echo "FAIL: env var $$var is set in $$svc — file-backed secret bypassed"; \
	            fail=1; \
	        fi; \
	    done; \
	    if [ $$fail -ne 0 ]; then exit 1; fi
	@echo "dev ops smoke: OK"

# --- Signup site (apps/signup/) -----------------------------------------

.PHONY: signup-dev
signup-dev: ## Run the SvelteKit signup site dev server (host :5173, /api → :8001).
	cd apps/signup && npm install --prefer-offline && npm run dev

.PHONY: signup-build
signup-build: ## Build the SvelteKit signup site to apps/signup/build/.
	cd apps/signup && npm install --prefer-offline && npm run build

.PHONY: signup-test
signup-test: ## Run the signup-site Vitest suite.
	cd apps/signup && npm install --prefer-offline && npm run test

.PHONY: frontend-test
frontend-test: ## Run the operator-console SPA Vitest suite.
	cd src/api/frontend && npm install --prefer-offline && npm run test

.PHONY: signup-verify
signup-verify: dev-up ## Run scripts/dev/verify_signup_slice1.py inside the dev delivery container (RW client-data + scripts/dev mounted).
	@docker cp scripts/dev/verify_signup_slice1.py heimdall_dev-delivery-1:/app/scripts/dev/verify_signup_slice1.py
	@docker exec heimdall_dev-delivery-1 python scripts/dev/verify_signup_slice1.py

.PHONY: signup-issue-token
signup-issue-token: dev-up ## Issue a fresh signup token + print the browser URL for /signup/start.
	@docker cp scripts/dev/issue_signup_token.py heimdall_dev-delivery-1:/app/scripts/dev/issue_signup_token.py
	@docker exec heimdall_dev-delivery-1 python scripts/dev/issue_signup_token.py

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
