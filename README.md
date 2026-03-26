<p align="center">
  <img src="/docs/images/heimdall.png?raw=true" alt="Heimdall keeps watch for invaders"/>
</p>

## An OpenClaw-Powered Cybersecurity Service for Small Businesses

External Attack Surface Management (EASM) for Danish SMBs. Finds vulnerabilities, explains them in plain language, delivers via Telegram.

### Project structure

```
src/prospecting/     Code — lead generation pipeline (Phase 0)
src/worker/          Code — Docker worker module (Sprint 2)
agents/              Agent specs + agent-owned data (12 agents)
config/              Static configuration (JSON)
data/input/          Manual input (CVR extracts)
data/output/         Pipeline results (briefs, CSV)
docs/                Briefing, business plan, legal, architecture
infra/               Docker Compose, environment templates
scripts/             Benchmark and utility scripts
tests/               pytest test suite
```

### Run the pipeline

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
python -m pytest
python -m pytest --cov=src       # with coverage
```

### Run benchmarks

```bash
python scripts/benchmark.py --mock --domains 5    # mock mode (no network)
python scripts/benchmark.py --domains 20           # real scan
```

### Environment variables

Copy `.env.example` to `.env`:

```bash
GRAYHATWARFARE_API_KEY=          # Optional — cloud storage exposure search
```
