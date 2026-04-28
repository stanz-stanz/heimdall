# Heimdall Toolset Broadening Plan

**Owner:** Product / Architecture
**Last updated:** 2026-04-28
**Purpose:** Define how Heimdall should broaden its scanning toolset without diluting product quality, operator trust, or ICP focus

---

## Executive summary

Heimdall should broaden its toolset selectively, not aggressively.

The rule is simple:

`Add tools only when they improve decision quality per finding, not finding count per domain.`

That means new tools must help at least one of these:

- improve operator prioritization
- improve remediation usefulness
- improve customer trust and explainability
- improve fit for the chosen ICP
- improve recurring monitoring value

Tool broadening is therefore a product decision, not a scanner-collector hobby.

---

## Broadening principles

Every proposed tool or enrichment source should be evaluated against these questions:

1. Does it produce findings that an operator can act on?
2. Does it reduce uncertainty, or merely add more surface area?
3. Does it fit the current ICP?
4. Does it improve an existing workflow, or create a new orphaned one?
5. Can Heimdall explain the result in plain business language?
6. Can the finding be normalized into Heimdall’s existing evidence and severity model?

If the answer to most of these is “no,” the tool should not be added.

---

## The six broadening priorities

## 1. WordPress vulnerability intelligence enrichment

### What it is

This is not another WordPress detector. Heimdall already has meaningful WordPress-related detection. The value is in deeper version-to-risk mapping:

- plugin vulnerability matching
- theme vulnerability matching
- WordPress core version risk mapping
- exploitability or KEV-style tagging where possible

### Why it matters

WordPress remains one of Heimdall’s strongest exposure surfaces:

- common in SMB websites
- frequently outdated
- relatively legible to operators and customers
- high leverage for prioritization

The real improvement is not “detect more WordPress things.” It is:

- distinguish cosmetic from urgent
- link detected versions to known issues
- make remediation advice much more concrete

### Why this is high priority

This broadening directly improves:

- finding quality
- triage quality
- customer credibility
- remediation guidance

### Risks

- poor plugin/theme normalization creates false matches
- incomplete version confidence creates noisy severity claims
- over-weighting WordPress can distort broader product strategy

### Right approach

- strengthen slug normalization first
- separate “version observed directly” from “version inferred”
- tag confidence explicitly
- connect results to remediation playbooks, not just CVE names

### Priority

`Highest`

---

## 2. Email and domain trust posture

### What it is

Focused analysis of externally visible mail/domain hygiene:

- SPF
- DKIM
- DMARC
- MX posture
- obvious anti-spoofing gaps

### Why it matters

This is strong for SMB because it maps well to business concerns:

- trust
- impersonation risk
- brand harm
- customer communication integrity

It is easier to explain than many purely technical web findings.

### Why this is high value

This broadening aligns well with Heimdall’s likely service positioning:

- “protect your external trust surface”
- not just “scan your website”

It also broadens beyond WordPress without becoming generic enterprise ASM.

### Risks

- oversimplified email posture grading can mislead
- customers may assume deliverability consulting is included
- some findings may be low urgency unless framed carefully

### Right approach

- keep scope narrow and externally observable
- score for trust/abuse relevance, not RFC perfection
- explain business impact simply
- avoid turning this into a full mail security product

### Priority

`Very high`

---

## 3. Cloud and storage exposure validation

### What it is

Deeper classification of publicly exposed cloud/storage findings:

- bucket/container type
- listing exposure vs object-read exposure
- probable sensitivity / business impact
- recurrence over time

### Why it matters

Exposed storage is highly legible and often materially serious.

It fits Heimdall because:

- it is externally observable
- it often yields strong, understandable findings
- it supports trust/compliance narratives

### Why this is high value

When real, storage exposure is the kind of finding that:

- gets operator attention
- gets customer attention
- justifies monitoring value

### Risks

- false positives from naming collisions or stale references
- overclaiming sensitivity without evidence
- legal caution if validation becomes too active

### Right approach

- emphasize classification and confidence
- separate “exposed index” from “sensitive data likely exposed”
- keep validation within policy boundaries
- connect to plain-language remediation advice

### Priority

`High`

---

## 4. JavaScript and frontend dependency fingerprinting

### What it is

Detection of client-side frameworks and library versions where visible:

- JavaScript packages
- frontend frameworks
- public asset version clues

### Why it matters

Heimdall is stronger today on:

- TLS
- headers
- CMS
- plugins
- DNS
- certs

It is weaker on modern frontend stack exposure. This fills a real gap, especially for:

- e-commerce
- brochureware sites
- SaaS-like SMB web properties

### Why this is valuable

It broadens coverage into modern websites without immediately requiring invasive active scanning.

### Risks

- huge noise potential
- client-side package sprawl may swamp operators
- weak version confidence can turn this into vanity telemetry

### Right approach

- only keep findings that affect decision quality
- normalize aggressively
- suppress low-confidence detections
- prioritize severe, widely exploitable, or recurrent library issues

### Priority

`Medium-high`

---

## 5. Better normalized service exposure analysis

### What it is

Not “more Nmap.” The goal is better productization of internet-exposed services:

- remote admin surfaces
- management interfaces
- old web services
- weakly protected panels
- externally exposed operational endpoints

### Why it matters

This can produce some of the most actionable findings in Heimdall:

- obvious exposure
- strong operator follow-up path
- strong business explanation

### Why this is not even higher

The signal can be excellent, but the operational and legal risk is higher because deeper service analysis tends to lean more active.

### Risks

