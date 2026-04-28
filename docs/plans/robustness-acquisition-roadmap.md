# Heimdall Robustness and Acquisition Roadmap

**Owner:** Product / Architecture
**Last updated:** 2026-04-28
**Horizon:** 12 months
**Primary goal:** Move Heimdall from promising early system to robust, acquirable SMB cyber operations product

---

## Executive framing

This plan is not a generic feature roadmap. It is a wrapper around one strategic outcome:

`Make Heimdall robust enough to be trusted as an SMB external-risk operations layer, and legible enough to be attractive to larger cybersecurity platforms as an acquisition target.`

The acquisition thesis is:

- Heimdall is **not** “another scanner”
- Heimdall is **not** “just an admin console”
- Heimdall is a **secure operator control plane + external exposure monitoring + remediation workflow engine for SMB**

That is the wedge that can matter to:

- MDR / MSSP platforms that underserve SMB
- EASM / ASM vendors that are weak on workflow and remediation follow-through
- compliance / trust platforms that need real external-risk signal
- channel-oriented security companies that want an SMB operating layer

---

## What “robust” means

Heimdall reaches `robust` status when all five are true:

1. The operator control plane is secure enough that it is not itself a major risk.
2. Detection, triage, notification, remediation tracking, and retention run as one coherent workflow.
3. Findings are prioritized well enough that operators and customers trust the system’s judgment.
4. Delivery is repeatable for one narrow ICP without heroic manual effort.
5. The product surface, data model, and operating logic are understandable to an acquirer and easy to integrate.

---

## Target state after 12 months

At the end of this roadmap, Heimdall should be describable as:

`A secure operations layer for SMB external exposure that continuously monitors public attack surface, explains what matters, and drives operator-guided remediation through an auditable control plane.`

That is the acquisition-facing narrative.

---

## Q1: Foundation and trust

**Goal:** Eliminate obvious control-plane weakness and make one operator workflow safe and repeatable.

### Build

- Land Stage A and Stage A.5 foundations:
  - operator identity
  - secure session model
  - websocket auth gate
  - auditability
  - request tracing
  - permission model appropriate to current team size
- Harden login and session controls:
  - brute-force protection
  - reliable operator disable / recovery flow
  - robust cookie/session semantics
- Build the first coherent operator loop:
  - detect
  - triage
  - notify
  - track
  - close
- Define one narrow ICP package and keep all workflow tuning aimed at that ICP.
- Convert the console from “pages” to “one place operators can work from” for at least one real flow.

### Product outcome

- Heimdall becomes safe enough to operate seriously.
- The operator console stops being a security liability.
- One narrow service can be delivered with discipline.

### Buyer / acquirer signal

- The team understands control-plane security.
- The console is not a toy internal panel.
- The product can be trusted with operator actions and customer state.

### KPIs

- 100% of state-changing operator actions are auditable.
- 0 known unauthenticated operator-console paths.
- 1 complete production-grade operator workflow in daily use.
- Mean time from detection to first operator action is measurable.
- Mean time from operator action to customer notification is measurable.

### Exit criteria

- Major auth / session / websocket / audit gaps are closed.
- One client workspace flow is usable end to end.
- One queue-based operator workflow exists and is stable.
- ICP definition is fixed enough that product tuning is not diffuse.

---

## Q2: Workflow and repeatability

**Goal:** Turn Heimdall from a secure prototype into a repeatable operating system.

### Build

- Introduce the unified operator work queue:
  - new critical findings
  - delivery failures
  - retention failures
  - trial / onboarding exceptions
  - unresolved client-change events
- Build a real per-client workspace:
  - overview
  - findings
  - scan history
  - message history
  - remediation status
  - subscription / trial state
  - audit trail
- Separate notifications into their own proper operating domain.
- Add findings lifecycle controls:
  - acknowledge
  - assign
  - suppress
  - snooze
  - resolve / reopen
- Standardize customer delivery for the chosen ICP:
  - cadence
  - message shape
  - evidence standard
  - remediation follow-up

### Product outcome

- Operators work from one queue instead of isolated views.
- Customers experience a consistent service, not ad hoc outreach.
- Heimdall starts to look like a workflow product, not just a detection stack.

### Buyer / acquirer signal

- This can plug into a larger SOC / MDR / partner workflow.
- The value is not raw findings count; it is operational follow-through.
- The platform has the beginnings of durable customer operations data.

### KPIs

- 80%+ of operator work starts from the queue, not direct page hunting.
- 100% of high-severity findings enter an explicit lifecycle state.
- Mean time to notification and mean time to closure are reported per week.
- False-positive / low-value finding rate is trending down for the chosen ICP.
- At least one standardized monthly customer review package exists.

### Exit criteria

- Unified work queue is the default operator surface.
- Client workspace is the primary navigation object.
- Notifications are no longer embedded informally across unrelated modules.
- Findings lifecycle is explicit and queryable.

---

## Q3: ICP depth and intelligence

**Goal:** Build differentiated value for one segment instead of broad generic coverage.

### Build

- Tune detection and prioritization for the chosen ICP:
  - reduce noise
  - improve severity relevance
  - add clearer business-language explanations
