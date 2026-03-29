#!/bin/bash
# Heimdall Pi5 aliases — source this from ~/.bashrc or ~/.zshrc:
#   echo 'source ~/heimdall/scripts/pi5-aliases.sh' >> ~/.bashrc

HEIMDALL_DIR="$HOME/heimdall"
COMPOSE_FILE="$HEIMDALL_DIR/infra/docker/docker-compose.yml"
COMPOSE_MON="$HEIMDALL_DIR/infra/docker/docker-compose.monitoring.yml"

# Deploy: pull + build + start everything
alias heimdall-deploy="cd $HEIMDALL_DIR && git pull && docker compose -f $COMPOSE_FILE -f $COMPOSE_MON up -d --build"

# Run the prospecting pipeline (scheduler creates jobs, workers process them)
alias heimdall-pipeline="docker compose -f $COMPOSE_FILE run --rm scheduler"

# Export results to CSV + briefs after a pipeline run
alias heimdall-export="cd $HEIMDALL_DIR && python3 scripts/export_results.py --results-dir data/results --output-dir data/output"

# Status: show all containers
alias heimdall-status="docker compose -f $COMPOSE_FILE -f $COMPOSE_MON ps"

# Logs: recent worker logs
alias heimdall-logs="docker compose -f $COMPOSE_FILE logs --tail 30"

# Worker logs specifically
alias heimdall-worker-logs="docker compose -f $COMPOSE_FILE logs worker --tail 50"

# Scheduler logs
alias heimdall-scheduler-logs="docker compose -f $COMPOSE_FILE logs scheduler --tail 30"

# Queue depths: check what's pending
alias heimdall-queue="docker compose -f $COMPOSE_FILE exec redis redis-cli LLEN queue:scan && docker compose -f $COMPOSE_FILE exec redis redis-cli LLEN queue:enrichment && docker compose -f $COMPOSE_FILE exec redis redis-cli LLEN queue:wpscan"

# Results: count completed scans
alias heimdall-count="find $HEIMDALL_DIR/data/results -name '*.json' -type f 2>/dev/null | wc -l"

# Stop everything
alias heimdall-stop="docker compose -f $COMPOSE_FILE -f $COMPOSE_MON down"

# Full run: deploy + pipeline + wait + export
heimdall-full-run() {
    echo "=== Deploying ==="
    heimdall-deploy
    echo ""
    echo "=== Running pipeline ==="
    heimdall-pipeline
    echo ""
    echo "=== Waiting for workers to drain queue ==="
    while true; do
        remaining=$(docker compose -f $COMPOSE_FILE exec -T redis redis-cli LLEN queue:scan 2>/dev/null | tr -d '[:space:]')
        if [ "$remaining" = "0" ] || [ -z "$remaining" ]; then
            break
        fi
        echo "  Queue: $remaining jobs remaining..."
        sleep 10
    done
    echo "=== Queue drained ==="
    echo ""
    echo "=== Exporting results ==="
    heimdall-export
}
