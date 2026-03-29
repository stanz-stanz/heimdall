# Marketing Strategy Draft — Heimdall

**Status:** DRAFT — in progress, pending legal consultation
**Date:** 2026-03-29
**Author:** Federico Alvarez + Claude Code

---

## The Problem: Two Walls

### Wall 1: The Consent Wall (partially solved)

Layer 2 vulnerability scanning requires written customer consent. Without paying clients, we couldn't test or demonstrate advanced capabilities.

**Solution:** The digital twin system. By reconstructing prospect websites on our own infrastructure from Layer 1 (passive) scan data, we can run Nuclei and WPScan against our own systems. This produces CVE-level findings without requiring consent. Findings carry `provenance: "twin-derived"` markers — they are inferred from detected versions, not confirmed by direct testing.

The consent wall is not fully removed — twin-derived findings are inferences, not confirmations, and must be framed accordingly. But they are dramatically more valuable than Layer 1 surface observations alone.

### Wall 2: The Contact Barrier (unsolved)

We can scan 2,400 businesses in Vejle and produce specific findings. We cannot reach most of them.

**Danish law (Markedsføringsloven §10):** Cold email is illegal for B2B in Denmark. No exceptions. SMS too. This eliminates the primary channel used by SaaS companies worldwide.

**CVR Reklamebeskyttet:** Businesses can opt out of unsolicited marketing. This blocks use of CVR-sourced contact data for advertising. The scope and exceptions are unclear — pending legal advice.

---

## Target Customer Profile

**Who:** Danish micro-business owners with 1-19 employees. Restaurants with online booking, physiotherapists, dental clinics, barbershops, accountants, real estate agents. Vejle area for the pilot.

**Their website:** Self-built WordPress on shared hosting (one.com, simply.com), or built by a local freelancer/agency. They don't maintain it actively. They don't know what "HSTS" means.

**Where they are:** Behind a counter, on their phone, on Facebook/Instagram. NOT on LinkedIn, NOT reading cybersecurity blogs, NOT checking email for B2B pitches.

**What they respond to:** Things that are about THEIR business specifically. Not generic "cybersecurity is important" messaging. A finding about their actual website gets attention. A brochure goes in the bin.

**The market:**
- ~2,400 active businesses in Vejle with under 20 employees
- Unknown: how many have a website, how many are GDPR-sensitive, how many are Bucket A/B
- Sprint 2 run (different extract, 1,012 companies) yielded 204 live domains, 68 after filtering
- Current run in progress on Pi5 — numbers pending

---

## Channel Assessment

### Channels We Ruled Out

| Channel | Why It's Out |
|---------|-------------|
| **Cold email** | Illegal in Denmark under §10. Absolute prohibition, B2B included. No workaround. |
| **SMS** | Same prohibition as email under §10. |
| **LinkedIn (for end customers)** | Our target customers are micro-businesses (restaurants, physios, barbershops). They are not on LinkedIn. LinkedIn is irrelevant for this segment. |
| **Walk-in visits at scale** | Works for 5 prospects. Does not work for 68 or 2,400. Federico is one person. |
| **Generic cybersecurity content marketing** | Our customers don't read cybersecurity blogs. SEO for Danish cybersecurity terms is a long game with uncertain payoff for this segment. |

### Channels Under Consideration (Pending Legal Advice)

| Channel | Status | What We Need to Know |
|---------|--------|---------------------|
| **Website contact forms** | Promising | Is submitting a security notification through a business's own contact form "electronic mail" under §10? See legal briefing Q4. |
| **Physical letter to Reklamebeskyttet businesses** | Promising | Is a security notification (no pricing, no CTA) "advertising" under Reklamebeskyttet rules? See legal briefing Q3. |
| **Facebook Messenger to business pages** | Promising | Is an organic message to a business page with Messenger enabled covered by §10? See legal briefing Q6. |
| **Responsible disclosure framing** | Promising | Does framing first contact as responsible disclosure of publicly visible issues protect against §10 complaints? See legal briefing Q7. |

### Channels We Can Use Now (No Legal Ambiguity)

| Channel | Scale | Cost | Notes |
|---------|-------|------|-------|
| **Physical letter (to non-Reklamebeskyttet)** | Medium (68 Bucket A/B) | ~19 kr/letter, ~1,300 kr for 68 | Legal, personal, high open rate. One finding per letter. Phone number as CTA. |
| **Phone call (to ApS/A/S, non-Reklamebeskyttet)** | Low (labor-intensive) | Free | Legal for registered companies. Business number from their website. |
| **Facebook group post (anonymized stats)** | High | Free | "We scanned 200 Vejle business websites — 73% are missing basic security." Drives inbound curiosity. Zero legal risk. |
| **Inbound (free scan tool / landing page)** | Medium-long term | ~200 kr domain + hosting | Prospects type their domain, see results. They initiate contact. |
| **Partner referrals (accountants, agencies)** | High leverage per partner | Free | One accountant or agency = 20-50 introductions. Hard to map who serves who. |

