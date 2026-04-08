# Email & DM Templates — Heimdall Outreach Campaign

*Created: 2026-04-07*
*Updated: 2026-04-08 — Danish cultural alignment pass*
*Language: Danish (all templates)*
*Legal status: GREEN — B2B email to non-Reklamebeskyttet companies; Facebook/Instagram DMs*
*Cultural alignment: all templates follow Danish cultural constraints in `docs/campaign/marketing-keys-denmark.md`. Craftsperson tone. Show don't claim. No fear-based selling. Transparency over persuasion.*

---

## Provenance Rules (apply to ALL templates)

| Provenance | Allowed framing | Prohibited framing |
|------------|----------------|-------------------|
| `confirmed` (exposed PHP, missing protections, SSL issues, exposed server info) | State as fact: "Vi har observeret at..." | -- |
| `unconfirmed` (version-matched CVE) | "Jeres detekterede version af [X] er kendt for at vaere paavirket af [beskrivelse]" | "I har denne saarbarhed", "Vi fandt denne saarbarhed paa jeres system" |

Lead with confirmed observations. Mention unconfirmed findings as secondary context only.

---

## Email Templates

### Email 1 — "First Finding Free" (sikkerhedsnotits)

**Channel:** B2B email to company address (non-Reklamebeskyttet verified)
**Psychology:** Reciprocity (genuine free value) + Transparency (specific, verifiable observation about their site)
**Danish key:** No open loops or AIDA funnels. Danes start from trust — be direct about what we found and why we're writing. Let them decide if they want more.
**Timing:** Week 3-4 of campaign (after Facebook warm-up)

---

**Emne:** Sikkerhedstjek af [DOMAIN] — noget vi gerne vil dele med jer

---

Hej [COMPANY_NAME],

Vi kigger paa danske virksomheders hjemmesider udefra — det samme som enhver automatiseret scanner kan se. I den forbindelse har vi ogsaa kigget paa [DOMAIN].

**Vi lagde maerke til noget:**

[CONFIRMED_FINDING]

Det er ikke noget, man opdager som ejer — det kraever at man kigger paa hjemmesiden udefra. De fleste sider vi har set har lignende observationer.

[GDPR_CONTEXT]

Vi har en samlet oversigt med flere observationer om [DOMAIN]. Den er gratis og uforpligtende.

**Vil I gerne se den?** Svar paa denne mail, saa sender jeg den.

Venlig hilsen,

[NAVN]
[TITEL]
Heimdall Cybersikkerhed
CVR: [CVR-NUMMER]

---

**Insertion points:**
- `[DOMAIN]` — prospect's domain (e.g., `vejleklinik.dk`)
- `[COMPANY_NAME]` — company name from CVR data
- `[CONFIRMED_FINDING]` — one confirmed Layer 1 observation, written in plain language with analogy. Examples:
  - "Jeres webserver fortaeller alle besoegende hvilken PHP-version den koerer (PHP 7.4). Det svarer til at haenge et skilt paa doeren med hvilke laase I bruger — det goer det lettere for automatiserede angreb at finde svagheder."
  - "Jeres hjemmeside mangler flere grundlaeggende sikkerhedsbeskyttelser (HSTS, Content-Security-Policy). Det betyder at browseren ikke faar besked om at kryptere forbindelsen automatisk — og jeres besoegendes data sendes uden fuld beskyttelse."
  - "Jeres SSL-certifikat udloeber om [X] dage. Naar det sker, viser browseren en advarsel til alle besoegende — og de fleste klikker vaek med det samme."
- `[GDPR_CONTEXT]` — only include if `gdpr_flag: true` in brief. Example:
  - "Fordi jeres hjemmeside haandterer kundedata (kontaktformular / booking / patientoplysninger), kan manglende sikkerhedsbeskyttelser vaere relevant i forhold til GDPR artikel 32 — kravet om passende tekniske foranstaltninger."
