# Heimdall Mobile Console — Design Spec

**Date:** 2026-03-28
**Status:** Approved for implementation

## Problem

Federico needs two mobile capabilities:
1. Monitor Heimdall's scan pipeline on the go (queue depth, recent results, errors) — read-only
2. Demo a live scan to prospective clients during in-person sales meetings — scanning a digital twin we own, with Hollywood-style animated findings reveal

No mobile interface exists today. The operator must be at the laptop to see pipeline status, and there is no visual demo tool for client meetings.

## Solution

A Progressive Web App (PWA) served by the existing FastAPI backend, installable on iPhone and iPad. Two modes: **Monitor** and **Demo**.

### Monitor Mode
Single-scroll dashboard that auto-refreshes every 5 seconds via polling:
- Queue depths (scan, enrichment, wpscan) with color indicators
- Recent scans list (domain, findings count, severity, duration, date)
- Cache key count
- Enrichment progress
- Responsive: single-column on iPhone, two-column on iPad

### Demo Mode
Full-screen Hollywood animation for client meetings:
1. **Brief selector** — grid of available prospects (from pre-computed briefs)
2. **Scan progress** — vertical timeline, each scan type animates from pending to complete
3. **Tech stack reveal** — technology badges stagger-animate in
4. **Findings reveal** — cards slide up one by one with severity colors and typewriter risk text
5. **Summary** — total findings, scan duration, Heimdall branding

The demo data comes from the pre-computed brief JSON (real scan data, theatrically presented). The digital twin can run alongside for legitimacy. Total demo duration: ~25-35 seconds.

## Architecture

- **Frontend:** Vanilla HTML/CSS/JS (no framework, no build step)
- **Backend:** FastAPI console router + demo orchestrator
- **Transport:** Polling for monitor, WebSocket for demo
- **Demo pacing:** Server-controlled — orchestrator publishes events with timing delays, frontend animates what arrives

### New endpoints
- `GET /console/status` — monitor data (Redis queries + ResultStore)
- `GET /console/briefs` — list available prospect briefs
- `POST /console/demo/start` — launch replay, returns scan_id
- `WS /console/demo/ws/{scan_id}` — real-time demo event stream

### WebSocket event types
- `phase` — twin_starting, scanning
- `scan_start` / `scan_complete` — per scan type with label and timing
- `tech_reveal` — technology stack array
- `finding` — individual finding with severity, description, risk
- `complete` — summary with total findings count

## Visual Design

- Dark theme: `#0a0a0a` background
- Green accent: `#00ff88` (security/terminal aesthetic)
- Severity colors: red (high), orange (medium), yellow (low), blue (info)
- CSS-only animations: slide-up, pulse, typewriter, badge-pop
- PWA standalone mode (no Safari chrome)

## Files

### New (7)
| File | Purpose |
|------|---------|
| `src/api/console.py` | Console API router (~200 lines) |
| `src/api/demo_orchestrator.py` | Replay orchestrator (~150 lines) |
| `src/api/static/index.html` | PWA shell (~120 lines) |
| `src/api/static/manifest.json` | PWA manifest (~20 lines) |
| `src/api/static/sw.js` | Service worker (~30 lines) |
| `src/api/static/css/main.css` | All styles + animations (~400 lines) |
| `src/api/static/js/app.js` | All client logic (~350 lines) |

### Modified (3)
| File | Change |
|------|--------|
| `src/api/app.py` | Add static mount + console router (~10 lines) |
| `infra/docker/docker-compose.yml` | Briefs volume + port on api service |
| `infra/docker/Dockerfile.api` | Copy static directory |

### Tests (1)
| File | Coverage |
|------|----------|
| `tests/test_console.py` | Status endpoint, briefs list, demo start, event sequence, WebSocket |

## Scope Boundary

**In scope:** Monitor dashboard (read-only) + Hollywood demo (replay mode) + PWA shell

**Out of scope (future iterations):**
- Live scanner integration against twin during demo
- Settings changes from mobile
- Push notifications
- Multi-user auth / operator login
- Container health monitoring (simplified for Phase 0)
