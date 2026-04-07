# Product Marketing Context

*Last updated: 2026-04-07*
*Auto-drafted from codebase. Review and correct before use.*

## Product Overview
**One-liner:** Heimdall is an AI-powered cybersecurity service that monitors Danish SMB websites and delivers plain-language security alerts through Telegram.

**What it does:** Heimdall continuously scans a business's public-facing digital surface — domains, certificates, web servers, CMS platforms, plugins — and translates technical findings into plain-language messages delivered through Telegram. It remembers each client's tech stack, tracks what changed since the last scan, and follows up on unresolved issues. The owner reads a message on their phone; they never log into a dashboard.

**Product category:** External Attack Surface Management (EASM) — but positioned as "cybersecurity monitoring for small businesses" because the target audience has never heard "EASM."

**Product type:** B2B SaaS subscription (monthly/annual), delivered via messaging app.

**Business model:** Three subscription tiers, all prices excl. moms:
- Watchman: 199 kr./mo (annual: 169 kr./mo) — finds problems, explains in plain language
- Sentinel: 399 kr./mo (annual: 339 kr./mo) — adds daily monitoring + step-by-step fix instructions
- Guardian: 799 kr./mo (annual: 669 kr./mo) — priority cadence + dedicated support + quarterly report

Acquisition: "First finding free" — passive scan produces real findings at near-zero cost, shared before asking for anything. Break-even at ~13-14 paying clients.

## Target Audience
**Target companies:** Danish micro-businesses (1-19 employees) with a website handling customer data or transactions. Restaurants with online booking, physiotherapists, dental clinics, barbershops, accountants, real estate agents. Initially Vejle area.

**Decision-makers:** The owner. There is no IT department, no security team, no procurement process. The person who answers the phone makes the buying decision.

**Primary use case:** Knowing when your website has a security problem — before a hacker, a customer, or the Datatilsynet finds it.

**Jobs to be done:**
- "Tell me if my website is safe" — peace of mind that someone is watching
- "Tell me what to do about it" — actionable instructions, not technical jargon
- "Give me proof I take security seriously" — documentation for insurers, accountants, GDPR compliance

**Use cases:**
- Restaurant with online booking running outdated WordPress — doesn't know plugins have known CVEs
- Physio clinic with patient contact form — doesn't know the form transmits data without proper security headers
- Accountant with client portal — needs documentation that their digital surface is monitored for insurance/audit purposes

## Personas

| Persona | Role | Cares about | Challenge | Value we promise |
|---------|------|-------------|-----------|------------------|
| Owner-Operator | Decision maker + buyer + user | Their business, not technology. Time. Reputation. "Will this cost me customers?" | No time, no IT knowledge, no awareness that their website is a liability | "We watch your website so you don't have to. You get a message when something needs attention — in words you understand." |
| The Accountant/Advisor | Influencer / referrer | Client compliance, risk reduction, documentation | Can't assess clients' digital security; knows GDPR applies but has no tools | "Your clients' websites are exposed. We can monitor them and give you quarterly reports." |
| The Web Agency | Channel partner | Client retention, reputation, upsell revenue | Built the site 3 years ago; has no ongoing security monitoring service to offer | "22 of your 35 client sites have issues. Your name is on the footer. We can fix that together." |

## Problems & Pain Points
**Core problem:** Danish SMBs have websites handling customer data but zero visibility into their external security posture. 40% lack adequate security (government statistic). They don't know they're exposed, and they wouldn't know what to do if they did.

**Why alternatives fall short:**
- Enterprise EASM tools (Qualys, Intruder, Detectify) are too expensive (740+ kr./mo), too technical (dashboards, QQL queries), and designed for security teams that SMBs don't have
- Managed Security Service Providers (MSSPs) are overkill and cost thousands per month
- "Do nothing" is the current default — and the government says 40% of SMBs are doing exactly this
- Web agencies built the site but don't monitor it ongoing

**What it costs them:**
- 60% of SMBs that suffer a major breach close within six months (VikingCloud 2026)
- Median breach cost exceeds $120,000 for small businesses
- GDPR fines under Article 32 for inadequate technical measures
- Customer trust destruction when browsers show security warnings

**Emotional tension:** "I know I should be doing something about cybersecurity, but I don't know what, I don't have time, and everything I see is designed for IT people — not for someone who runs a restaurant."

## Competitive Landscape

**Direct competitors:**
- Intruder.io (~740 kr./mo) — web dashboard + Slack/Jira. Falls short: too expensive for micro-SMBs, requires technical knowledge to use dashboard, no messaging delivery
- HostedScan (free tier; paid from ~215 kr./mo) — web dashboard. Falls short: dashboard-only, no interpretation, no follow-up
- Detectify (~610 kr./mo app) — web dashboard. Falls short: price, complexity, enterprise-oriented

**Secondary competitors (different solution, same problem):**
- Web agencies offering "maintenance packages" — sporadic, not continuous, no vulnerability scanning
- DIY WordPress security plugins (Wordfence, Sucuri plugin) — requires the owner to understand what the plugin shows them

**Indirect competitors (conflicting approach):**
- "Do nothing and hope for the best" — the #1 competitor. 60% of the market.
- Cyber insurance without monitoring — pays after the breach, doesn't prevent it

**Enterprise EASM (not competitors, but context):** CrowdStrike Falcon Surface, Qualys EASM, Censys ASM, Outpost24 (Swedish, Danish subsidiary, $40-100k/yr). Validates the market category exists; Heimdall serves the segment they all ignore.

