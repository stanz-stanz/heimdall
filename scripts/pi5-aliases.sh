#!/bin/bash
# Heimdall Pi5 commands — source this from ~/.bashrc:
#   echo 'source ~/heimdall/scripts/pi5-aliases.sh' >> ~/.bashrc

HEIMDALL_DIR="$HOME/heimdall"
COMPOSE_FILE="$HEIMDALL_DIR/infra/docker/docker-compose.yml"
COMPOSE_MON="$HEIMDALL_DIR/infra/docker/docker-compose.monitoring.yml"

alias heimdall-deploy="cd $HEIMDALL_DIR && git pull && docker compose -f $COMPOSE_FILE -f $COMPOSE_MON up -d --build"
alias heimdall-export="cd $HEIMDALL_DIR && PYTHONPATH=$HEIMDALL_DIR python3 scripts/export_results.py --results-dir data/results --output-dir data/output"
alias heimdall-analyze="cd $HEIMDALL_DIR && python3 scripts/analyze_pipeline.py"
alias heimdall-status="docker compose -f $COMPOSE_FILE -f $COMPOSE_MON ps"
alias heimdall-logs="docker compose -f $COMPOSE_FILE logs --tail 30"
alias heimdall-worker-logs="docker compose -f $COMPOSE_FILE logs worker --tail 50"
alias heimdall-scheduler-logs="docker compose -f $COMPOSE_FILE logs scheduler --tail 30"
alias heimdall-queue="docker compose -f $COMPOSE_FILE exec -T redis redis-cli LLEN queue:scan && docker compose -f $COMPOSE_FILE exec -T redis redis-cli LLEN queue:enrichment && docker compose -f $COMPOSE_FILE exec -T redis redis-cli LLEN queue:wpscan"
alias heimdall-count="find $HEIMDALL_DIR/data/results -name '*.json' -type f 2>/dev/null | wc -l"
alias heimdall-stop="docker compose -f $COMPOSE_FILE -f $COMPOSE_MON down"
alias heimdall-flush="docker compose -f $COMPOSE_FILE exec -T redis redis-cli DEL queue:scan queue:enrichment queue:wpscan"
alias heimdall-pipeline="docker compose -f $COMPOSE_FILE run --rm --entrypoint bash worker scripts/docker-smoke.sh && docker compose -f $COMPOSE_FILE exec -T redis redis-cli DEL queue:scan queue:enrichment queue:wpscan && docker compose -f $COMPOSE_FILE run --rm scheduler"
alias heimdall-smoke="docker compose -f $COMPOSE_FILE run --rm --entrypoint bash worker scripts/docker-smoke.sh"
alias heimdall-audit="cd $HEIMDALL_DIR && python3 scripts/audit.py"