- `[NAVN]`, `[TITEL]`, `[CVR-NUMMER]` — sender details

**Unconfirmed finding variant** (use as secondary context only, never as the lead finding):
> "Derudover koerer jeres hjemmeside en version af [plugin/CMS], som er kendt for at vaere paavirket af en sikkerhedsfejl ([kort beskrivelse]). Vi kan ikke bekraefte om den er aktiv paa jeres side, men det er vaerd at faa tjekket."

---

### Email 2 — Follow-up (5-7 dage efter Email 1)

**Channel:** Reply thread to Email 1
**Psychology:** Transparency (new observation adds context) + Low friction (simple choice)
**Danish key:** No manipulation framing. They didn't respond — that's fine. Add genuine new value. Keep it short. Danes appreciate brevity and respect for their time.
**Timing:** 5-7 days after Email 1, only to non-responders

---

**Emne:** Re: Sikkerhedstjek af [DOMAIN] — noget vi gerne vil dele med jer

---

Hej [COMPANY_NAME],

Jeg skrev for nogle dage siden om [DOMAIN]. Vi har siden lagt maerke til noget mere:

[SECOND_FINDING]

Vi har samlet alle observationer i en kort oversigt — i klart sprog, uden teknisk jargon.

Vil I have den paa email, eller som en besked paa Telegram? Svar bare med "email" eller "besked".

Venlig hilsen,

[NAVN]
[TITEL]
Heimdall Cybersikkerhed
CVR: [CVR-NUMMER]

---

**Insertion points:**
- `[DOMAIN]` — same as Email 1
- `[COMPANY_NAME]` — same as Email 1
- `[SECOND_FINDING]` — a different confirmed Layer 1 observation than Email 1. Choose a different category. Examples:
  - If Email 1 used exposed PHP version, Email 2 uses missing security protections: "Jeres hjemmeside sender ikke de sikkerhedsbeskyttelser (headers) som moderne browsere forventer. Det betyder at browseren ikke kan beskytte jeres besoegende optimalt — f.eks. mod at data paa siden bliver manipuleret."
  - If Email 1 used missing headers, Email 2 uses exposed server info: "Jeres server deler information om hvilken software den koerer (servertype og version). Det goer det lettere for automatiserede vaerktoejer at lede efter kendte svagheder i netop den version."
  - If applicable, a GDPR angle: "Vi bemerkede at jeres kontaktformular sender data uden at jeres side har en Content-Security-Policy. Det er relevant fordi GDPR kraever passende tekniske foranstaltninger naar I haandterer persondata."

---

## Facebook / Instagram DM Templates

### DM 1 — Engagement-baseret (liked/kommenteret paa et opslag)

**Channel:** Facebook/Instagram direct message
**Psychology:** Community (shared local context) + Reciprocity (they showed interest, we offer value)
**Danish key:** They engaged voluntarily — acknowledge it warmly but don't treat it as a sales funnel step. Offer, don't push.
**Trigger:** Prospect liked or commented on a Heimdall post

---

> Hej [FORNAVN] — tak for din [like/kommentar] paa vores opslag om hjemmesidesikkerhed! Vi har faktisk kigget paa hjemmesider i Vejle-omraadet, og vi har ogsaa set paa [DOMAIN]. Vi har et par observationer vi gerne vil dele — helt gratis og uforpligtende. Maa vi sende dem?

---

**Notes:**
- Max ~280 characters for Facebook Messenger opening. The template above is ~290 characters — trim `helt gratis og uforpligtende` to `helt gratis` if needed.
- If domain is not identifiable from their profile, replace `[DOMAIN]` with: "hjemmesider i jeres branche"
- Only send if their profile clearly identifies them as a business owner

**Insertion points:**
- `[FORNAVN]` — first name from profile
- `[like/kommentar]` — match their specific action
- `[DOMAIN]` — their business domain if identifiable

---

### DM 2 — Lead form-respondent (udfyldte en annonce)

