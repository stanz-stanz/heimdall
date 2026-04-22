# Onboarding Playbook

**Purpose:** Reference playbook for Heimdall client onboarding (Watchman trial → Sentinel paid). Not a decision doc — input material for the onboarding design we do post-SIRI.
**Ingested:** 2026-04-22
**Sources digested in this doc:**
- Custify — *SaaS Customer Onboarding Guide* (Irina Vatafu, upd. 2026-04-01) — https://www.custify.com/blog/saas-customer-onboarding-guide/
- Plecto — *SaaS Onboarding* (Sage Crawford, 2026-01-01) — https://www.plecto.com/blog/customer-service/saas-onboarding/
- Rocketlane — *The Ultimate Guide to SaaS Customer Onboarding* — https://www.rocketlane.com/blogs/the-ultimate-guide-to-saas-customer-onboarding

Sections labelled **[Custify]** below form the core structure. Sections labelled **[Plecto]** / **[Rocketlane]** add only material that was *not* already in Custify and that is *relevant to Heimdall* (restaurants/physios/barbershops, Telegram-first delivery, 199/399 kr. ARPU, solo operator). Material irrelevant to our model — Forward Deployed Engineers, steering committees, POCs for large ACVs, RACI charts, linear progress bars, training phases, self-segmentation tracks for technical vs. non-technical users — has been intentionally dropped.

---

## Core thesis [Custify]

Customer onboarding is a multi-stage process that carries a new customer from sign-up to realised value. Done well it is the single biggest lever on retention, support load, and lifetime value. Done poorly, it is the single biggest cause of churn.

Anchor stats:
- **66%** of customers churn if their experience is not personalised.
- **72%** of business leaders pursue personalisation without asking customers what they want — the service gap Heimdall can exploit.
- Measuring account data alone "doubles customer lifespan and dramatically reduces churn" (ChurnRX 2023).
- **75%** of CSMs handle onboarding, adoption, renewals, and churn simultaneously — a warning for solo-operator Heimdall.

---

## Framing [Plecto]

Onboarding is an extension of delivery, not a second sales cycle. The Watchman → Sentinel transition is the same relationship continuing at a deeper scope — more of what the client already gets — not a new pitch, a new product, or a renegotiation. This matters in the Danish SMB context: a client who feels "sold to twice" will quietly revoke trust, and Janteloven makes them unlikely to say why. The first Sentinel finding should land with the same calm, analogy-driven tone as the Watchman finding that earned the relationship.

---

## Five onboarding stages [Custify]

| # | Stage | Core activity | Heimdall analogue |
|---|-------|---------------|-------------------|
| 1 | Sign Up | Three patterns: all data upfront, data after access, instant + progressive. | Watchman = instant + progressive (one free finding). Sentinel = data upfront (consent form, scope). |
| 2 | Welcome | Welcome email, onboarding survey, onboarding call. | Welcome Telegram message; Sentinel kickoff call confirming scope + escalation preferences. |
| 3 | Implementation | Account setup, desired outcomes, integrations, project management. | Sentinel: domain scoping, consent signing, Telegram bot setup, first scan scheduling. |
| 4 | First-Time User Experience | Guided quick wins, choice over forced paths, simple docs. | First interpreted finding delivered. Should land a concrete "here is something you can act on today." |
| 5 | Post-Onboarding | Health scores, follow-ups, upsell detection, QBRs. | Client memory deltas, cert-change alerts, monthly summary, Watchman → Sentinel upgrade prompt. |

---

## First Value Delivery [Rocketlane]

Treat time-to-first-value as a sequence, not a single moment. Break the onboarding path into the smallest wins we can deliver *during* onboarding, each landing before the client has time to wonder whether they should have bothered. For Watchman, the wins are: welcome message acknowledged, first passive finding delivered, finding understood (reply or "Got it" click). For Sentinel, the wins are: consent signed, scope confirmed in plain language, first scan scheduled, first interpreted alert delivered, first monthly summary. Each win is a natural check-in point; a silent step is a churn risk.

---

## Best practices that apply to Heimdall [Custify]

**Welcome stage**
- Set tone in first message — we already do (calm, analogy-driven, no jargon).
- Link to popular features with usage guides → for us: what a finding looks like, how the "Got it" button works, how escalation works.
- Simple text over flashy design. Aligns with our Telegram-first delivery.

**First-time user experience**
- "Think of customers as the main characters." Their desired outcome is *"I am not the next compromised restaurant in the news"* — not *"I have a WordPress plugin CVE."*
- Deliver a quick win in the first interaction. Watchman's free finding *is* the quick win, if the interpreter lands the business impact.
- Ask what they want; don't force a path. We already constrain to passive scanning without consent — good. But the first message could ask *what they're worried about* before the next scan.
- Work from the assumption that the single biggest churn driver is "I do not understand what I am paying for." The interpreter layer exists to close that gap — every finding must read as something a restaurant owner could explain to their business partner over coffee. If it cannot, the finding is not ready to send. [Rocketlane]

**Implementation (Sentinel)**
- Single lead per account — Federico is the lead today. Client memory agent backs this.
- Automate reminders for setup steps. Scheduler already does this for scans; extend to "we have not received your consent doc yet."
- Account setup checklist: desired outcomes, client requirements, FAQs, escalation path. We do not have this document yet — open gap.
- The Sentinel kickoff call is not a greeting — it is where goals, scope, milestones, and escalation expectations are named and agreed in one sitting. Every item confirmed on that call becomes part of the client memory record; anything unconfirmed is a future dispute. Forty-five minutes, one agenda, written back to the client in Danish plain language the same day. [Rocketlane]
- When setup is waiting on the client, say so plainly in Telegram — "we have not received your signed consent yet, reply here when it is in" — rather than chasing through side channels. No dashboard means the chat itself has to carry the visibility: the client should always know whose turn it is. [Rocketlane]

