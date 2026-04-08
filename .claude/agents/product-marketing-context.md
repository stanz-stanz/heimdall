# Product Marketing Context

*Last updated: 2026-04-07*
*Auto-drafted from codebase. Review and correct before use.*

## Product Overview
**One-liner:** Heimdall is an AI-powered cybersecurity service that monitors Danish SMB websites and delivers plain-language security alerts through Telegram.

**What it does:** Heimdall continuously scans a business's public-facing digital surface — domains, certificates, web servers, CMS platforms, plugins — and translates technical findings into plain-language messages delivered through Telegram. It remembers each client's tech stack, tracks what changed since the last scan, and follows up on unresolved issues. The owner reads a message on their phone; they never log into a dashboard.

**Product category:** External Attack Surface Management (EASM) — but positioned as "cybersecurity monitoring for small businesses" because the target audience has never heard "EASM."

**Product type:** B2B SaaS subscription (monthly/annual), delivered via messaging app.

**Business model:** Two tiers, all prices excl. moms:
- Watchman: 199 kr./mo (annual: 169 kr./mo) — trial/on-ramp tier. Passive scanning, plain-language alerts. Designed as a stepping stone to Sentinel, not a permanent product.
- Sentinel: 399 kr./mo (annual: 339 kr./mo) — the actual product. Daily monitoring, active vulnerability testing (Layer 2), confirmed findings, step-by-step fix instructions.

Watchman exists because passive scans are nearly free to run — it's the low-commitment entry point. Sentinel is where real protection starts. Every SMB needs what Sentinel delivers; Watchman is a bridge to get there.

Acquisition: "First finding free" — passive scan produces real findings at near-zero cost, shared before asking for anything.

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
2. Plain-language interpretation — technical findings translated into language the restaurant owner understands, reviewed by a human
3. Persistent memory + follow-up — tracks what changed, what was fixed, what was ignored, follows up
4. Digital twin system — CVE-level findings without touching the prospect's systems or requiring consent
5. Price: Sentinel at 399 kr./mo is cheaper than every competitor's comparable offering

**How we do it differently:** Tools detect. Findings get translated into plain language. Telegram delivers. The owner reads a message, not a report.

**Why that's better:** The security finding that never gets read is worthless. Heimdall's findings get read because they arrive in the app the owner already checks 50 times a day.

**Why customers choose us:** "It's the only thing that actually tells me what's wrong with my website in a way I can understand."

## Objections

Responses follow the Danish cultural constraints: show don't claim, no pressure, let them decide.

| Objection | Response |
|-----------|----------|
| "I already have a website, it works fine" | "It does work — your customers can use it. We just noticed [specific finding] when we looked at what's visible from the outside. Here's what that means in practice: [analogy]. You can decide if it's worth addressing." |
| "I'm too small to be a target" | "Most attacks are automated — they scan thousands of sites looking for known weaknesses, regardless of company size. 40% of Danish SMBs lack adequate security according to government data. We can show you what your site looks like from the outside." |
| "My web developer/hosting handles security" | "They handle the server and the code. We look at what's visible from the outside — the things an automated scanner would find. Think of it as the difference between your building's locks and someone checking if the windows are open. Complementary, not competing." |
| "399 kr. is another monthly expense I don't need" | "Here's what you'd get for that: daily checks, confirmed findings about your actual site, and plain-language instructions you can forward to your webmaster. Whether that's worth it depends on what your website handles — if customers enter data on it, the risk calculus changes." |

**Anti-persona:** Companies with an existing MSSP or in-house security team. Companies on fully managed platforms (Shopify, Squarespace) with no plugins or custom code — they already have platform security. Companies that don't have a website at all.

**Note on AI framing (Danish AI trust gap):** Danish consumers see through AI marketing and trust brands less when it's used without care. In all client-facing materials: lead with human expertise ("Federico reviews findings"), describe AI as the method not the product ("we use AI to translate technical findings into plain language"), never use "AI-powered" as a headline or selling point.

## Switching Dynamics (JTBD Four Forces)
**Push (away from current state):** Insurer asking about cybersecurity. Customer noticing a browser warning. Government allocating 211M kr. for SMB digital security. Hearing about a breach at a similar business. These are context — not arguments to weaponize.

**Pull (toward Heimdall):** A specific observation about THEIR website — concrete, not generic. Plain language they understand. A free report with no strings. The feeling that someone competent is keeping an eye on things.

