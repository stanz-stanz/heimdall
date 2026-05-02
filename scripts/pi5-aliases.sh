#!/bin/bash
# Heimdall Pi5 commands — source this from ~/.bashrc:
#   echo 'source ~/heimdall/scripts/pi5-aliases.sh' >> ~/.bashrc

# Prevent shell-env contamination of compose project name. Every alias below
# pins `-p docker` explicitly so the project name is unambiguous in logs and
# `docker ps`, regardless of cwd or environment.
unset COMPOSE_PROJECT_NAME

# Same defence for the dev/prod data-isolation overrides (M37 finalisation,
# 2026-04-26). The base compose's host bind-mounts use ${VAR:-default}; if
# any of these four were ever exported in this shell (e.g. someone sourced
# infra/compose/.env.dev on a Mac dev box and then called the aliases) the
# prod-targeted aliases below would silently mount data/dev/* paths.
unset INPUT_HOST_DIR ENRICHED_HOST_DIR RESULTS_HOST_DIR BRIEFS_HOST_DIR

HEIMDALL_DIR="$HOME/heimdall"
COMPOSE_FILE="$HEIMDALL_DIR/infra/compose/docker-compose.yml"
COMPOSE_MON="$HEIMDALL_DIR/infra/compose/docker-compose.monitoring.yml"

# Git-SHA image tags. Exported so docker compose expands ${HEIMDALL_TAG:-latest}
# in the image: field of every buildable service. `-dirty` suffix fires if the
# checkout has uncommitted changes — stops accidental "latest" builds of
# untracked code from shipping silently.
export HEIMDALL_TAG="$(cd "$HEIMDALL_DIR" && git rev-parse --short HEAD 2>/dev/null)$(cd "$HEIMDALL_DIR" && git diff --quiet 2>/dev/null || echo -dirty)"

# Pi5 tracks the `prod` branch. `main` is dev-tested work; `prod` is
# what has also passed `make dev-smoke` on the laptop AND been pushed
# via the .githooks/pre-push gate. See docs/runbook-prod-deploy.md.
# Function names use underscores (POSIX-compliant); the user-facing
# `heimdall-deploy` / `heimdall-quick` names are aliased below so the
# operator's existing muscle memory works unchanged. POSIX-mode bash
# (`set -o posix`, common in Debian/Raspbian login shells) rejects
# function names with hyphens — caught when sourcing this file on Pi5
# 2026-05-02.
_heimdall_deploy() {
    cd "$HEIMDALL_DIR" || return 1
    git fetch origin || return 1
    git checkout prod || return 1
    git pull --ff-only origin prod || return 1
    # Recompute after the pull so image labels match the deployed SHA.
    # Line-25 export is the shell-load default; this overrides it for
    # the build that follows.
    export HEIMDALL_TAG="$(git rev-parse --short HEAD)$(git diff --quiet || echo -dirty)"
    docker compose -p docker -f "$COMPOSE_FILE" build worker || return 1
    docker compose -p docker -f "$COMPOSE_FILE" build api scheduler delivery || return 1
    docker compose -p docker -f "$COMPOSE_FILE" -f "$COMPOSE_MON" up -d --force-recreate --remove-orphans
}
alias heimdall-deploy='_heimdall_deploy'

