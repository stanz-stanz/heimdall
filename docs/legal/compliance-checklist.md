# Heimdall Compliance Checklist

Maintained by Valdi (Legal Compliance Agent). See `docs/agents/legal-compliance/SKILL.md` for full context.

---

## Per-Client Onboarding

- [ ] Written scanning authorisation obtained
- [ ] Authorised domains explicitly listed
- [ ] Layer scope confirmed (Layer 1 only / Layer 1+2)
- [ ] Authorising person confirmed as domain owner or authorised representative
- [ ] Consent document stored securely
- [ ] Data processing agreement (DPA) signed if processing personal data

## Per-Scan-Type Registration

- [ ] Function submitted to Valdi for Gate 1 review
- [ ] Forensic log entry created (approval or rejection)
- [ ] Approval token generated and recorded
- [ ] Scan type registered in `data/scan_types.json`
- [ ] Function handles robots.txt denial correctly
- [ ] Operator (Federico) has reviewed Valdi's reasoning and confirmed

## Per-Scan Execution

- [ ] Approval token for scan type is valid and current
- [ ] Target domain's authorisation level determined
- [ ] Scan type Layer does not exceed what target's Level permits
- [ ] No Layer 3 activity in scan profile
- [ ] robots.txt does not deny automated access for this target
- [ ] Pre-scan check logged to `data/compliance/`
- [ ] For Level 1: authorisation file exists, is not expired, and domain is in scope
- [ ] For Level 1: consent document on file at referenced path

## Data Handling

- [ ] Scan results stored with access controls
- [ ] Client data retention policy documented
- [ ] No scan data shared with third parties without consent
- [ ] Data deletion process documented for client offboarding

## Open Questions for Legal Counsel

1. Confirm the Layer 1/Layer 2 boundary under Straffeloven SS263
2. Can a web agency authorise scanning of their clients' sites?
3. Or must each end client consent independently?
4. Does a programmatic compliance layer (Valdi) with forensic logs reduce liability for inadvertent boundary crossings?
5. What audit trail documentation would a court expect to see?
6. Recommended firms: Plesner, Kromann Reumert, Bech-Bruun
