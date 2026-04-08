# Remediation Objection Handling

*Created: 2026-04-08*
*Status: DRAFT — strategic messaging framework, not yet deployed*
*Stage: Retention (post-subscription) — not part of the acquisition campaign*
*Purpose: Prevent churn from the "you found it but won't fix it" objection*

---

## 1. The Core Objection — Dissected

The objection surfaces like this:

> "You told me my booking system has a security problem. But you can't fix it? Then what am I paying 399 kr. for?"

This is not a pricing objection. It is a *trust* objection — and in Denmark, that makes it existential. Here is why.

**Ordentlighed demands closure.** Doing things properly in Danish culture means finishing the job. A carpenter who finds a rotten beam but leaves without replacing it has not been ordentlig. A security service that finds a problem but cannot resolve it triggers the same instinct: you started something you cannot finish.

**The craftsman expectation.** Danish consumers — especially SMB owners who are craftspeople themselves — evaluate services through a lens of completeness. A restaurant owner who hires a plumber expects the leak to be fixed, not a report describing the leak. Heimdall's monitoring-only model breaks this expectation unless it is framed correctly from the first interaction.

**Trust is default-on but permanently revocable.** Danish consumers do not start from skepticism. They assume you will deliver what your service implies. If a customer subscribes expecting their problems to be solved, and then discovers Heimdall only reports them, the betrayal is not proportional to the disappointment — it is total. They will not complain. They will cancel and never come back.

**The information asymmetry trap.** Telling a non-technical owner that their WordPress plugin has a known vulnerability, without fixing it, can leave them feeling *worse* than before they subscribed. They now know about a problem they cannot solve. That is not peace of mind — it is anxiety with a monthly invoice attached.

This objection is the single biggest churn risk in the business model. Every customer-facing message must be designed to prevent it from forming.

---

## 2. Framing Strategies

Five distinct angles for explaining why Heimdall monitors but does not fix. Each addresses a different aspect of the objection. Use them in combination depending on the context.

### Strategy A: The Access Argument

**Core logic:** Fixing requires access to internal systems that Heimdall does not and should not have.

**Pitch line:** "I can see your website from the outside, exactly like a hacker would. But to fix anything, I would need your passwords, your hosting login, your admin panel. For your security, I should never have those."

**Danish framing:** "Jeg holder oje med din hjemmeside udefra — ligesom en hacker ville. Men for at rette noget skal jeg bruge dine adgangskoder. Og af hensyn til din sikkerhed skal jeg aldrig have dem."

**Why it works:** It turns the limitation into a security feature. The customer's data is safer *because* Heimdall cannot touch their systems. This resonates with Danish pragmatism — the constraint is not a shortcoming, it is a design choice that protects them.

### Strategy B: The Liability Argument

**Core logic:** Fixing someone else's website carries real risk of breaking it.

**Pitch line:** "Your website is built with a specific setup — your theme, your plugins, your booking system all depend on each other. If I update one piece without understanding the whole picture, your booking page could go down on a Friday night. That is not a risk I am willing to take with your business."

**Danish framing:** "Din hjemmeside er bygget med en bestemt opsaetning — dit tema, dine tilfoejelser, dit bookingsystem haenger sammen. Hvis jeg opdaterer en ting uden at forstaa helheden, kan din bookingside gaa ned en fredag aften. Den risiko tager jeg ikke med din forretning."

**Why it works:** This appeals directly to ordentlighed — doing things properly means not rushing a fix that could cause more damage. The restaurant owner understands that updating one ingredient in a recipe changes the whole dish.

### Strategy C: The Specialist Argument

**Core logic:** Different problems require different specialists. Heimdall finds the problems; the right person for each fix varies.

**Pitch line:** "Some fixes take your web developer five minutes. Some need your hosting provider to flip a switch. Some require the company behind your booking system to release an update. I make sure you know exactly who to contact and exactly what to tell them — so they do not waste your time asking questions."