---

## Ideas Evaluated and Parked

### The Accountant Network
**Idea:** One bogholder/revisor serves 30-50 SMBs. Approach the accountant with findings across their client base. They introduce you to their clients.

**Why parked:** Smart but hard to execute. CVR data doesn't map accountant to client. We'd need to discover these relationships manually. High leverage if we crack it, but no clear path to doing so at pilot scale.

**Revisit when:** We have a few paying clients who can refer their own accountant.

### The Insurance Partner Channel
**Idea:** Business insurers care about cybersecurity risk. Partner with a local insurance agent who already has relationships with Vejle SMBs.

**Why parked:** Too slow for the pilot. Insurance partnerships take months to formalize. The incentive alignment is also unclear — insurers might not want to surface problems in their portfolio.

**Revisit when:** Post-pilot, when Heimdall has paying clients and credibility.

### LinkedIn (for agencies)
**Idea:** Web agencies ARE on LinkedIn, even if their clients aren't. Approach agencies with aggregate findings ("22 of your 35 client sites have issues").

**Why parked:** The data from our Sprint 2 run suggests most Bucket A prospects are self-built WordPress — no identifiable agency. The agency channel may serve a smaller slice than expected. Waiting for the current Pi5 run to confirm the numbers.

**Revisit when:** Pi5 run completes and we see agency detection results. If significant agency presence, this becomes a priority channel.

### Walk-In Visits
**Idea:** You're in Vejle, they're in Vejle. Walk in with a printout.

**Why kept (limited scope):** Valid for the pilot 5 — highest-value prospects where a personal conversation matters. Not a scalable channel.

---

## What We Know

1. Cold email is dead in Denmark. Do not waste time on email tools (Clay, Instantly, Lemlist) — the channel is legally closed.
2. Our target customer (micro-business owner) is not on LinkedIn. Do not build a LinkedIn-first strategy.
3. Physical mail is the clearest legal channel for written first contact.
4. Facebook is where micro-business owners actually spend time. Local Facebook groups and business page messaging are realistic channels.
5. The "first finding free" model is strong — a specific finding about their actual website cuts through noise in a way generic marketing cannot.
6. The digital twin extends findings from surface observations to CVE-level specificity, making the "free sample" dramatically more compelling.
7. The agency channel has theoretical leverage but may not be supported by the data.

## What We Don't Know

1. Whether a security notification (no pricing, no CTA) counts as "direct marketing" under §10 — **depends on legal advice**
2. Whether Reklamebeskyttet blocks ALL unsolicited contact or only CVR-sourced contact data — **depends on legal advice**
3. Whether website contact forms are "electronic mail" under §10 — **depends on legal advice**
4. Whether Facebook business page messages are covered by the spam ban — **depends on legal advice**
5. How many of the 2,400 Vejle businesses have a website, are GDPR-sensitive, and fall into Bucket A/B — **depends on current Pi5 run**
6. How many prospects have an identifiable web agency — **depends on current Pi5 run**
7. Whether the responsible disclosure framing provides legal protection for commercial entities — **depends on legal advice**

---

## Immediate Actions

| Action | Owner | Timeline | Dependency |
|--------|-------|----------|------------|
| Complete Pi5 pipeline run | Federico | In progress | CVR extract deployed |
| Analyze pipeline output: funnel numbers, agency detection, GDPR breakdown | Federico + Claude | After run completes | Pi5 run |
| Prepare legal briefing documents for lawyer meeting | Federico | Done (this document + legal briefing) | None |
| Lawyer consultation | Federico | Week of 2026-03-31 | Legal briefing prepared |
| Draft sample security notification letter | Federico + Claude | Before lawyer meeting | Legal briefing |
| Design Facebook approach (local group post, business page messages) | Federico + Claude | After legal consultation | Legal advice on Facebook messages |
| Letter generation system (template brief → printable letter) | Claude | After legal consultation | Legal advice on letter framing |
| Select pilot 5 prospects from pipeline output | Federico | After run + legal advice | Both |

---

## Budget Allocation (Revised)

| Item | Cost | Priority |
|------|------|----------|
| Legal consultation (Plesner/Kromann Reumert) | 3,000–5,000 kr. | **Highest** — unlocks multiple channels |
| Physical mail campaign (68 letters, first wave) | ~1,300 kr. | High — after legal clears the framing |
| Domain + landing page | ~200 kr. | Medium — for inbound CTA on letters |
| Loom (free) for personalized video | 0 kr. | Test alongside letters |
| Facebook group engagement | 0 kr. | Start immediately (anonymized stats only) |
| LinkedIn Sales Navigator (for agency channel only) | ~700 kr./mo | Only if agency data supports it |
| **Total immediate** | **~5,000–7,000 kr.** | |

The legal consultation is the highest-leverage spend. Every answer from counsel either opens or closes a channel. Everything downstream depends on it.
