# Pipeline Analysis — 1,173 Danish SMB Websites

**Date:** 2026-04-05
**Methodology:** Passive observation of publicly accessible information — HTTP headers, HTML source, DNS records, SSL certificates, and technology fingerprinting. No active probing, no authentication, no exploitation. The same information available to any browser visit.

*Some findings are identified by matching detected software versions against published security databases. A deeper, consent-based scan is required to confirm whether these apply to a specific site's configuration.*

---

## What We Found

**14,699 findings across 1,173 sites. Average: 12.5 per site. 96.7% of sites have at least one finding.**

| Severity | Findings | Sites affected |
|----------|----------|----------------|
| Critical | 459 (3.1%) | 393 (33.5%) |
| High | 931 (6.3%) | 299 (25.5%) |
| Medium | 8,886 (60.5%) | 973 (82.9%) |
| Low | 3,582 (24.4%) | 1,129 (96.2%) |

49.3% of sites have at least one Critical or High severity finding.

## Technology Landscape

WordPress is the dominant platform at 37.5% of sites (440), followed by no-CMS/custom builds (53.5%), Wix (2.0%), and Shopify (1.9%).

WordPress sites account for the majority of findings — 27.3 average findings per site versus 3.9 for non-CMS sites. The primary driver is plugin sprawl: 6.7 plugins per site on average, 90.2% running versions with published security advisories, 71.4% running outdated plugins.

Most commonly affected plugins: WooCommerce (40.7% of WP sites), Elementor (45.2%), Yoast SEO (59.1% — most commonly outdated at 177 sites).

## Security Headers

| Header | Adoption |
|--------|----------|
| X-Content-Type-Options | 30.4% |
| HSTS | 22.9% |
| X-Frame-Options | 16.2% |
| Content Security Policy | 9.0% |

60.4% of sites deploy none of the four core security headers. 6.6% deploy all four.

## SSL/TLS

79.4% have valid SSL certificates. 20.6% (242 sites) serve content over unencrypted HTTP. Of those with SSL, 83.1% use Let's Encrypt with an average 68 days until expiry.

## GDPR Exposure

46.5% of sites handle personal data — online shops, booking forms, analytics tracking. These sites average 19.6 findings versus 6.4 for brochure-only sites. The most common data-handling technologies: Google Analytics/GTM (34.4%), WooCommerce (15.4%), Contact Form 7 (8.2%).

---

## In Plain Language — What This Means for Business Owners

We visited 1,173 Danish business websites — the same way a customer or a search engine would. We didn't try to break in. We just looked at what's visible to everyone. Here's what we found.

**Your website tells visitors what software it runs.** Nearly half of the sites we checked openly display their backend technology, version numbers, and plugin list. That information is meant for developers, but it's readable by anyone. It tells a knowledgeable visitor exactly which published security advisories may apply to your site.

**Most WordPress sites haven't been updated.** 7 out of 10 WordPress sites run plugins with available updates. Each outdated plugin has a public record of known issues — the same records security researchers and automated scanning tools reference daily. Whether each issue affects your specific site depends on your configuration, but the outdated version is visible to anyone who looks.

**1 in 5 sites doesn't encrypt its traffic.** 242 businesses serve their website without HTTPS. Contact form submissions, login credentials, booking details — transmitted in plain text. Browsers already warn visitors about this with a "Not Secure" label.

**60% of sites use none of the standard browser protections.** Content Security Policy, HSTS, clickjacking prevention — these are built into modern browsers at no cost. They reduce the risk of common attacks. 708 sites haven't enabled a single one.

**The sites that handle the most customer data have the most findings.** Sites with online shops, booking systems, and visitor tracking have three times more findings than simple informational sites. The correlation is consistent across industries.

**Most of this goes unnoticed.** Small business breaches are rarely dramatic. Customer data copied quietly, SEO spam injected where only Google sees it, checkout page modifications that skim payment details. The typical business owner finds out from a customer complaint, a Google ranking drop, or a letter from Datatilsynet — not from a warning on their screen.

---

## Market Implications (SIRI context)

**The gap is measured, not projected.** 1,173 Danish SMB websites analysed in a single automated batch. 49.3% with Critical or High findings. 60.4% with zero security headers. These are not survey estimates — they are direct observations from publicly accessible data.

**Our data reinforces the government's concern.** Styrelsen for Samfundssikkerhed estimates that 40% of Danish SMBs do not have a security level matching the threats they face. Our scan data is consistent with that assessment — 96.7% of sites have at least one finding, and 49.3% have findings rated Critical or High. The tools to detect these issues exist; the challenge the government has identified is getting them into SMB hands.

**Enterprise tools exist. SMB-priced tools do not.** External Attack Surface Management solutions like Outpost24 serve this market at 40,000-100,000 kr./year. A carpenter in Vejle with a WordPress booking plugin will not pay that. The technology to detect these issues at scale exists — what's missing is a delivery model that works at SMB price points.

**The pipeline scales without manual intervention.** 1,173 sites, 14,699 findings, classified by severity, mapped to published advisories, ready for plain-language interpretation. No analyst sat in front of a screen. The bottleneck in SMB cybersecurity is not detection — it is reaching the businesses that need it, in language they understand, at a price they can justify.
