#!/bin/bash
# Heimdall Pi5 commands — source this from ~/.bashrc:
#   echo 'source ~/heimdall/scripts/pi5-aliases.sh' >> ~/.bashrc

HEIMDALL_DIR="$HOME/heimdall"
COMPOSE_FILE="$HEIMDALL_DIR/infra/docker/docker-compose.yml"
COMPOSE_MON="$HEIMDALL_DIR/infra/docker/docker-compose.monitoring.yml"

alias heimdall-deploy="cd $HEIMDALL_DIR && git pull && docker compose -f $COMPOSE_FILE build worker && docker compose -f $COMPOSE_FILE build api ct-collector scheduler delivery && docker compose -f $COMPOSE_FILE -f $COMPOSE_MON up -d --force-recreate --remove-orphans"
alias heimdall-quick="cd $HEIMDALL_DIR && git pull && docker compose -f $COMPOSE_FILE build scheduler api && docker compose -f $COMPOSE_FILE -f $COMPOSE_MON up -d --force-recreate --remove-orphans"
alias heimdall-export="cd $HEIMDALL_DIR && docker compose -f $COMPOSE_FILE run --rm --no-deps -v $HEIMDALL_DIR/data/input:/data/input:ro -v $HEIMDALL_DIR/data/output:/data/output --entrypoint python3 worker scripts/export_results.py --results-dir /data/results --output-dir /data/output --cvr-file /data/input/CVR-extract.xlsx"
alias heimdall-analyze="cd $HEIMDALL_DIR && docker compose -f $COMPOSE_FILE run --rm --no-deps -v $HEIMDALL_DIR/data/output:/data/output:ro --entrypoint python3 worker scripts/analyze_pipeline.py --results-dir /data/results"
alias heimdall-deep="cd $HEIMDALL_DIR && docker compose -f $COMPOSE_FILE run --rm --no-deps -v $HEIMDALL_DIR/data/output:/data/output:ro --entrypoint python3 worker scripts/analyze_pipeline.py --results-dir /data/results --deep"
alias heimdall-status="docker compose -f $COMPOSE_FILE -f $COMPOSE_MON ps"
alias heimdall-logs="docker compose -f $COMPOSE_FILE logs --tail 30"
alias heimdall-worker-logs="docker compose -f $COMPOSE_FILE logs worker --tail 50"
alias heimdall-scheduler-logs="docker compose -f $COMPOSE_FILE logs scheduler --tail 30"
alias heimdall-delivery-logs="docker compose -f $COMPOSE_FILE logs delivery --tail 50"
alias heimdall-queue="echo -n 'scan: ' && docker compose -f $COMPOSE_FILE exec -T redis redis-cli LLEN queue:scan && echo -n 'enrichment: ' && docker compose -f $COMPOSE_FILE exec -T redis redis-cli LLEN queue:enrichment"
alias heimdall-count="find $HEIMDALL_DIR/data/results -name '*.json' -type f 2>/dev/null | wc -l"
alias heimdall-stop="docker compose -f $COMPOSE_FILE -f $COMPOSE_MON down"
alias heimdall-flush="docker compose -f $COMPOSE_FILE exec -T redis redis-cli DEL queue:scan queue:enrichment enrichment:completed enrichment:total"
alias heimdall-pipeline="docker compose -f $COMPOSE_FILE run --rm --entrypoint bash -v $HEIMDALL_DIR/scripts/docker-smoke.sh:/tmp/smoke.sh:ro worker /tmp/smoke.sh && docker compose -f $COMPOSE_FILE stop scheduler 2>/dev/null; docker compose -f $COMPOSE_FILE exec -T redis redis-cli DEL queue:scan queue:enrichment enrichment:completed enrichment:total && echo 'Clearing old results...' && rm -rf $HEIMDALL_DIR/data/results/prospect && docker compose -f $COMPOSE_FILE up -d --force-recreate && docker compose -f $COMPOSE_FILE run --rm scheduler"
alias heimdall-smoke="docker compose -f $COMPOSE_FILE run --rm --entrypoint bash -v $HEIMDALL_DIR/scripts/docker-smoke.sh:/tmp/smoke.sh:ro worker /tmp/smoke.sh"
alias heimdall-audit="cd $HEIMDALL_DIR && python3 scripts/audit.py"