**Channel:** Facebook/Instagram direct message
**Psychology:** Reciprocity (they asked, we deliver) + Trust maintenance (do exactly what was promised, nothing more)
**Danish key:** They opted in — honour that with speed and simplicity. No upsell in this message. Trust is default-on; don't break it by adding sales language.
**Trigger:** Prospect submitted a lead form ad requesting a free check

---

> Hej [FORNAVN] — tak fordi du tilmeldte dig vores gratis sikkerhedstjek! Vi gaar i gang med det samme. Har du et domaenanavn vi skal kigge paa? (f.eks. dinvirksomhed.dk)

---

**Follow-up after receiving domain:**

> Perfekt — vi kigger paa [DOMAIN] og sender dig resultatet her inden for et par dage. Det er helt gratis, og du forpligter dig ikke til noget.

---

**Notes:**
- If the lead form already captured their domain, skip the first message and go straight to the follow-up
- Keep conversational, not formal — they already showed interest

**Insertion points:**
- `[FORNAVN]` — from lead form data
- `[DOMAIN]` — from lead form or their reply

---

### DM 3 — Rapport-opfoelgning (efter gratis rapport er sendt)

**Channel:** Facebook/Instagram direct message
**Psychology:** Genuine follow-up (check if they have questions) + Soft introduction to ongoing service
**Danish key:** No manipulation framing (endowment, foot-in-door). This is a craftsperson checking back: "Did that make sense? Any questions?" The monitoring offer comes naturally if they're interested.
**Trigger:** 2-3 days after sending the free report via DM or email

---

> Hej [FORNAVN] — naaede du at se rapporten om [DOMAIN]? Hvis du har spoergsmaal til noget af det, svarer jeg gerne. Mange af de ting vi fandt kan loeses ret nemt af jeres webmaster. Hvis I oensker loebendeovervaagning, saa jeres hjemmeside bliver tjekket automatisk, kan jeg fortaelle mere om hvordan det virker. Bare sig til!

---

**Notes:**
- Do NOT mention pricing in this message. The goal is to open a conversation, not close a sale.
- If they respond with interest in monitoring, THEN introduce Watchman tier in the next message.
- If they say "my webmaster handles it" — respond with the scope reframe: "Det er perfekt. Jeres webmaster passer paa bygningen — vi holder oeje med hvad der er synligt udefra. Taenk paa det som forskellen mellem laasene paa jeres doer og nogen der tjekker om vinduerne staar aabne."

**Insertion points:**
- `[FORNAVN]` — first name
- `[DOMAIN]` — their domain

---

## Usage Notes

### Sending sequence
1. Facebook content starts Week 1 (mere exposure)
2. Email 1 goes out Week 3-4
3. Email 2 goes out 5-7 days after Email 1 (non-responders only)
4. DM 1 is triggered by engagement at any time
5. DM 2 is triggered by lead form submission (if paid ads are running)
6. DM 3 is sent 2-3 days after delivering a free report

### Batch segmentation
- Batch 1 (Weeks 3-4): ~40-50 prospects — GDPR-sensitive industries + highest finding counts
- Batch 2 (Weeks 5-6): ~60-70 prospects — remaining high-priority
- Batch 3 (Weeks 7-8): ~20-30 prospects — lower priority

### Legal checklist per email
- [ ] Company is NOT on Robinson-listen (Reklamebeskyttet)
- [ ] Email is sent to a general company address (info@, kontakt@), not a personal email
- [ ] Finding used is from passive Layer 1 scan only
- [ ] Confirmed findings stated as facts; unconfirmed findings use "known to be affected" language
- [ ] No pricing in Email 1
- [ ] Heimdall identity and CVR clearly stated
- [ ] No threatening or pressure language

### Measurement targets
- Email 1 open rate: >30%
- Email 1 response rate: >10%
- Email 2 response rate: >15% (of Email 1 non-responders)
- Free report requests: >5% of total contacted
- DM response rate: >25% (warmer audience)
