# Heimdall — SIRI Video Pitch Script

**Status:** Working draft, not committed.
**Purpose:** Spoken script for the mandatory Startup Denmark video pitch.
**Format:** English. Target duration 4:30 (SIRI maximum: 5 minutes). No burned-in captions.
**Audience:** SIRI independent expert panel, scoring on four criteria (Innovation / Market / Scalability / Team).
**Delivery note:** Read conversationally. Danish register — calm, specific, no hype, no superlatives. Pause on the finding, not on the claim.

Word count target: ~600 spoken words at a natural 135–140 wpm.

---

## Stage setup (before speaking)

- Federico on camera, neutral background, daylight. No product logo slide.
- On-screen text appears only where marked. No animated transitions.
- Single cut allowed between sections if needed.

---

## 0:00–0:25 — Cold open (Hook)

> [On camera. No title card yet.]
>
> Forty percent of Danish small businesses don't have cybersecurity that matches the threats they face. That number comes from Styrelsen for Samfundssikkerhed — the Danish agency. The government's response, in January 2026, was to commit 211 million kroner over four years to close the gap.
>
> [Brief pause.]
>
> The tools to find these problems already exist. They run in dashboards built for security teams. The restaurant owner with an online booking system doesn't have a security team. She has a phone.

**On-screen text (0:20):** *40% · 211M kr. · Styrelsen for Samfundssikkerhed, 2026*

---

## 0:25–1:10 — What Heimdall is *(Innovation + Market)*

> I'm Federico Alvarez. I'm building Heimdall — a cybersecurity service for Danish small businesses that delivers findings through Telegram, in plain language, instead of through a dashboard.
>
> Here's the product in one message. When Heimdall scans a website and finds something, the owner gets a message that reads something like:
>
> *"Your SSL certificate expires in 12 days. When it does, customers will see a browser warning when they try to book. That scares people away."*
>
> That's it. No login. No PDF. No jargon. They read it on the bus.

**On-screen text (0:40–1:10):** *Real Telegram screenshot from `@HeimdallSecurityDEVbot` — the SSL certificate message above, in an actual chat bubble. Static image, no animation. Scrub any chat_id, operator handle, or timestamp that identifies a real account before recording.*

---

## 1:10–2:15 — What's actually innovative *(Innovation)*

> Every existing attack-surface tool on the market delivers findings through a web dashboard. Intruder, Detectify, Qualys, HostedScan — they all assume the buyer has someone on staff who reads security dashboards. For two hundred thousand Danish small businesses, that assumption fails.
>
> Heimdall is built the opposite way. The architecture is conversational from the ground up: plain-language interpretation, persistent memory of each client's technology stack, escalating follow-up on unresolved findings.
>
> Two pieces of the system are genuinely new.
>
> The first is a digital twin. Heimdall collects publicly visible data about a prospect's website — the same information any browser receives — and reconstructs the technology stack on dedicated infrastructure Heimdall operates. Danish criminal law, Straffeloven §263, protects "another person's data system." A twin Heimdall builds and runs is Heimdall's own system. That means CVE-level vulnerability scanning becomes possible without touching the prospect's live site and without requiring their consent. No competitor offers this.
>
> The second is Valdí — a programmatic compliance agent. Every scanning function in the codebase passes through two automated gates before execution: one validates the scan type against documented legal rules, the other checks per-target consent. Every decision is logged. I built Valdí after I caught a boundary violation in my own code during early development. The systemic response was to make that class of error structurally impossible going forward.

**On-screen text (1:30–1:55, small, lower third):** *Telegram · digital twin · persistent memory · programmatic compliance*

---

## 2:15–3:05 — Market evidence *(Market)*

> This isn't theoretical. I've already run the pipeline against 1,173 Danish business websites — passive observation only, the same information a browser sees.
>
> Of those 1,173 sites: 49.3 percent had Critical or High severity findings. 60 percent had none of the four standard browser protections enabled. One in five didn't encrypt traffic at all.
>
> These aren't survey estimates. They're direct observations. The government's 40-percent figure is consistent with what I measured.
>
> Pricing is where the competitive gap is widest. The cheapest alternative on the market starts around 215 kroner per month and still ships through a dashboard. Heimdall's Watchman trial is 199 kroner per month. Sentinel — the actual product with daily monitoring and active testing — is 399 kroner per month. All prices excluding moms. For a restaurant with an online booking system, 399 kroner a month is less than a single evening's delivery orders. Price stops being the objection.