**Post-onboarding**
- Track health scores. Our analogue: finding count trend, response-to-alert rate, last message opened.
- Detect upsell opportunities. Watchman clients who engage with the free finding = primary Sentinel conversion target.
- Publicise progress back to the client even when the news is quiet. The monthly summary — "your surface stayed clean this month, here is what we watched" — is the milestone message, not a filler. A silent month from us reads as an absent month; a short acknowledged one reinforces that the service is still on watch. [Rocketlane]

**Feedback timing [Plecto]**
- Ask the single feedback question immediately after onboarding lands, while it is fresh — not folded into a monthly summary. For us this is one plain-language Telegram message after the first Sentinel finding has been delivered and acknowledged.

---

## Metrics to track (mapped to Heimdall) [Custify]

| Custify metric | Heimdall measurement |
|----------------|----------------------|
| Time to onboarding completion | Hours from consent signing → first Sentinel scan delivered |
| Time to first value | Watchman: minutes from signup → first finding message. Sentinel: hours from consent → first alert. |
| Trial → paid conversion | Watchman → Sentinel conversion rate (primary funnel metric) |
| Onboarding completion rate | % of Watchman signups who received + read the first finding |
| CSAT / CES | "Got it" button click rate; reply rate to follow-up |
| Product adoption | Scan cadence accepted, alerts acknowledged |
| Churn rate | Sentinel monthly cancellations |
| First-90-day churn | Sentinel cancellations in the first 90 days — diagnosed as onboarding failure, not product failure [Rocketlane] |

We do not yet have a time-to-first-value SLA. Recommend defining one before pilot.

Churn after 90 days is a product-fit signal; churn inside 90 days is an onboarding signal. Treat them as different problems with different fixes. [Rocketlane]

---

## Pitfalls to avoid [Custify]

1. **No standard operating procedure** — every onboarding ad-hoc. **Action for Heimdall:** write the SOP before the first pilot client, not after.
2. **No tracking setup** — "common in startups." We already have `client_memory` infrastructure; populate it from day one.
3. **Mismatched / disparate data** — a false sense of security. Single source of truth = `data/clients/clients.db`. Enforce it.
4. **Budget / resource constraints** — solo-operator risk. Mitigate with automation (scheduler, interpreter, composer) and by putting appropriate setup work on the client (consent signing, scope confirmation).
5. **Outdated SOP** — re-review onboarding flow after every 5 clients during pilot.

---

## Automation opportunities (already mapped to Heimdall) [Custify]

| Custify category | Heimdall implementation |
|------------------|--------------------------|
| Welcome automation | Telegram welcome message on bot first-contact |
| Data collection | Onboarding survey — *not yet built*; currently captured in free-text during outreach |
| Implementation | Scheduler auto-creates first scan post-consent |
| Follow-up / nurturing | CT monitoring → auto-alert; cert-change dry run lives in `scripts/dev/cert_change_dry_run.py` |

**Gate question before automating anything new:** *"Can automating this specific process cause more problems than it solves?"* (Valdí territory — Layer/consent state must still be respected by any automated trigger.)

---

## Templates the Custify guide points at (worth adapting) [Custify]

- **Customer onboarding checklist** — 5-stage visual. Heimdall should write its own Watchman + Sentinel versions.
- **Welcome email template** (Appcues example).
- **Onboarding call script** (Hubspot example).
- **Onboarding survey** — specific account info, product questions, customer goals, stakeholder identification.
- **Good onboarding CX checklist (6 items):** keep them interested, ensure they understand value, ask goals, repeat goals back, plan next steps, schedule next meeting.

---

## What this means for Heimdall (present, not decided)

Three candidate next actions, each with a trade-off — **Federico decides**:

1. **Write Watchman + Sentinel onboarding SOPs before pilot.** Cost: half-day doc work. Benefit: prevents ad-hoc variance in the first 5 clients. Risk: premature if SIRI takes 6+ months.
2. **Define time-to-first-value SLA — as a sequence of small-win deadlines, not a single number.** Post-FVD merge: welcome-ack, first-finding-delivered, first-alert-delivered, first-monthly-summary, each with its own target. Cost: small. Benefit: turns a soft claim into a measurable sequence. Risk: commits us before we know real operational load.
3. **Build the onboarding survey into the Telegram welcome flow.** Cost: 1–2 dev days + bot UX. Benefit: captures desired outcomes in customer's own words (feeds interpreter tone). Risk: adds friction to the "first finding free" promise.
4. **Define the first-90-day churn diagnostic split + the one-question end-of-onboarding feedback prompt, both before client #1.** Cost: near-zero (both are policy, not code). Benefit: the two cheapest pieces of the Plecto/Rocketlane merge; both need to exist at pilot start to be meaningful. Risk: none worth listing.

None of these are urgent — all are pilot-prep.

---

## References

1. Custify — SaaS Customer Onboarding Guide. Irina Vatafu. Updated 2026-04-01. https://www.custify.com/blog/saas-customer-onboarding-guide/
2. ChurnRX 2023 Report (cited in source).
3. Plecto — SaaS Onboarding. Sage Crawford. 2026-01-01. https://www.plecto.com/blog/customer-service/saas-onboarding/
4. Rocketlane — The Ultimate Guide to SaaS Customer Onboarding. https://www.rocketlane.com/blogs/the-ultimate-guide-to-saas-customer-onboarding
