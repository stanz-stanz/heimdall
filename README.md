<p align="center">
  <img src="/docs/images/heimdall.png?raw=true" alt="Heimdall keeps watch for invaders"/>
</p>

# Project Heimdall

## An AI-Powered Cybersecurity Service for Small Businesses

External Attack Surface Management (EASM) for small and medium businesses (SMBs) that handle customer data and risk breaching GDPR regulations. Finds vulnerabilities, explains them in plain language, delivers via Telegram.

### Project structure

```
src/prospecting/     Lead generation pipeline (Phase 0)
src/worker/          Docker scan worker (BRPOP loop, enrichment, scan execution)
src/scheduler/       Job scheduler daemon (operator commands + daily CT monitoring timer)
src/client_memory/   Client state + Sentinel CT monitoring (CertSpotter polling, diff, alerts)
.claude/agents/      Agent specs + agent-owned data (12 agents)
config/              Static configuration (JSON)
data/input/          Manual input (CVR extracts)
data/output/         Pipeline results (briefs, CSV)
docs/                Briefing, business plan, legal, architecture
infra/compose/       Docker Compose, Dockerfiles, Prometheus, Grafana
scripts/             Benchmark, analysis, and utility scripts
tests/               pytest test suite (217 tests)
```

### Docker deployment (Pi5)

```bash
# Build and start the full stack (scheduler, 3 workers, Redis, ct-collector, monitoring)
docker compose -f infra/compose/docker-compose.yml -f infra/compose/docker-compose.monitoring.yml up -d --build

# Analyze results after a run completes
docker exec docker-worker-1 python scripts/analyze_results.py /data/results/prospect

# Run with warm cache (skip enrichment phase)
docker compose run scheduler --mode prospect --confirmed --skip-enrichment

# One-time CT backfill (run before first deploy, with ct-collector stopped)
docker compose --profile backfill run --rm ct-backfill
```

**Monitoring endpoints:**
- Dozzle (live logs): `http://<pi5-ip>:8080`
- Grafana (dashboards): `http://<pi5-ip>:3000`
- Prometheus (metrics): `http://<pi5-ip>:9090`

### Local development (laptop)

```bash
# Install dependencies
pip install -r requirements.txt

# Install Go scanning tools
go install github.com/projectdiscovery/httpx/cmd/httpx@latest
go install github.com/rverton/webanalyze/cmd/webanalyze@latest
go install github.com/projectdiscovery/subfinder/v2/cmd/subfinder@latest
go install github.com/projectdiscovery/dnsx/cmd/dnsx@latest

# Run (requires CVR-extract.xlsx in data/input/)
python -m src.prospecting.main --confirmed

# With JSON logging
python -m src.prospecting.main --confirmed --log-format json

# Skip scanning (test ingestion only)
python -m src.prospecting.main --skip-scan
```

### Run tests

```bash
python -m pytest              # 217 tests
python -m pytest --cov=src    # with coverage
```

### Run benchmarks

```bash
python scripts/benchmark.py --mock --domains 5    # mock mode (no network)
python scripts/benchmark.py --domains 20           # real scan
```

### Performance

204 domains (Vejle municipality), Pi5 with 3 workers:

| Phase | Time |
|-------|------|
| Subfinder enrichment | 5.5 min (3 parallel batches) |
| Core scan (warm cache) | 3.0 min |
| **Total** | **~8.5 min** |

100% cache hit rate on subsequent runs. 9x improvement over initial sequential approach.

### Environment variables

Copy `.env.example` to `.env`:

```bash
GRAYHATWARFARE_API_KEY=          # Optional — cloud storage exposure search
ENRICHMENT_WORKERS=3             # Number of subfinder batch workers (default: 3)
CERTSPOTTER_API_KEY=             # Optional — Sentinel-tier CT monitoring (free tier OK)
```
