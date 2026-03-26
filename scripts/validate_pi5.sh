#!/usr/bin/env bash
# Heimdall Pi5 Readiness Validator
# Run on the Pi5 before first deployment.
# Usage: bash scripts/validate_pi5.sh

set -euo pipefail

PASS=0
FAIL=0
WARN=0

pass() { echo "  ✓ $1"; ((PASS++)); }
fail() { echo "  ✗ $1"; ((FAIL++)); }
warn() { echo "  ! $1"; ((WARN++)); }

echo "============================================"
echo "  Heimdall Pi5 Readiness Check"
echo "============================================"
echo ""

# --- Hardware ---
echo "Hardware:"
if [ -f /proc/device-tree/model ]; then
    MODEL=$(cat /proc/device-tree/model)
    echo "  Model: $MODEL"
    if echo "$MODEL" | grep -q "Raspberry Pi 5"; then
        pass "Raspberry Pi 5 detected"
    else
        warn "Not a Pi 5 — $MODEL (may still work)"
    fi
else
    warn "Cannot detect hardware model (not a Pi?)"
fi

MEM_KB=$(grep MemTotal /proc/meminfo 2>/dev/null | awk '{print $2}')
MEM_KB=${MEM_KB:-0}
MEM_GB=$(python3 -c "print(f'{${MEM_KB}/1048576:.1f}')" 2>/dev/null || echo "?")
if [ "$MEM_KB" -ge 7000000 ] 2>/dev/null; then
    pass "RAM: ${MEM_GB} GB (need ≥8 GB)"
elif [ "$MEM_KB" -ge 3500000 ] 2>/dev/null; then
    warn "RAM: ${MEM_GB} GB (8 GB recommended, will work with fewer workers)"
else
    fail "RAM: ${MEM_GB} GB (minimum 4 GB required)"
fi

DISK_AVAIL=$(df -BG / 2>/dev/null | tail -1 | awk '{print $4}' | tr -d 'G' || echo 0)
if [ "$DISK_AVAIL" -ge 10 ] 2>/dev/null; then
    pass "Disk: ${DISK_AVAIL} GB available"
else
    fail "Disk: ${DISK_AVAIL} GB available (need ≥10 GB for Docker images + data)"
fi
echo ""

# --- OS ---
echo "Operating System:"
if [ -f /etc/os-release ]; then
    . /etc/os-release
    echo "  $PRETTY_NAME"
    if echo "$ID" | grep -qE "debian|raspbian"; then
        pass "Debian-based OS"
    else
        warn "Non-Debian OS — Docker install may differ"
    fi
fi

ARCH=$(uname -m)
if [ "$ARCH" = "aarch64" ]; then
    pass "Architecture: arm64 (aarch64)"
else
    warn "Architecture: $ARCH (expected aarch64)"
fi
echo ""

# --- Docker ---
echo "Docker:"
if command -v docker &>/dev/null; then
    DOCKER_VER=$(docker --version 2>/dev/null || echo "unknown")
    pass "Docker installed: $DOCKER_VER"
else
    fail "Docker not installed — run: curl -fsSL https://get.docker.com | sh"
fi

if command -v docker &>/dev/null && docker compose version &>/dev/null; then
    COMPOSE_VER=$(docker compose version 2>/dev/null || echo "unknown")
    pass "Docker Compose: $COMPOSE_VER"
else
    fail "Docker Compose not available — install docker-compose-plugin"
fi

if command -v docker &>/dev/null && docker info &>/dev/null 2>&1; then
    pass "Docker daemon running"
else
    fail "Docker daemon not running — run: sudo systemctl start docker"
fi

if groups | grep -q docker; then
    pass "Current user in docker group"
else
    warn "Current user not in docker group — may need sudo for docker commands"
fi
echo ""

# --- Network ---
echo "Network:"
if ping -c 1 -W 3 1.1.1.1 &>/dev/null; then
    pass "Internet connectivity"
else
    fail "No internet — Docker build requires downloading images"
fi

if command -v tailscale &>/dev/null; then
    TS_STATUS=$(tailscale status --json 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('BackendState','unknown'))" 2>/dev/null || echo "unknown")
    if [ "$TS_STATUS" = "Running" ]; then
        pass "Tailscale: running"
    else
        warn "Tailscale installed but status: $TS_STATUS"
    fi
else
    warn "Tailscale not installed — needed for secure remote access"
fi
echo ""

# --- Project files ---
echo "Project files:"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

if [ -f "$PROJECT_ROOT/infra/docker/docker-compose.yml" ]; then
    pass "docker-compose.yml found"
else
    fail "docker-compose.yml not found at infra/docker/"
fi

if [ -f "$PROJECT_ROOT/infra/docker/Dockerfile.worker" ]; then
    pass "Dockerfile.worker found"
else
    fail "Dockerfile.worker not found"
fi

if [ -f "$PROJECT_ROOT/infra/docker/Dockerfile.scheduler" ]; then
    pass "Dockerfile.scheduler found"
else
    fail "Dockerfile.scheduler not found"
fi

if [ -f "$PROJECT_ROOT/infra/docker/.env.template" ]; then
    pass ".env.template found"
else
    fail ".env.template not found"
fi

if [ -f "$PROJECT_ROOT/infra/docker/.env" ]; then
    pass ".env file exists"
else
    warn ".env not found — copy from .env.template and fill in values"
fi

if [ -f "$PROJECT_ROOT/agents/valdi/approvals.json" ]; then
    pass "Valdí approvals.json found"
else
    fail "Valdí approvals.json missing — worker will refuse to start"
fi

if [ -f "$PROJECT_ROOT/config/filters.json" ]; then
    pass "filters.json found"
else
    fail "filters.json missing"
fi
echo ""

# --- Data directories ---
echo "Data directories:"
for dir in data/input data/output data/output/briefs data/results data/benchmarks; do
    FULL="$PROJECT_ROOT/$dir"
    if [ -d "$FULL" ]; then
        pass "$dir/"
    else
        warn "$dir/ does not exist — will be created by Docker volumes"
    fi
done
echo ""

# --- Summary ---
echo "============================================"
echo "  Results: $PASS passed, $FAIL failed, $WARN warnings"
echo "============================================"

if [ "$FAIL" -gt 0 ]; then
    echo ""
    echo "  Fix the failures above before deploying."
    exit 1
else
    echo ""
    echo "  Ready for: docker compose -f infra/docker/docker-compose.yml up --build"
    exit 0
fi