**Danish framing:** "Nogle ting tager din webudvikler fem minutter. Noget skal din hostingudbyder ordne. Andet kraever at firmaet bag dit bookingsystem laver en opdatering. Jeg soerger for, at du ved praecis hvem du skal kontakte, og praecis hvad du skal sige."

**Why it works:** This reframes Heimdall's role from "incomplete service" to "translator between you and the right specialist." It positions the customer as empowered rather than abandoned.

### Strategy D: The Continuous Watch Argument

**Core logic:** A one-time fix is not security. New problems appear constantly. The value is the ongoing watch.

**Pitch line:** "Even if I fixed today's problem, a new one could appear next week — a plugin update introduces a flaw, a certificate expires, a new vulnerability is published. What you are paying for is not a single fix. It is someone watching every day so nothing slips through."

**Danish framing:** "Selv hvis jeg rettede dagens problem, kan der komme et nyt naeste uge — en opdatering introducerer en fejl, et certifikat udloeber, en ny saarbarhed opdages. Det du betaler for er ikke en enkelt reparation. Det er nogen der holder oje hver dag, saa intet slipper igennem."

**Why it works:** This shifts the mental model from "transaction" (find problem, fix problem) to "relationship" (ongoing protection). Danish consumers value durability and long-term thinking — a service that watches continuously is more ordentligt than one that fixes and walks away.

### Strategy E: The Recipe Card Argument

**Core logic:** Heimdall provides the exact instructions so anyone can execute the fix — no guesswork, no expensive consulting hours.

**Pitch line:** "I give you the recipe — step by step, in plain Danish. Your web developer does not need to spend hours figuring out what is wrong. They open the message, follow the steps, done. That saves you their hourly rate and your time explaining the problem."

**Danish framing:** "Jeg giver dig opskriften — trin for trin, paa almindeligt dansk. Din webudvikler behoever ikke bruge timer paa at finde ud af hvad der er galt. De aabner beskeden, foelger trinnene, faerdigt. Det sparer dig deres timepris og din tid paa at forklare problemet."

**Why it works:** This is Federico's original insight, refined. It positions Heimdall as the expert who has already done the diagnostic work — the expensive, skilled part. The fix itself is often mechanical. The restaurant owner understands: a doctor's value is the diagnosis, not writing the prescription.

---

## 3. Analogies That Resonate

Each analogy is chosen for Danish SMB owners specifically — people who run physical businesses and think in concrete terms.

### The Building Inspector

> "Think of Heimdall as your digital building inspector. The inspector comes every quarter, checks the building, and tells you: the fire exit sign is missing, the emergency light needs a new battery, the backdoor lock is worn. The inspector does not replace the lock — your locksmith does that. But without the inspector, you would never know the lock was worn until someone walked in."

**Why it works for Danes:** Building inspections (tilstandsrapporter) are deeply familiar in Denmark — every property transaction includes one. The inspector's authority comes from identifying problems, not from fixing them. Nobody questions why the inspector does not also do the repairs.

### The Tandlaege (Dentist)

> "Your dentist takes an X-ray and says: there is a cavity on tooth 7. The dentist can fix it — but if you had a specialist issue, they would refer you to the right person. The X-ray is the valuable part. Without it, the cavity grows until you are in pain and the fix is ten times more expensive."

**Why it works for Danes:** Dental care is familiar, structured, and respected. Danish dental practice explicitly separates diagnosis from treatment referral. The cost escalation argument — a small problem today becomes an expensive emergency tomorrow — is concrete and non-threatening.

### The Bilsyn (Vehicle Inspection — MOT)

> "Every two years, your car goes to syn. The mechanic checks brakes, lights, emissions, and gives you a list: these three things need fixing before you pass. The mechanic does not fix them — your regular vaerksted does. But without the syn, you would not know your brake pads were down to 2mm until they failed."

