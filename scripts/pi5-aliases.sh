#!/bin/bash
# Heimdall Pi5 commands — source this from ~/.bashrc:
#   echo 'source ~/heimdall/scripts/pi5-aliases.sh' >> ~/.bashrc

# Prevent shell-env contamination of compose project name. Every alias below
# pins `-p docker` explicitly so the project name is unambiguous in logs and
# `docker ps`, regardless of cwd or environment.
unset COMPOSE_PROJECT_NAME

HEIMDALL_DIR="$HOME/heimdall"
COMPOSE_FILE="$HEIMDALL_DIR/infra/docker/docker-compose.yml"
COMPOSE_MON="$HEIMDALL_DIR/infra/docker/docker-compose.monitoring.yml"

# Git-SHA image tags. Exported so docker compose expands ${HEIMDALL_TAG:-latest}
# in the image: field of every buildable service. `-dirty` suffix fires if the
# checkout has uncommitted changes — stops accidental "latest" builds of
# untracked code from shipping silently.
export HEIMDALL_TAG="$(cd "$HEIMDALL_DIR" && git rev-parse --short HEAD 2>/dev/null)$(cd "$HEIMDALL_DIR" && git diff --quiet 2>/dev/null || echo -dirty)"

# Pi5 tracks the `prod` branch. `main` is dev-tested work; `prod` is
# what has also passed `make dev-smoke` on the laptop AND been pushed
# via the .githooks/pre-push gate. See docs/runbook-prod-deploy.md.
alias heimdall-deploy="cd $HEIMDALL_DIR && git fetch origin && git checkout prod && git pull --ff-only origin prod && docker compose -p docker -f $COMPOSE_FILE build worker && docker compose -p docker -f $COMPOSE_FILE build api scheduler delivery && docker compose -p docker -f $COMPOSE_FILE -f $COMPOSE_MON up -d --force-recreate --remove-orphans"
alias heimdall-quick="cd $HEIMDALL_DIR && git fetch origin && git checkout prod && git pull --ff-only origin prod && docker compose -p docker -f $COMPOSE_FILE build scheduler api && docker compose -p docker -f $COMPOSE_FILE -f $COMPOSE_MON up -d --force-recreate --remove-orphans"
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

# Rollback to a prior git-SHA image tag. Usage: heimdall-rollback abc1234
# The tag must already exist as a local docker image — this PR does not push
# to a registry, so rollback is limited to the local image cache (which
# `docker image prune` will wipe). PR-F will remove that limitation by
# pushing to GHCR on every main-branch build.
heimdall-rollback() {
    if [ -z "${1:-}" ]; then
        echo "usage: heimdall-rollback <short-sha>"
        echo "available local tags:"
        docker images --format '{{.Repository}}:{{.Tag}}' | grep '^heimdall-' | sort -u
        return 1
    fi
    local target="$1"
    if ! docker images --format '{{.Repository}}:{{.Tag}}' | grep -q ":${target}$"; then
        echo "error: no local image tagged :${target}. Rebuild or pull first."
        return 1
    fi
    cd "$HEIMDALL_DIR" || return 1
    HEIMDALL_TAG="$target" docker compose -p docker -f "$COMPOSE_FILE" -f "$COMPOSE_MON" up -d --force-recreate --remove-orphans
}