**On-screen text (2:25–2:50, stacked bullets):**
*1,173 sites scanned · 49.3% Critical or High · 60% zero security headers*

---

## 3:05–3:35 — Scalability and Denmark *(Scalability + Market)*

> The architecture is substrate-independent. Scanning, compliance, delivery — all scale without a product rewrite. Moving from pilot to hundreds of clients is an infrastructure change.
>
> Denmark is the starting market, not the ceiling. Telegram is language-agnostic; compliance built for Danish GDPR translates to all 27 EU states by default. Four to six people based in Denmark by year three.
>
> And there's a structural reason to build here. Danish marketing law blocks unsolicited electronic outreach — which kills the SaaS cold-email playbook and forces a high-trust, in-person acquisition model a remote competitor can't replicate. Physical presence in Denmark is the moat.

---

## 3:35–4:15 — Team *(Team Competencies)*

> I've spent nearly twenty years as an enterprise software engineer in the SAP ecosystem. I've led a team of thirty consultants through a full implementation at a major Colombian bank. I've coordinated SAP rollouts across Argentina, Mexico, Colombia, Barbados, and the United States. I currently work as a Senior SAP Engineer at LEGO here in Vejle — I came to Denmark on the Fast-Track scheme in 2019 and I've been based here ever since.
>
> I didn't write a business plan and stop there. The lead-generation pipeline is running. The Telegram delivery bot is running. The digital twin framework is running. The Valdí compliance system is running, with a forensic log of every scan it has approved and every scan it has rejected. The codebase has over nine hundred automated tests.
>
> A network security specialist partners with me on domain expertise. The first Danish hire — part-time operations — is the priority after pilot launch.

**On-screen text (3:35–3:55, lower third):** *Federico Alvarez · Senior SAP Engineer, LEGO (2023–) · In Denmark since 2019 · Vejle*

---

## 4:15–4:30 — The ask *(Close)*

> The pilot is ready. The code is ready. The market is measured. What's missing is the legal vehicle — a Danish company, a CVR number, the ability to sign the first paid contract.
>
> That's what the Startup Denmark residence permit unlocks. With it, I register Heimdall ApS in Vejle, open the first five pilot contracts, and start work on the local agency partnerships.
>
> Denmark created the market. I built the product for it. I'm asking for the permit to run it here.
>
> Thank you.

**On-screen text (final 5 seconds):** *Heimdall · Vejle, Denmark · Startup Denmark application*

---

## Decisions recorded (2026-04-18)

- **Language:** English.
- **Length:** 4:30 target, 5:00 hard cap.
- **Captions:** none.
- **On-screen Telegram mock (0:40–1:10):** real screenshot from `@HeimdallSecurityDEVbot`, PII scrubbed.
- **Team compression:** as-is (~40s spoken); written application remains authoritative Team record.

## Tension between written application and spoken pitch

- The written application lists **five** innovations (messaging-first, digital twin, persistent memory, Valdí, AI interpretation). The script foregrounds **two** (digital twin + Valdí) and folds the others into the "conversational architecture" description. Tradeoff: spoken clarity vs. completeness. Chose clarity; the written document carries the full list.
- The Team section in the application is ~1.5 pages. Compressed to ~40 seconds spoken, it loses the multi-geography consulting history and the Grupo Bancolombia leadership specifics. I kept one number (team of 30) as proxy for leadership scale.
- The video's closing ask maps residence-permit → CVR → pilot launch in a single chain. The written application phrases post-CVR steps more cautiously ("accessible post-establishment"). The spoken version needs causal clarity; the written version needs legal precision. Both are correct for their medium.

## Recording notes

- Read section-by-section, with a natural pause between sections. Don't try to do it in one take.
- The hook at 0:00 should not start with "Hi, I'm Federico." The 40% statistic is the hook; introduce yourself at 0:25 after the problem is on the table.
- Enunciate "Styrelsen for Samfundssikkerhed" and "Straffeloven §263" slowly — these are the two Danish-specific phrases that signal local embeddedness to the panel.
- Numbers to land cleanly: 40 percent, 211 million kroner, 1,173 sites, 49.3 percent, 199 and 399 kroner, 20 years, 2019.