**Why it works for Danes:** Bilsyn (vehicle inspection) is mandatory, familiar, and nobody questions the model. The inspection station identifies; the garage repairs. It is the closest structural analogy to Heimdall's business model. Every Danish business owner has been through this process personally.

### The Tyverialarm (Burglar Alarm)

> "Your alarm system monitors your restaurant at night. If someone breaks a window, it alerts you and calls the police. The alarm does not board up the window — you call a glazier for that. But you sleep better knowing someone is watching."

**Why it works for Danes:** Security monitoring is a pure watch-and-alert service. Nobody expects their alarm company to also repair break-in damage. The analogy maps perfectly to Heimdall's model and is immediately intuitive.

### The Revisor (Accountant/Auditor)

> "Your revisor goes through your books and says: here is a discrepancy, here is a tax risk, here is a deadline you are about to miss. They tell you what to do about it. But they do not log into your bank and move the money — that is your job, and for good reason."

**Why it works for Danes:** Every Danish business has a revisor. The revisor's authority comes from oversight and expertise, not from executing transactions. The "for good reason" framing reinforces that the separation is a feature, not a limitation.

---

## 4. Pre-Emptive Messaging

The best way to handle the remediation objection is to prevent it from forming. Every customer touchpoint before and during the first month must set the expectation clearly.

### First finding free (outreach stage)

When sharing the first finding with a prospect, include the role framing naturally:

> "Vi har koert et sikkerhedstjek af [domain]. Vi fandt [finding in plain language]. Hvis du vil vide mere, sender jeg gerne en komplet oversigt med trinvise anvisninger til din webudvikler."

Translation: "We ran a security check on [domain]. We found [finding]. If you want to know more, I'll send you a full overview with step-by-step instructions for your web developer."

The phrase "instructions for your web developer" sets the model immediately: Heimdall finds and explains, someone else fixes.

### Subscription page / onboarding copy

Before they pay, the value proposition must be explicit about what they get and what they do not get:

> **Hvad du faar med Sentinel:**
> - Daglig overvaagning af din hjemmesides sikkerhed
> - Besked paa Telegram naar noget kraever din opmaerksomhed
> - Trin-for-trin vejledning du kan sende direkte til din webudvikler
> - Bekraeftelse naar problemet er loest
>
> **Hvad Sentinel IKKE er:**
> - Vi logger ikke ind paa din hjemmeside
> - Vi foretager ikke aendringer paa din server
> - Vi er din digitale vagt — ikke din IT-afdeling

Translation of the "what Sentinel is NOT" section: We do not log into your website. We do not make changes on your server. We are your digital watchman — not your IT department.

The "what it is NOT" framing is critical. It is honest, it is Danish (directness is valued), and it prevents the expectation gap from forming.

### First Telegram message framing

The very first alert a new customer receives should reinforce the model:

> "Hej [navn] — velkommen til Heimdall. Jeg holder fra nu af oje med [domain] hver dag. Naar jeg finder noget, faar du en besked her med en klar forklaring og en opskrift paa loesningen, som du kan sende videre til den der passer din hjemmeside. Lad os komme i gang."

Translation: "Hi [name] — welcome to Heimdall. From now on, I'm watching [domain] every day. When I find something, you'll get a message here with a clear explanation and a recipe for the fix that you can forward to whoever maintains your website. Let's get started."

Key phrase: "en opskrift paa loesningen" (a recipe for the fix). This frames the fix instruction as the deliverable — concrete, complete, actionable. The word "opskrift" (recipe) is deliberate: it implies something anyone can follow, step by step.

---

## 5. Escalation Path Messaging

When a customer is actively frustrated — they have received findings but feel nothing is getting fixed.

### Stage 1: Mild frustration

Customer says something like: "I keep getting these messages but nothing changes."

**Response framework:**