- consent and policy requirements become stricter
- scanning aggressiveness can create noise or compliance problems
- service-level findings can be harder to standardize than website findings

### Right approach

- keep this behind clear consent / tier gates
- focus on high-value exposed services, not broad enumeration for its own sake
- normalize exposures into product-level categories
- make sure each exposure type maps to an operator playbook

### Priority

`Medium`

---

## 6. TLS posture enrichment

### What it is

Heimdall already gathers TLS/certificate data. The broadening here is not another TLS scanner, but stronger interpretation:

- expiry risk
- weak protocol/cipher relevance
- hostname mismatch significance
- cert-change anomaly interpretation

### Why it matters

This compounds with current certificate and CT monitoring capability.

It is especially useful in recurring monitoring:

- changes over time
- risky drift
- operational surprises

### Why it is lower priority

The current TLS layer is already decent. The value here is incremental and interpretive, not transformational.

### Risks

- easy to overproduce low-value findings
- many TLS posture issues are hard to monetize directly
- can distract from higher-impact workflow improvements

### Right approach

- tie every TLS issue to clear customer impact
- emphasize recurring-monitoring value over one-off severity theater
- avoid noisy “best practice” warnings unless they matter

### Priority

`Medium-low`

---

## Ranked priority stack

If Heimdall broadens the toolset in phases, the order should be:

1. WordPress vulnerability intelligence enrichment
2. Email and domain trust posture
3. Cloud and storage exposure validation
4. JavaScript and frontend dependency fingerprinting
5. Better normalized service exposure analysis
6. TLS posture enrichment

---

## Why this order

### 1. WordPress vulnerability intelligence enrichment

Best near-term leverage because it deepens an area Heimdall already touches and can improve prioritization immediately.

### 2. Email and domain trust posture

Strong commercial fit, strong explainability, good trust narrative, and not overly dependent on risky active scanning.

### 3. Cloud and storage exposure validation

Potentially high-severity, highly legible findings with strong business impact.

### 4. JavaScript and frontend dependency fingerprinting

A useful coverage expansion, but only if normalized carefully to avoid noise.

### 5. Better normalized service exposure

Powerful, but should remain tightly governed and consent-aware.

### 6. TLS posture enrichment

Worth doing, but mainly as improved interpretation once higher-impact additions are handled.

---

## What Heimdall should avoid

### Avoid 1: Broad CVE feed ingestion without strong normalization

This usually creates:

- noisy results
- weak severity confidence
- poor operator trust

### Avoid 2: Overlapping tech fingerprint tools

More fingerprints do not automatically improve product value. They often create de-duplication and interpretation burden.

### Avoid 3: Heavy active web vulnerability scanning in broad prospecting

This increases:

- policy complexity
- legal complexity
- operational cost

without necessarily improving commercial outcomes.

### Avoid 4: Tool additions that do not map to remediation

If the operator cannot answer “what do we do next?” the finding is low-value by default.

### Avoid 5: Expanding tools before normalizing outputs

Broadening without a stronger evidence-normalization layer will compound inconsistency and noise.

---

## The right implementation approach

Tool broadening should happen through four layers:

### Layer 1: Evidence acquisition

Run or integrate the tool/source.

### Layer 2: Evidence normalization

Convert raw tool output into Heimdall-native evidence types:

- software/version
- trust posture
- exposed asset
- service exposure
- certificate state

### Layer 3: Product interpretation

Translate evidence into:

- risk significance
- confidence
- business impact
- operator actionability

### Layer 4: Workflow integration

Make the result useful in:

- queues
- briefs
- remediation playbooks
- customer reporting
- recurring monitoring

Heimdall should not adopt any tool that cannot move through all four layers cleanly.

---

## Expansion gates

A new tool or enrichment source should only ship if it passes these gates:

### Gate A: Signal quality

- produces findings above a minimum severity or trust threshold
- does not flood the operator with low-value output

### Gate B: ICP relevance

- matters to the chosen ICP now
- not just theoretically useful someday

### Gate C: Workflow fit

- maps to operator action
- maps to remediation guidance
- maps to customer communication

### Gate D: Policy and operational fit

- acceptable within Heimdall’s scanning/compliance model
- acceptable cost and runtime profile

### Gate E: Explainability

- can be explained in plain language without hand-waving

---

## Recommended execution phases

### Phase 1

- WordPress vulnerability intelligence enrichment
- Email and domain trust posture

These are the best balance of:

- current fit
- customer explainability
- product value
- manageable implementation risk

### Phase 2

- Cloud and storage exposure validation
- JavaScript and frontend dependency fingerprinting

These broaden Heimdall’s coverage meaningfully once normalization discipline is stronger.

### Phase 3

- Better normalized service exposure analysis
- TLS posture enrichment

These add value, but they should not come before stronger workflow and evidence normalization.

---

## Success metrics

Tool broadening is successful only if it improves product outcomes. Use these checks:

- higher operator confidence in severity/prioritization
- lower ratio of ignored findings
- higher ratio of findings with clear remediation path
- better customer comprehension of findings
- better ICP-specific relevance
- no material increase in operator noise burden

If a new tool increases output but not these outcomes, it failed.

---

## Bottom line

Heimdall should broaden the toolset where it sharpens the product, not where it merely expands the scanner collection.

The best broadening path is:

- deepen WordPress vulnerability intelligence
- add email/domain trust posture
- improve cloud/storage exposure classification
- then broaden into frontend and service surfaces only as normalization and workflow maturity allow

That is the right approach if the goal is to make Heimdall more valuable, more trustworthy, and more defensible.

