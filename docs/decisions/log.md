# Decision Log

Running record of architectural decisions, rejections, and reasoning made during Claude Code sessions.

---
<!-- Entries added by /wrap-up. Format: ## YYYY-MM-DD — [topic] -->

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