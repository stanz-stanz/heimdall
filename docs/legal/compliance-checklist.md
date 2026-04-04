# Heimdall Compliance Checklist

Maintained by Valdí (Legal Compliance Agent).

---

## Per-Client Onboarding

- [ ] Written scanning authorisation obtained
- [ ] Authorised domains explicitly listed
- [ ] Layer scope confirmed (Layer 1 only / Layer 1+2)
- [ ] Authorising person confirmed as domain owner or authorised representative
- [ ] Consent document stored securely
- [ ] Data processing agreement (DPA) signed if processing personal data

## Per-Scan-Type Registration

- [ ] Function submitted to Valdí for Gate 1 review
- [ ] Forensic log entry created (approval or rejection)
- [ ] Approval token generated and recorded
- [ ] Scan type registered in the scan type registry
- [ ] Function handles robots.txt denial correctly
- [ ] Operator (Federico) has reviewed Valdí's reasoning and confirmed

## Per-Scan Execution

- [ ] Approval token for scan type is valid and current
- [ ] Target domain's consent state determined
- [ ] Scan type Layer does not exceed what target's consent state permits
- [ ] No Layer 3 activity in scan profile
- [ ] robots.txt does not deny automated access for this target
- [ ] Pre-scan check logged to the compliance audit trail
- [ ] For consented targets: authorisation file exists, is not expired, and domain is in scope
- [ ] For consented targets: consent document on file at referenced path

## Data Handling

- [ ] Scan results stored with access controls
- [ ] Client data retention policy documented
- [ ] No scan data shared with third parties without consent
- [ ] Data deletion process documented for client offboarding

## Open Questions for Legal Counsel

All open legal questions (16 total — outreach, scanning, consent, GDPR) are consolidated in `docs/legal/legal-briefing-outreach-2026-03-29.md`. That document is the single source of truth for the lawyer meeting.