> "Jeg kan godt forstaa frustrationen. Lad mig hjaelpe dig med at komme videre. Problemet med [finding] kraever at [who] goer [what]. Jeg har skrevet en besked du kan sende direkte til dem — skal jeg sende den her, saa du bare kan videresende den?"

Translation: "I understand the frustration. Let me help you move forward. The problem with [finding] requires [who] to do [what]. I've written a message you can send directly to them — shall I send it here so you can just forward it?"

**What this does:** It acknowledges the feeling without being defensive. It identifies the specific bottleneck (the customer has not acted on the instructions, or the third party has not responded). It offers to reduce friction further by drafting the actual message to the web developer or hosting provider.

### Stage 2: Active frustration

Customer says something like: "I'm paying 399 kr. and my website still has problems. What's the point?"

**Response framework:**

> "Du har ret i at [finding] stadig er aabent. Det er et problem. Lad os finde ud af hvad der blokerer — er det din webudvikler der ikke har svaret, eller er du usikker paa hvem der skal kontaktes? Jeg vil gerne hjaelpe dig med at faa det loest, og naar det er fikset, bekraefter jeg det paa naeste scanning saa du kan se det groenne lys."

Translation: "You're right that [finding] is still open. That's a problem. Let's figure out what's blocking — is it your web developer who hasn't responded, or are you unsure who to contact? I want to help you get it resolved, and when it's fixed, I'll confirm it on the next scan so you can see the green light."

**What this does:** It validates the frustration ("you're right, that's a problem"). It diagnoses the bloccker. It points toward the green light loop (see section 6) as the resolution moment.

### Stage 3: Cancellation threat

Customer says: "I want to cancel."

**Response framework:**

> "Det forstaar jeg. Foer du goer det — din hjemmeside har lige nu [N] aabne problemer. Hvis du annullerer, forsvinder de ikke. Du vil bare ikke vide om nye dukker op. Hvis problemet er at du mangler nogen der kan rette tingene, kan jeg anbefale en lokal webudvikler der kender dit system. Det er din beslutning."

Translation: "I understand. Before you do — your website currently has [N] open issues. If you cancel, they don't go away. You just won't know when new ones appear. If the problem is that you need someone who can fix things, I can recommend a local web developer who knows your system. It's your decision."

**What this does:** No pressure. States facts. Offers a concrete solution to the underlying problem (they need a web developer, not a different monitoring service). Ends with "it's your decision" — respecting Danish autonomy and avoiding any hint of manipulation.

**The web developer referral is a retention strategy.** If the customer's real problem is that they have no one to execute fixes, connecting them with a developer solves the root cause and makes the monitoring service valuable again. Consider maintaining a list of reliable local web developers for referral. This is also a potential partner channel.

---

## 6. The Green Light Loop

The most powerful retention mechanism is not finding problems — it is confirming that problems are gone.

### The concept

When Heimdall detects a finding, it is flagged as open. When the customer (or their developer) fixes it, the next scan confirms the fix and the finding moves to resolved. The customer receives a confirmation message:

> "Godt nyt — [finding] paa [domain] er nu loest. Det fangede vi paa dagens scanning. Et problem mindre at taenke paa."

Translation: "Good news — [finding] on [domain] is now resolved. We caught it on today's scan. One less thing to worry about."

### Why this is the retention hook

The green light message is the moment where the customer feels the value of the subscription. It closes the loop:

1. Heimdall finds a problem (creates anxiety)
2. Customer or developer fixes it (takes action)
3. Heimdall confirms the fix (resolves anxiety)
4. Customer feels: "this is working"

Without step 3, the cycle is incomplete. The customer is left wondering: did the fix actually work? Is my site safe now? The green light message answers both questions and delivers the emotional payoff.

### Framing for the subscription pitch

The green light loop is the strongest argument against the "you don't fix anything" objection:

> "Du betaler ikke for at vi finder problemer. Du betaler for at vi bekraefter at de er vaek. Naar din webudvikler har rettet noget, fortaeller vi dig: det virkede, din hjemmeside er sikker paa det punkt. Det er den tryghed du betaler for."

Translation: "You're not paying for us to find problems. You're paying for us to confirm they're gone. When your web developer has fixed something, we tell you: it worked, your website is secure on that point. That's the peace of mind you're paying for."

### The progress narrative

Over time, the customer accumulates a history of resolved findings. This creates a progress narrative that reinforces the value:

> "Siden du startede med Heimdall, har vi identificeret 7 sikkerhedsproblemer paa [domain]. 5 er loest. 2 er aabne. Her er status:"

Translation: "Since you started with Heimdall, we've identified 7 security issues on [domain]. 5 are resolved. 2 are open. Here's the status:"

This scorecard framing turns Heimdall from a bearer of bad news into a partner in continuous improvement. The ratio of resolved to open findings is a tangible measure of progress.

---

## 7. Key Phrases — Danish Translations

Ready-to-use phrases for Telegram messages, onboarding, and conversation.

### Setting expectations

| Danish | English | When to use |
|--------|---------|-------------|
| "Jeg holder oje med din hjemmeside udefra" | "I watch your website from the outside" | First contact — establishes the monitoring model |
| "En opskrift paa loesningen" | "A recipe for the fix" | Describing what the alert contains |
| "Trin-for-trin vejledning til din webudvikler" | "Step-by-step instructions for your web developer" | Subscription page, onboarding |
| "Din digitale vagt — ikke din IT-afdeling" | "Your digital watchman — not your IT department" | Onboarding, expectation setting |
| "Af hensyn til din sikkerhed logger vi aldrig ind paa dit system" | "For your security, we never log into your system" | When explaining why Heimdall cannot fix |

### Delivering findings

| Danish | English | When to use |
|--------|---------|-------------|
| "Vi har fundet noget der kraever din opmaerksomhed" | "We found something that needs your attention" | Alert opening |
| "Her er hvad det betyder for din forretning" | "Here's what it means for your business" | Plain-language explanation |
| "Her er hvad din webudvikler skal goere" | "Here's what your web developer needs to do" | Fix instructions (Sentinel) |
| "Send denne besked videre til [webudvikler/hostingudbyder]" | "Forward this message to [developer/hosting provider]" | Actionable next step |

### Confirming fixes

| Danish | English | When to use |
|--------|---------|-------------|
| "Godt nyt — [problem] er nu loest" | "Good news — [problem] is now resolved" | Green light confirmation |
| "Det fangede vi paa dagens scanning" | "We caught it on today's scan" | Proof that monitoring works |
| "Et problem mindre at taenke paa" | "One less thing to worry about" | Emotional payoff |
| "[N] ud af [M] problemer er loest" | "[N] out of [M] issues are resolved" | Progress scorecard |

### Handling frustration

| Danish | English | When to use |
|--------|---------|-------------|
| "Jeg kan godt forstaa frustrationen" | "I understand the frustration" | Acknowledgment, never defensive |
| "Lad os finde ud af hvad der blokerer" | "Let's figure out what's blocking" | Diagnosing the bottleneck |
| "Skal jeg skrive en besked du kan sende til dem?" | "Shall I write a message you can forward to them?" | Reducing friction |
| "Det er din beslutning" | "It's your decision" | Respecting autonomy, always close with this |

---

## Summary: The Five Things Every Customer Must Understand

Before their first alert arrives:

1. **Heimdall watches from the outside** — like a building inspector, not a contractor
2. **Fixes require system access that Heimdall does not have** — and should not have
3. **Every alert comes with a recipe** — step-by-step instructions they can forward
4. **Heimdall confirms when the fix works** — the green light is the payoff
5. **The value is continuous vigilance** — not a one-time repair

If these five points are clear before the first finding lands in their Telegram, the remediation objection will not form.
