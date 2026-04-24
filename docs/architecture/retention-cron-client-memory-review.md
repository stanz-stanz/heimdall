# Retention-Execution Cron — Client-Memory Semantic Review

**Date:** 2026-04-24
**Reviewer:** Client Memory agent
**Scope:** §3 (anonymise) + §4 (purge cascade) of `docs/architecture/retention-cron-options.md`.
**Locked upstream (do not relitigate):** Q2 tombstone, Q3 null-at-anonymise, Q4 alert channel.

---

## Agreement

- Tombstone shape: keep `clients` row, null PII, `company_name='[purged]'`, `data_retention_mode='purged'` (§4). Matches Q2.
- `cvr`, `company_name`, `industry_code`, `plan`, `gdpr_sensitive`, `gdpr_reasons`, `trial_started_at`, `trial_expires_at`, `signup_source`, `churn_reason`, `churn_requested_at`, `churn_purge_at` preserved at anonymise — all non-PII funnel/audit. Correct.
- `clients.telegram_chat_id`, `contact_name`, `contact_email`, `contact_phone`, `contact_role`, `developer_contact`, `next_scan_date`, `notes` → NULL at anonymise. Correct PII set.
- `consent_records.authorised_by_name`, `authorised_by_email`, `notes` → NULL at anonymise; `consent_document`, `consent_date`, `consent_expiry`, `authorised_domains`, `authorised_by_role` preserved as Bogføringsloven/§263 evidence. Correct.
- `delivery_log.message_preview`, `external_id`, `error_message` → NULL at anonymise; timing columns preserved for funnel. Correct.
- `conversion_events.payload_json` and `onboarding_stage_log.note` → NULL at anonymise. Correct.
- `subscriptions` + `payment_events` untouched at anonymise for both tiers (5yr Bogføringsloven). Correct.
- Watchman purge keeps `clients` + `client_domains.domain` (public CVR+domain data), deletes all scan/finding/brief/cert/signup/delivery rows. Cascade order is correct.
- Purge step preserves the currently-executing `retention_jobs` row (§4 line `id != :current_job_id`). Correct self-preservation.

---

## Corrections

1. **`scan_history.result_json` — architect says "defer to purge" (§3 line 146, confidence paragraph, §9 Q4). I say: null at anonymise.** Plan reference: Federico locked Q3 explicitly — `scan_history.result_json` and `brief_snapshots.brief_json` are in the null-at-anonymise set. The architect's "replay archive" argument is overridden. Implementation: at anonymise, `UPDATE scan_history SET result_json=NULL WHERE cvr=?;` — keep the row (timing/scan_id is funnel-useful), scrub the scraped content.

2. **`brief_snapshots.brief_json` — architect says "defer to purge". I say: null at anonymise.** Same Q3 reasoning. `UPDATE brief_snapshots SET brief_json=NULL WHERE cvr=?;` — keep the row skeleton, scrub the scraped content. This is the conservative GDPR posture Federico picked.

3. **`client_cert_snapshots` / `client_cert_changes` — architect says "keep intact until purge" (§3 line 140). I say: preserve structure, null PII-shaped fields at anonymise, full purge at 1yr / 5yr.** Plan reference: these rows are §263 evidence under Sentinel (`authorisation_revoked` row 7 in the 7-row audit trail references what we monitored). Specifically:
   - Keep `cvr`, `domain`, `cert_sha256`, `issuer_name`, `not_before`, `not_after`, `first_seen_at`, `last_seen_at`, `change_type`, `detected_at`, `status`.
   - Null `dns_names_json` and `details_json` at anonymise — SANs may contain customer-specific subdomains (`kunde-navn.domain.dk`) that leak third-party PII.
   - Architect's §3 omission is material: both tables are entirely absent from the "Anonymise sequence" SQL block (§3 line 160+).

4. **`consent_records.status='revoked'` — architect sets this at anonymise (§3 line 165).** Fine, but flag: this MUST happen AFTER the 7th audit-trail row (`authorisation_revoked`) is written — otherwise the audit trail is incomplete. See "Open questions" #1.

5. **`clients.consent_granted = 0` — architect sets at anonymise (§3 line 71).** Correct, but this should also be set at offboarding_trigger time (Step 1 of the offboarding flow), not only 30/90 days later at anonymise. Otherwise Valdí Gate 2 would keep permitting Layer-2 scans for 30–90 days after cancellation. Flag to architect: this belongs in the offboarding handler, not the anonymise job.

---

## Additions

1. **`signup_tokens` — missing from anonymise sequence.** Plan schema §"Schema additions" lists this table. Magic-link tokens are dead once consumed, but an unconsumed `signup_tokens` row for an offboarded CVR is a PII-adjacent artifact (it ties back to the contact email). At anonymise: `DELETE FROM signup_tokens WHERE cvr=?;` (tokens are ephemeral, 30-min TTL, nothing to anonymise; delete outright). Architect's purge cascade already includes this at §4 line 202 — just needs mirroring at anonymise.

2. **`delivery_retry` — missing from anonymise.** Rows hang off `delivery_log.id`. If `delivery_log` survives anonymise (it does, timing kept), `delivery_retry` is retained too. That's fine, but `delivery_retry.last_error` may quote message content. Add to anonymise: `UPDATE delivery_retry SET last_error=NULL WHERE delivery_log_id IN (SELECT id FROM delivery_log WHERE cvr=?);`.

3. **`authorisation.json` file on disk — architect §3 line 116 mentions `consent_document` PDF path preserved but does not mention the Valdí authorisation.json file.** Per `src/consent/validator.py` this is read by Gate 2. Anonymise should leave it (Bogføringsloven evidence), purge should delete it alongside the signed PDFs. Flag for architect: the purge SQL cascade is DB-only; the filesystem side needs a parallel step.

4. **Watchman purge — `subscriptions` / `payment_events` correctly skipped.** Architect does this right (§4 line 238 cascade omits them). Explicit note for verification: Watchman clients have **zero** `subscriptions` / `payment_events` rows by definition (free trial), so the skip is belt-and-braces. Test `TestWatchmanLeavesBookkeeping` (§8) confirms the invariant.

---

## Compromises

None. The architect's §3/§4 disagreements resolve against the locked decisions (Q3 wins on scan_history/brief_snapshots; cert tables are an omission, not a disagreement). No middle ground needed.

---

## Open questions for Federico

1. **Consent-audit-trail sequencing vs. anonymise.** The 7-row audit trail ends with `offboarding_triggered` (row 6) and `authorisation_revoked` (row 7). Row 7 is written at anonymise time. The architect's anonymise SQL sets `consent_records.status='revoked'` in the same transaction — but if row 7 is *itself* a `consent_records` insert (one interpretation of the plan), then the transaction order must be: `INSERT row-7 → UPDATE status='revoked' on prior rows → NULL authorised_by_name/email on all rows`. If row 7 lives elsewhere (e.g., `conversion_events` with `event_type='authorisation_revoked'`), no race. **Question: where does the 7-row audit trail physically live?** The plan says `consent_records` (7 rows per onboarding) but the current schema treats `consent_records` as state, not an event log. This is an architect question more than mine, but it blocks the anonymise SQL.

2. **Watchman-that-never-converted: does row 7 get written?** A Watchman trialist has no Layer-2 authorisation to revoke. Does the 7-row audit trail apply to Watchman, or is it Sentinel-only? If Sentinel-only, Watchman anonymise skips the row-7 step entirely. Plan §"Consent audit trail" doesn't disambiguate. (My read: Sentinel-only, because rows 1–5 reference PDFs and Gate 2, which Watchman never has. Confirm.)
