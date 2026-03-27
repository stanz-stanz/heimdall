# Decision Log

Running record of architectural decisions, rejections, and reasoning made during Claude Code sessions.

---
<!-- Entries added by /wrap-up. Format: ## YYYY-MM-DD — [topic] -->

## 2026-03-27 — Tiered enrichment: subfinder batch + local CT database + observability

**Decided**
- Subfinder batch pre-scan: two-phase scheduler (enrichment → scan), 3 parallel batches of 68 domains, Redis atomic counter for completion signaling
- Local CertStream CT database replaces remote crt.sh API: SQLite WAL mode on NVMe, `immutable=1` for readers, ct-collector Docker container
- cAdvisor replaced with Docker built-in Prometheus metrics endpoint (cAdvisor incompatible with Pi OS containerd snapshotter)
- Docker-expert agent reviews mandatory before merge (both branches reviewed, 9 findings fixed per branch)
- Prometheus retention: 30 days or 2GB whichever first
- Worker `stop_grace_period: 330s` (5 min subfinder + 20s stagger + 30s buffer)
- `ENRICHMENT_WORKERS` configurable via env var, not hardcoded
- Subfinder CLI flags: `-t 10` (threads) and `-max-time 3` (min/domain) to cap memory within 1GB container budget

**Rejected**
- cAdvisor for container metrics — incompatible with Pi OS overlayfs/containerd snapshotter
- Worker `depends_on: ct-collector` — .dk certificates too rare in CertStream for healthcheck timing
- Hardcoded `ENRICHMENT_WORKERS=3` — made env-configurable per docker-expert review

**Unresolved**
- Subfinder found 0 subdomains — most passive sources need API keys (not blocking, pipeline works)
- CT backfill from crt.sh not yet run — one-time step before first production deploy
- cgroup memory limits not supported on Pi OS kernel — `cgroup_enable=memory` added to cmdline.txt but container memory limits still show warnings
- Grafana dashboard needs customization for Heimdall-specific panels

---

## 2026-03-26 — Session wrap-up: tooling, pipeline enrichment, GDPR redesign, project restructure

**Decided**
- Integrate 4 new Level 0 tools: subfinder (subdomain enumeration), dnsx (DNS enrichment), crt.sh (CT log queries), GrayHatWarfare (exposed cloud storage index)
- Valdí classification: GrayHatWarfare → Layer 1 (third-party index), CloudEnum → Layer 2 (active enumeration)
- Add 5 Level 1 tools to SCANNING_RULES.md: CMSeek, Katana, FeroxBuster, SecretFinder, CloudEnum (not registered — no approval tokens until Level 1 pipeline is built)
- Replace flat `sales_hook` with structured `findings` array: severity (industry-standard), description, risk
- Evidence-based GDPR determination from scan results (plugins, tracking, e-commerce) replaces industry-code-only approach
- WPScan commercial API: flag as cost to investigate with Automattic, add to COGS in SIRI financials
- Three-phase project restructure: `pipeline/` → `src/prospecting/`, `docs/agents/` → `agents/`, docs reorganised

**Rejected**
- Flat per-event remediation pricing (Model A) — too rigid for variable-complexity work
- Bundled remediation credits (Model C) — premature before pilot validation
- Code-lives-with-agent structure (Option A) — awkward Python imports

**Unresolved**
- WPScan commercial API pricing (need quote from Automattic)
- crt.sh rate limiting (429s at 1s delay — increase to 2-3s)
- Hardcoded config values in config.py need extracting to `config/*.json` files (planned follow-up)
- Agent SKILL.md files have stale path references (data/prospects/, docs/Heimdall_Business_Case_v2.md)
- CLAUDE.md Scanning Workflow section still references `pipeline.main`
- Video pitch script (mandatory for SIRI) deferred
- Valdí forensic logs missing for the 4 new scan types (approval tokens reference files that don't exist yet)

---

## 2026-03-25 — Session wrap-up: SIRI pivot + pricing + remediation service

**Decided**
- Pricing finalized at aggressive tiers: Watchman 199 / Sentinel 399 / Guardian 799 kr./mo (annual: 599). All excl. moms. Source: Heimdall_Investor_Plan_v1_angel.docx (the manually maintained .docx had the final pricing, not the .md)
- Optional per-event remediation service added to all tiers: 599 kr. first hour, 399 kr./hr additional (reference pricing, subject to pilot adjustment, excl. moms). Model B — hourly with minimum
- Remediation service positioned as 4th durable differentiator: neither Intruder.io nor HostedScan offers hands-on fixes

**Rejected**
- Model A (flat per-event pricing) — too rigid for variable-complexity work
- Model C (bundled credits / unlimited add-on) — premature before pilot validation
- Premium pricing (499/799/1,199) — superseded by aggressive pricing strategy in .docx

**Unresolved**
- Video pitch script (mandatory 5-min for SIRI) — deferred to separate session
- Specific remediation pricing needs pilot validation
- CLAUDE.md Build Priority section has stale references that need cleanup

---

## 2026-03-25 — Pivot business documents from angel investor to Startup Denmark (SIRI) audience

**Context:** Federico is Argentinian, currently in Denmark on a Fast-Track employment scheme (Senior SAP Engineer at LEGO). The project was originally targeting angel investors and the NCC-DK grant pool. However, NCC-DK requires a CVR (Danish company registration), and Federico does not have one. The Startup Denmark program provides a path: a work/residence permit for non-EU founders to establish a company in Denmark — which then provides the CVR needed for grants.

**Decision:** Reframe all business case documents from "angel investor pitch" to "Startup Denmark residence permit application." The technical product is unchanged. The business case is reframed around SIRI's four scoring criteria: Innovation, Market Potential, Scalability, Team Competencies. Expert panel scores 1–5 per criterion; minimum average 3.5 required for approval.

**Consequences:**
- `heimdall-investor-plan.md` → `heimdall-siri-application.md` (major rewrite)
- `investor-plan-outline.md` → `siri-application-outline.md` (major rewrite)
- `Heimdall_Investor_Plan.docx` archived to `docs/business/archive/`
- Grant & Funding agent scope expanded to include SIRI application as Priority 0
- NCC-DK grant becomes Phase 2 (post-CVR), not primary goal
- New mandatory sections: "Why Denmark", "Scalability & Job Creation in Denmark", "Innovation"
- Sections removed: Risk Analysis, The Ask, Why Now (content folded into other sections)
- New future deliverable: 5-minute video pitch script (mandatory for SIRI submission)