**Habit (keeps them doing nothing):** "It's been fine so far." Inertia. "I wouldn't know what to do with the information anyway." Cost aversion.

**Anxiety (about switching):** "Will this expose something embarrassing?" "Am I committing to something I don't understand?" "What if they find something terrible?"

**Danish-specific note:** Fear-based push is counterproductive with Danish consumers. They reject pressure. The pull must do the heavy lifting — a real finding about their real website is more persuasive than any statistic about breaches.

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
**Tone:** Direct, calm, understated. Like a craftsperson explaining their work to a peer — not a salesperson pitching a prospect. Never alarmist. Never condescending. Never self-congratulatory.

**Style:** Analogy-driven, consequence-aware. Show, don't claim. Present data and let the reader draw conclusions. "Your website is broadcasting which PHP version it runs. That's like putting a sign on your shop door listing which locks you use." No jargon. Short sentences.

**Personality:** Watchful, competent, approachable, Danish-grounded, honest about what we know vs. what we infer.

## Danish Cultural Constraints (mandatory for all client-facing copy)

These rules are derived from `docs/campaign/marketing-keys-denmark.md` and apply to ALL outreach, campaign, and client-facing materials. They are not guidelines — they are hard constraints.

1. **Janteloven is the master constraint.** No superiority claims. No "we're the best." No "exclusive." Position around collective benefit and smart choices. If copy implies "we know better than you," rewrite it.
2. **Show, don't claim.** Proof over promise. Data, demos, peer reviews — not superlatives. Let the Dane decide if it's good. Never tell them it's good.
3. **Trust is default-on but permanently revocable.** Danish consumers start from trust. Over-promising is the fastest way to destroy a brand relationship. Radical transparency is baseline, not a differentiator. If Heimdall can't confirm something, say so explicitly.
4. **Humble + honest + durable.** The brand voice should sound like a craftsperson explaining their work to a peer. Not a pitch. Not a performance.
5. **Community benefit over individual gain.** Frame what the product does for the customer's neighborhood, their customers' safety, shared digital hygiene — not just their own business.
6. **Egalitarianism — no status tiers.** Never frame Watchman vs. Sentinel as "basic vs. premium" or imply one customer is more valued than another. Watchman is a trial; Sentinel is the service. Different stages, not different status.
7. **AI trust gap.** Danish consumers trust brands less when AI is foregrounded without care. Lead with human expertise and judgment. "Federico reviews every finding" matters more than "AI-powered." Technology is the how, not the what.
8. **Work-life balance framing.** Efficiency is only valued if it translates to more free time and peace of mind — not more productivity. "So you can focus on your business" = good. "Optimize your security posture" = wrong audience.
9. **No fear-based selling.** Loss aversion is acceptable as context (breach statistics exist), but it must never be the primary driver. Lead with what Heimdall does, not what happens without it. Danes reject pressure tactics.
10. **Design = function.** Show how it works, not how polished it looks. Every element of communication must serve a purpose. No decoration for decoration's sake.

## Proof Points
**Metrics:**
- 1,173 Danish SMB websites scanned (real data, not projections)
- 94% missing Content-Security-Policy header
- 83% missing HSTS
- 40% of Danish SMBs lack adequate security (government statistic)
- 211 million kr. government investment in SMB cybersecurity 2026-2029
- Sentinel at 399 kr./mo — cheaper than every competitor's comparable offering
- Watchman trial at 199 kr./mo — low-commitment entry point

**Customers:** Pre-launch (pilot in progress, blocked by SIRI approval)

**Testimonials:** None yet. First pilot clients will provide.

**Value themes:**
| Theme | Proof |
|-------|-------|
| The gap is real | 40% of Danish SMBs + 211M kr. government response |
| Existing tools don't fit | Every competitor uses dashboards; cheapest entry is 215 kr./mo |
| Our approach works | 1,173 sites scanned with real findings using only passive observation |
| Price is not a barrier | Sentinel 399 kr./mo — less than half the cheapest competitor. Free trial via Watchman. |

## Goals
**Business goal:** 5 paying pilot clients in Vejle, then 200 clients in 36 months.

**Conversion action:** Agree to receive a free security report (email or DM) → Watchman trial → Sentinel subscription.

**Current metrics:** 138 Bucket A contactable prospects identified. 0 clients (pre-launch). Pipeline operational, outreach beginning.
