# Backlog

Organised by sprint. Each sprint groups items by track: **Product** (code/pipeline), **SIRI** (application materials), **Housekeeping** (cleanup, process, infra).

Status: `[ ]` pending · `[~]` in progress · `[x]` done

---

## Sprint 1 — Consolidate & Ship (current)

Close out the feature branch. Everything needed to merge and have a clean baseline.

### Product
- [ ] Merge `feature/siri-pivot` to `main` (squash or rebase to clean history)
- [ ] Create `.env.example` documenting `GRAYHATWARFARE_API_KEY`

### SIRI
- [ ] Video pitch script — mandatory 5-min video for Startup Denmark submission (structure in `docs/business/siri-application-outline.md`)

### Housekeeping
- [ ] Clean git history on feature branch (revert commit sandwiched between two config extraction commits)
- [ ] Update `README.md` with new project structure and run instructions (`python -m src.prospecting.main`)

---

## Sprint 2 — Pipeline Hardening

Make the pipeline production-ready for a full Vejle run (all 68 targets, not just the 4 restaurant filter).

### Product
- [ ] Widen filters for full Vejle run (currently filtering to industry code 561110 only)
- [ ] WPScan commercial API — contact Automattic for pricing, evaluate for Level 1
- [ ] Rate limiting / throttling for crt.sh (currently 2s, may need adaptive backoff)
- [ ] Error handling review — what happens when a tool hangs mid-batch?
- [ ] Pipeline output summary: per-finding severity breakdown, top-N hooks
- [ ] Marketing sub-agent — translate technical findings (severity/description/risk) into business-impact language for the sales conversation

### SIRI
- [ ] Finalise SIRI application content based on pilot data from full Vejle run
- [ ] Generate SIRI pitch deck (10-page PDF from `heimdall-siri-application.md`)

### Housekeeping
- [ ] SSLyze AGPL review — confirm unmodified use is safe for our commercial model
- [ ] Nikto DB licensing — assess whether we need a CIRT.net commercial license
- [ ] Document all tool licenses in a single reference file

---

## Sprint 3 — Level 1 Pipeline (Consent-Gated Scanning)

Build the paid-service scanning pipeline. Requires written client consent (Level 1).

### Product
- [ ] Level 1 scanning module (`src/scanning/`) — Nuclei, WPScan, Nmap, CMSeek
- [ ] Consent management — client authorization template, consent registry in `agents/valdi/`
- [ ] Layer 2 tools integration: Katana, FeroxBuster, SecretFinder, CloudEnum
- [ ] Finding Interpreter agent — Claude API translation of raw scan results
- [ ] Message Composer agent — format findings for Telegram/WhatsApp delivery
- [ ] Client Memory agent — persistent per-client state, scan history, remediation tracking
- [ ] Remediation service workflow — per-event billing, fix execution, verification

### SIRI
- [ ] Update SIRI application with pilot results and Level 1 capabilities

### Housekeeping
- [ ] Valdí Gate 1 approval for all Level 1 scan types
- [ ] Scanning authorization template — draft for legal counsel review
- [ ] Infrastructure plan — move from laptop to dedicated scanning infrastructure

---

## Sprint 4 — Pilot Launch (Vejle, 5 clients)

First paying clients. Human-in-the-loop for every message.

### Product
- [ ] Telegram bot setup and delivery pipeline
- [ ] Human-in-the-loop review workflow (Federico approves every message before send)
- [ ] Escalating follow-up system (week 1/2/3)
- [ ] Remediation service: first real fix event
- [ ] Client onboarding flow

### SIRI
- [ ] Submit Startup Denmark application
- [ ] Record 5-min video pitch

### Housekeeping
- [ ] Professional indemnity insurance
- [ ] Legal counsel engagement (§263 confirmation, authorization template)
- [ ] Domain + landing page

---

## Parking Lot

Items with no sprint assignment yet.

- [ ] Agency detection improvements — better footer/meta parsing
- [ ] Agency pitch workflow — aggregate scan data per agency
- [ ] GrayHatWarfare premium subscription (~230 EUR/yr) — evaluate after pilot
- [ ] EU expansion research — Germany/Netherlands market sizing
- [ ] NCC-DK grant application (post-CVR, post Startup Denmark approval)
- [ ] Quarterly security report template (Guardian tier)
- [ ] Dashboard-vs-Telegram visual mockup for SIRI pitch deck
