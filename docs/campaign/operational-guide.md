# Campaign Operational Guide

How to run the Heimdall marketing campaign from prospect data to email outreach.

---

## The Flow

```
CVR data (Excel)
    |
    v
[1] Enrich companies (one-time)
    python -m src.enrichment
    -> data/enriched/companies.db (emails, contactable flag, domains)
    |
    v
[2] Run pipeline (one-time)
    python -m src.scheduler --mode prospect
    -> data/output/briefs/{domain}.json (scan results per site)
    |
    v
[3] Promote into campaign
    python -m src.outreach promote --campaign 0426-vejle --bucket A
    -> Loads briefs into prospects table in clients.db
    |
    v
[4] Interpret findings
    python -m src.outreach interpret --campaign 0426-vejle --min-severity high --language da
    -> Claude API translates findings into plain Danish
    |
    v
[5] Export CSV for mail merge
    python -m src.outreach export --campaign 0426-vejle
    -> data/output/campaign-0426-vejle.csv
    |
    v
[6] MANUAL: Import CSV into Brevo, send emails
```

Steps 1-2 are already done for the current dataset. Start from step 3.

---

## Step-by-Step

### Step 3: Promote prospects into a campaign

Select which prospects enter this campaign. Filter by bucket and/or industry.

```bash
# All Bucket A contactable prospects
python -m src.outreach promote --campaign 0426-vejle --bucket A

# Only restaurants (industry code 56*)
python -m src.outreach promote --campaign 0426-vejle --bucket A --industry 56

# Bucket A + B
python -m src.outreach promote --campaign 0426-vejle --bucket A B
```

This is idempotent — running it twice won't create duplicates.

### Step 4: Interpret findings with Claude API

This step costs money (Claude API calls). Use `--dry-run` first to see what would be processed, and `--limit` to control batch size.

```bash
# Preview what would be interpreted (no API calls)
python -m src.outreach interpret --campaign 0426-vejle --dry-run

# Interpret only prospects with high/critical findings, in Danish
python -m src.outreach interpret --campaign 0426-vejle --min-severity high --language da

# Limit to 10 prospects (cost control)
python -m src.outreach interpret --campaign 0426-vejle --min-severity high --language da --limit 10
```

Interpretation results are cached. If two prospects have identical findings, the API is called once.

### Step 5: Export CSV

```bash
# Default output: data/output/campaign-0426-vejle.csv
python -m src.outreach export --campaign 0426-vejle

# Custom output path
python -m src.outreach export --campaign 0426-vejle --output ~/Desktop/vejle-batch1.csv
```

The CSV contains one row per prospect:

| Column | What it is | Used for |
|--------|-----------|----------|
| `domain` | The prospect's website | Email subject line, personalization |
| `company_name` | Business name from CVR | Email greeting |
| `cvr` | CVR number | Reference |
| `email` | Contact email from enriched DB | Send to this address |
| `industry_name` | Business type | Segmentation |
| `bucket` | A/B/C/D/E priority | Batch ordering |
| `finding_count` | Total findings | Context |
| `critical_count` | Critical severity findings | Batch priority (sorted desc) |
| `high_count` | High severity findings | Batch priority |
| `gdpr_sensitive` | yes/no/unknown | Include GDPR paragraph in email? |
| `top_confirmed_finding` | Best Layer 1 fact to lead with | Email 1 main finding (Danish) |
| `interpretation_snippet` | LLM plain-language text | Personalization reference |

Rows are sorted by severity — highest-priority prospects first.

### Step 6: Manual — Import into Brevo and send

1. **Create a Brevo account** (free tier: 300 emails/day — more than enough)
2. **Set up sender domain**: Add heimdall.dk, configure SPF and DKIM records
3. **Create a contact list**: Import the CSV. Map columns to Brevo contact attributes
4. **Create email template**: Use the templates from `docs/campaign/email-and-dm-templates.md`. Map insertion points:
   - `[DOMAIN]` → `domain` column
   - `[COMPANY_NAME]` → `company_name` column
   - `[CONFIRMED_FINDING]` → `top_confirmed_finding` column
   - `[GDPR_CONTEXT]` → conditional block based on `gdpr_sensitive` column
5. **Send Email 1** to Batch 1 (first ~40-50 rows — GDPR-sensitive, highest severity)
6. **Wait 5-7 business days**
7. **Send Email 2** to non-responders (check Brevo open/click stats to identify them)

---

## Batching Strategy

Don't email all 138 prospects at once. Split into 3 batches:

| Batch | Who | When | Size |
|-------|-----|------|------|
| 1 | GDPR-sensitive + high/critical findings + confirmed Layer 1 facts | Weeks 3-4 | ~40-50 |
| 2 | GDPR-sensitive + medium findings | Weeks 5-6 | ~60-70 |
| 3 | Remaining Bucket A | Weeks 7-8 | ~20-30 |

The CSV is already sorted by severity, so Batch 1 = the first ~50 rows.

To export only a specific batch, run promote with tighter filters or manually split the CSV.

---

## Campaign Assets (in this directory)

| File | What |
|------|------|
| `facebook-posts-week1-4.md` | 12 Facebook posts in Danish, ready to copy-paste |
| `email-and-dm-templates.md` | 2 email templates + 3 DM templates, all in Danish |
| `operational-guide.md` | This file |

---

## Timing (8-week plan)

| Weeks | Activity |
|-------|----------|
| 1-2 | Facebook warm-up: create page, post educational content, join local groups |
| 3-4 | Email Wave 1 (Batch 1): Email 1 → wait 5-7 days → Email 2 to non-responders |
| 5-6 | Email Wave 2 (Batch 2) + DM engaged Facebook followers who didn't reply |
| 7-8 | Email Wave 3 (Batch 3) + DM follow-ups + in-person top 5-10 |

Facebook posting continues throughout — 3 posts/week, every Mon/Wed/Fri.