## Differentiation
**Key differentiators:**
1. Messaging-first delivery (Telegram/WhatsApp) — no dashboard, no login, no learning curve
2. Plain-language AI interpretation — Claude API translates technical findings into language the restaurant owner understands
3. Persistent memory + follow-up — tracks what changed, what was fixed, what was ignored, escalates
4. Digital twin system — CVE-level findings without touching the prospect's systems or requiring consent
5. Price: 199 kr./mo entry tier is cheaper than every competitor

**How we do it differently:** Tools detect. AI interprets. Telegram delivers. The owner reads a message, not a report.

**Why that's better:** The security finding that never gets read is worthless. Heimdall's findings get read because they arrive in the app the owner already checks 50 times a day.

**Why customers choose us:** "It's the only thing that actually tells me what's wrong with my website in a way I can understand."

## Objections

| Objection | Response |
|-----------|----------|
| "I already have a website, it works fine" | "It works for customers. But when we looked at it from the outside — the way a hacker would — we found [specific finding]. That doesn't mean you're hacked, but it means the door isn't locked." |
| "I'm too small to be a target" | "Automated attacks don't check company size. 40% of Danish SMBs lack adequate security — the government just allocated 211 million kr. because businesses exactly your size are the ones getting hit." |
| "My web developer/hosting handles security" | "They handle the server. We monitor the attack surface — everything a hacker can see from the outside. Think of it as the difference between your building's locks and someone checking if your windows are open." |
| "199 kr. is another monthly expense I don't need" | "It's less than a single dinner delivery. And the average SMB breach costs over $120,000. It's not about the 199 kr. — it's about the one finding that saves your business." |

**Anti-persona:** Companies with an existing MSSP or in-house security team. Companies on fully managed platforms (Shopify, Squarespace) with no plugins or custom code — they already have platform security. Companies that don't have a website at all.

## Switching Dynamics (JTBD Four Forces)
**Push (away from current state):** News about breaches. GDPR fine stories. Insurer asking about cybersecurity. Customer complaint about browser warning. Government announcing 211M kr. because businesses like theirs are vulnerable.

**Pull (toward Heimdall):** Specific finding about THEIR website — not generic fear. Plain language. Low price. "Someone is watching out for me." The feeling of being protected.

**Habit (keeps them doing nothing):** "It's been fine so far." Inertia. "I wouldn't know what to do with the information anyway." Cost aversion.

**Anxiety (about switching):** "Will this expose something embarrassing?" "Am I committing to something I don't understand?" "What if they find something terrible?"

## Customer Language
**How they describe the problem:**
- "Jeg aner ikke om min hjemmeside er sikker" (I have no idea if my website is safe)
- "Min webmaster har ikke kigget pa den i to ar" (My webmaster hasn't looked at it in two years)
- "Jeg fik en mail om GDPR men jeg forstod det ikke" (I got an email about GDPR but I didn't understand it)

**How they describe the solution (aspirational — pre-customer):**
- "Nogen der holder oje med det for mig" (Someone keeping an eye on it for me)
- "En besked nar der er noget galt" (A message when something's wrong)

**Words to use:** hjemmeside (website), sikkerhed (security), hacker, GDPR, databrud (data breach), besked (message), gratis tjek (free check), overvagning (monitoring)

**Words to avoid:** EASM, attack surface, vulnerability, CVE, CMS, header, endpoint, Layer 1/2, API, plugin (use "tilfoejelse" or skip), pentest, remediation

**Glossary:**
| Term (internal) | Customer-facing equivalent |
|-----------------|---------------------------|
| EASM | Cybersecurity monitoring for your website |
| Layer 1 scan | Free security check |
| Finding | Something we noticed on your website |
| CVE | A known security flaw |
| Security header | A basic protection your website should have |
| SSL certificate | The padlock in your browser's address bar |

## Brand Voice
**Tone:** Direct, calm, professional. Never alarmist. Never condescending. Like a knowledgeable neighbor explaining something important.

**Style:** Analogy-driven, consequence-focused. "Your website is broadcasting which PHP version it runs. That's like putting a sign on your shop door listing which locks you use." No jargon. Short sentences.

**Personality:** Watchful, competent, approachable, Danish-grounded, honest about what we know vs. what we infer.

## Proof Points
**Metrics:**
- 1,173 Danish SMB websites scanned (real data, not projections)
- 94% missing Content-Security-Policy header
- 83% missing HSTS
- 40% of Danish SMBs lack adequate security (government statistic)
- 211 million kr. government investment in SMB cybersecurity 2026-2029
- Watchman tier at 199 kr./mo — cheaper than every competitor's entry price

**Customers:** Pre-launch (pilot in progress, blocked by SIRI approval)

**Testimonials:** None yet. First pilot clients will provide.

**Value themes:**
| Theme | Proof |
|-------|-------|
| The gap is real | 40% of Danish SMBs + 211M kr. government response |
| Existing tools don't fit | Every competitor uses dashboards; cheapest entry is 215 kr./mo |
| Our approach works | 1,173 sites scanned with real findings using only passive observation |
| Price is not a barrier | 199 kr./mo — less than a dinner delivery |

## Goals
**Business goal:** 5 paying pilot clients in Vejle, then 200 clients in 36 months.

**Conversion action:** Agree to receive a free security report (email or DM), leading to Watchman subscription.

**Current metrics:** 138 Bucket A contactable prospects identified. 0 clients (pre-launch). Pipeline operational, outreach beginning.