- Build ICP-specific remediation playbooks:
  - common stack issues
  - expected owners
  - standard fixes
  - escalation paths
- Turn scan history into usable intelligence:
  - what changed
  - what recurred
  - what was fixed
  - what remained ignored
- Add health / outcome analytics:
  - remediation latency
  - recurrence rate
  - customer responsiveness
  - conversion / retention predictors
- Strengthen delivery/reporting around business continuity and trust, not technical novelty.

### Product outcome

- Heimdall becomes noticeably better for one ICP than a generic external scanner.
- Operators act with more confidence and less manual interpretation overhead.
- Customer conversations become grounded in historical evidence, not just current snapshots.

### Buyer / acquirer signal

- There is real verticalized product knowledge here.
- The company is accumulating an operations dataset that improves the product.
- This is harder to clone than a scanning pipeline alone.

### KPIs

- Lower noise rate for the chosen ICP quarter over quarter.
- Recurring exposure patterns are measurable across customers.
- Remediation completion rate is measurable and improving.
- At least 3 ICP-specific playbooks are used operationally.
- Customer-facing reports explain deltas, not just current-state findings.

### Exit criteria

- Heimdall has one clear “best-fit” segment where it is stronger than generic tools.
- Historical intelligence is visible in operator workflow and customer output.
- The product is beginning to compound with use.

---

## Q4: Platform legibility and acquirer readiness

**Goal:** Make Heimdall easy to understand, trust, and integrate for a larger buyer.

### Build

- Clean integration surfaces:
  - exportable findings state
  - client state
  - notification state
  - remediation state
  - audit stream
- Stabilize domain boundaries and document them clearly.
- Make partner / channel mode possible if it proves commercially useful:
  - MSP / agency workflow support
  - delegated visibility
  - branded or partner-safe reporting
- Build robust governance documentation:
  - data model
  - audit model
  - operator controls
  - retention model
  - integration map
- Package the product and story for diligence:
  - architecture narrative
  - ICP narrative
  - workflow narrative
  - evidence of repeatable outcomes

### Product outcome

- Heimdall is not just useful; it is understandable as a platform asset.
- The company can demonstrate clean architecture and repeatable value.
- Integration cost for a larger buyer looks manageable.

### Buyer / acquirer signal

- This could slot into a broader cyber platform without a rewrite.
- The team has real architectural discipline.
- The product owns an SMB workflow surface that complements larger platforms.

### KPIs

- Core domains documented and stable.
- Key product entities exportable through stable APIs or reports.
- One partner-ready operating mode validated or consciously rejected.
- Diligence packet exists and is current.

### Exit criteria

- Heimdall can be pitched credibly as an SMB external-risk operations layer.
- Product, data, and workflow boundaries are legible to a third party.
- The roadmap has produced defensibility, not just more features.

---

## Quarter-by-quarter priority stack

If priorities must be compressed, use this order:

### Q1 priorities

1. Control-plane hardening
2. One queue-backed operator workflow
3. One narrow ICP focus

### Q2 priorities

1. Unified work queue
2. Client workspace
3. Findings lifecycle
4. Notifications separation

### Q3 priorities

1. ICP-specific prioritization
2. Historical intelligence
3. Remediation playbooks

### Q4 priorities

1. Integration surfaces
2. Partner / channel readiness
3. Acquisition-facing packaging

---

## Robustness milestones

The roadmap should be judged against these milestone labels:

### Milestone A: Safe

- Console auth/session/websocket model is sound
- Operator actions are auditable
- Recovery flows exist

Target: end of Q1

### Milestone B: Repeatable

- Operators can work from one queue
- Customers receive a consistent service
- Findings lifecycle is explicit

Target: end of Q2

### Milestone C: Differentiated

- One ICP is clearly better served than by generic tools
- Historical operations improve product output

Target: end of Q3

### Milestone D: Acquirable

- Product boundaries are clear
- Workflow value is demonstrable
- Integration and diligence story is credible

Target: end of Q4

---

## Acquisition narrative

At the end of this plan, Heimdall should be sellable to a larger cyber buyer as one or more of:

- an `SMB external-risk operations layer`
- a `remediation workflow engine for underserved SMB security`
- a `verticalized SMB exposure-intelligence and service platform`

The preferred wrapper is the first:

`Heimdall gives larger security platforms a secure, operator-friendly SMB layer for external exposure monitoring and guided remediation.`

That is stronger than positioning the company as a scanning vendor.

---

## False moats to avoid

Do not mistake these for defensibility:

- adding more scanners without improving actionability
- broadening to “all SMBs” before one ICP works
- maximizing finding volume instead of operator usefulness
- building heavyweight platform abstractions before workflows are proven
- treating the operator console as a forever-internal tool

---

## Immediate next actions

1. Finish the Stage A / A.5 control-plane path without security debt carry-forward.
2. Define the primary ICP in one sentence and lock it for the next quarter.
3. Identify the single operator workflow that becomes the Q1 proof loop.
4. Instrument the system so Q1 produces baseline timing and outcome metrics.
5. Keep every new feature tied to either robustness, repeatability, or acquisition legibility.