_heimdall_quick() {
    cd "$HEIMDALL_DIR" || return 1
    git fetch origin || return 1
    git checkout prod || return 1
    git pull --ff-only origin prod || return 1
    export HEIMDALL_TAG="$(git rev-parse --short HEAD)$(git diff --quiet || echo -dirty)"
    docker compose -p docker -f "$COMPOSE_FILE" build scheduler api || return 1
    docker compose -p docker -f "$COMPOSE_FILE" -f "$COMPOSE_MON" up -d --force-recreate --remove-orphans
}
alias heimdall-quick='_heimdall_quick'
alias heimdall-export="cd $HEIMDALL_DIR && docker compose -p docker -f $COMPOSE_FILE run --rm --no-deps -v $HEIMDALL_DIR/data/input:/data/input:ro -v $HEIMDALL_DIR/data/output:/data/output --entrypoint sh worker -c 'PYTHONPATH=/app python3 scripts/export_results.py --results-dir /data/results --output-dir /data/output --cvr-file /data/input/CVR-extract.xlsx'"
alias heimdall-analyze="cd $HEIMDALL_DIR && docker compose -p docker -f $COMPOSE_FILE run --rm --no-deps -v $HEIMDALL_DIR/data/output:/data/output:ro --entrypoint sh worker -c 'PYTHONPATH=/app python3 scripts/analyze_pipeline.py --results-dir /data/results'"
alias heimdall-deep="cd $HEIMDALL_DIR && docker compose -p docker -f $COMPOSE_FILE run --rm --no-deps -v $HEIMDALL_DIR/data/output:/data/output:ro --entrypoint sh worker -c 'PYTHONPATH=/app python3 scripts/analyze_pipeline.py --results-dir /data/results --deep'"
alias heimdall-status="docker compose -p docker -f $COMPOSE_FILE -f $COMPOSE_MON ps"
alias heimdall-logs="docker compose -p docker -f $COMPOSE_FILE logs --tail 30"
alias heimdall-worker-logs="docker compose -p docker -f $COMPOSE_FILE logs worker --tail 50"
alias heimdall-scheduler-logs="docker compose -p docker -f $COMPOSE_FILE logs scheduler --tail 30"
alias heimdall-delivery-logs="docker compose -p docker -f $COMPOSE_FILE logs delivery --tail 50"
alias heimdall-queue="echo -n 'scan: ' && docker compose -p docker -f $COMPOSE_FILE exec -T redis redis-cli LLEN queue:scan && echo -n 'enrichment: ' && docker compose -p docker -f $COMPOSE_FILE exec -T redis redis-cli LLEN queue:enrichment"
alias heimdall-count="find $HEIMDALL_DIR/data/results -name '*.json' -type f 2>/dev/null | wc -l"
alias heimdall-stop="docker compose -p docker -f $COMPOSE_FILE -f $COMPOSE_MON down"
alias heimdall-flush="docker compose -p docker -f $COMPOSE_FILE exec -T redis redis-cli DEL queue:scan queue:enrichment enrichment:completed enrichment:total"
alias heimdall-pipeline="docker compose -p docker -f $COMPOSE_FILE run --rm --entrypoint bash -v $HEIMDALL_DIR/scripts/docker-smoke.sh:/tmp/smoke.sh:ro worker /tmp/smoke.sh && docker compose -p docker -f $COMPOSE_FILE stop scheduler 2>/dev/null; docker compose -p docker -f $COMPOSE_FILE exec -T redis redis-cli DEL queue:scan queue:enrichment enrichment:completed enrichment:total && echo 'Clearing old results...' && rm -rf $HEIMDALL_DIR/data/results/prospect && docker compose -p docker -f $COMPOSE_FILE up -d --force-recreate && docker compose -p docker -f $COMPOSE_FILE run --rm scheduler"
alias heimdall-smoke="docker compose -p docker -f $COMPOSE_FILE run --rm --entrypoint bash -v $HEIMDALL_DIR/scripts/docker-smoke.sh:/tmp/smoke.sh:ro worker /tmp/smoke.sh"
alias heimdall-audit="cd $HEIMDALL_DIR && python3 scripts/audit.py"

# Manual wrappers for scripts that normally run via cron/one-shot.
# Surfacing them as aliases lets the operator trigger them ad-hoc.
alias heimdall-backup="$HEIMDALL_DIR/scripts/backup.sh"
alias heimdall-health="$HEIMDALL_DIR/scripts/healthcheck.sh"
alias heimdall-validate="bash $HEIMDALL_DIR/scripts/validate_pi5.sh"

# M33 operational verification: confirm the Claude API key is delivered via
# /run/secrets (file-backed) and NOT leaked into the CLAUDE_API_KEY env var
# for every service that mounts it. Run post-deploy and after any compose
# secrets edit.
#
# Uses `test -s` (exit code only) — never reads secret contents. Even a byte
# count leaks signal, so no cat/head/wc. The env-var absence check catches
# a PR-D regression where a service still pulls the key from the environment.
heimdall-verify-secrets() {
    local fail=0
    local svc
    for svc in scheduler api delivery; do
        if ! docker compose -p docker -f "$COMPOSE_FILE" exec -T "$svc" test -s /run/secrets/claude_api_key; then
            echo "FAIL: $svc /run/secrets/claude_api_key missing or empty"
            fail=1
        fi
        if ! docker compose -p docker -f "$COMPOSE_FILE" exec -T "$svc" sh -c 'test -z "$CLAUDE_API_KEY"'; then
            echo "FAIL: $svc CLAUDE_API_KEY env var is SET — file-backed secret bypassed"
            fail=1
        fi
    done
    if [ "$fail" -ne 0 ]; then
        return 1
    fi
    echo "OK: claude_api_key populated via /run/secrets in 3 services, no env fallback"
    return 0
}

# List locally-cached SHA-tagged Heimdall images — first-choice rollback
# targets. If a SHA is not in this list, heimdall-rollback falls through
# to GHCR pull (publish-images.yml keeps the last ~30 SHAs per service).
alias heimdall-tags="docker images --format '{{.Repository}}:{{.Tag}}\t{{.CreatedSince}}' | grep '^heimdall-' | sort -u"

# GHCR org — derived from HEIMDALL_GHCR_OWNER or the git remote.
# Override via export HEIMDALL_GHCR_OWNER=... in ~/.bashrc if the repo owner
# ever changes.
HEIMDALL_GHCR_OWNER="${HEIMDALL_GHCR_OWNER:-stanz-stanz}"

# Rollback to a prior git-SHA image tag. Usage: heimdall-rollback abc1234
# Tries local cache first; if absent, pulls all 5 images from GHCR,
# retags atomically, then recreates the stack. If any pull fails, no
# retag happens — local state stays consistent.
heimdall-rollback() {
    local target="${1:-}"
    if [ -z "$target" ]; then
        echo "usage: heimdall-rollback <short-sha>"
        echo "local tags:"
        docker images --format '{{.Repository}}:{{.Tag}}' | grep '^heimdall-' | sort -u
        return 1
    fi

    local svcs=(api delivery scheduler worker twin)

    if ! docker images --format '{{.Repository}}:{{.Tag}}' | grep -q ":${target}$"; then
        echo "not in local cache. pulling heimdall-*:${target} from GHCR..."
        for svc in "${svcs[@]}"; do
            local ref="ghcr.io/${HEIMDALL_GHCR_OWNER}/heimdall-${svc}:${target}"
            if ! docker pull "$ref"; then
                echo "ERROR: pull failed for ${ref}. aborting before retag."
                return 1
            fi
        done
        # All pulls succeeded — retag as the local short name so the
        # compose image: field resolves without modification, and log
        # each digest for the forensic trail.
        for svc in "${svcs[@]}"; do
            local ref="ghcr.io/${HEIMDALL_GHCR_OWNER}/heimdall-${svc}:${target}"
            local digest
            digest=$(docker image inspect "$ref" --format '{{.Id}}')
            docker tag "$ref" "heimdall-${svc}:${target}"
            echo "retagged heimdall-${svc}:${target} (digest: ${digest})"
        done
    fi

    cd "$HEIMDALL_DIR" || return 1
    HEIMDALL_TAG="$target" docker compose -p docker -f "$COMPOSE_FILE" -f "$COMPOSE_MON" up -d --force-recreate --remove-orphans
}
