# Sample Prospect Brief — Anonymized

**Purpose:** This is a real scan output from Heimdall's Layer 1 pipeline, anonymized for the lawyer meeting. It demonstrates what Heimdall collects from a single passive scan and how findings are structured. All data was obtained by reading publicly served information — no crafted probes, no login attempts, no port scanning.

**Source:** Heimdall pipeline output (domain name, IP addresses, and identifiable details replaced)

---

## Brief: example-restaurant.dk

```json
{
  "domain": "example-restaurant.dk",
  "cvr": "prospect",
  "company_name": "[Anonymized — Danish restaurant/hotel in Vejle area]",
  "scan_date": "2026-03-29",
  "bucket": "A",
  "gdpr_sensitive": true,
  "gdpr_reasons": [
    "Data-handling plugins: WooCommerce, Contact Form 7",
    "E-commerce plugin: WooCommerce:9.6.4"
  ],
  "industry": "",
  "technology": {
    "cms": "WordPress",
    "hosting": "LiteSpeed",
    "ssl": {
      "valid": true,
      "issuer": "Sectigo Limited",
      "expiry": "2027-01-21",
      "days_remaining": 298
    },
    "server": "LiteSpeed",
    "detected_plugins": [
      "Instagram Feed",
      "Elementor",
      "WooCommerce",
      "Cookie Law Info",
      "Contact Form 7",
      "Custom Facebook Feed"
    ],
    "headers": {
      "x_frame_options": false,
      "content_security_policy": false,
      "strict_transport_security": false,
      "x_content_type_options": false
    }
  },
  "tech_stack": [
    "Bootstrap",
    "Contact Form 7:6.0.3",
    "CookieYes:3.2.8",
    "Elementor:3.27.3",
    "HTTP/3",
    "LiteSpeed",
    "LiteSpeed Cache",
    "MySQL",
    "PHP",
    "WooCommerce:9.6.4",
    "WordPress:6.9.4",
    "Yoast SEO:24.5",
    "jQuery"
  ],
  "subdomains": {
    "count": 0,
    "list": []
  },
  "dns": {
    "a": ["[IP redacted]"],
    "aaaa": [],
    "cname": [],
    "mx": ["[redacted].mail.protection.outlook.com"],
    "ns": ["ns1.[hosting-provider].dk", "ns2.[hosting-provider].dk"],
    "txt": ["v=spf1 include:spf.protection.outlook.com -all"]
  },
  "cloud_exposure": [],
  "findings": [
    {
      "severity": "medium",
      "description": "Missing HSTS header (HTTP Strict Transport Security)",
      "risk": "Browsers are not instructed to always use HTTPS. On unsecured networks (public WiFi), a visitor's first connection could be intercepted before the redirect to HTTPS occurs."
    },
    {
      "severity": "low",
      "description": "Missing Content-Security-Policy header",
      "risk": "The browser has no restrictions on which scripts can run on the page. If the site is compromised, injected scripts can operate without constraint."
    },
    {
      "severity": "low",
      "description": "Missing X-Frame-Options header",
      "risk": "The website can be embedded in frames on other sites. This enables clickjacking attacks where users interact with hidden elements overlaid on the legitimate page."
    },
    {
      "severity": "low",
      "description": "Missing X-Content-Type-Options header",
      "risk": "Browsers may misinterpret uploaded files as executable content. This is primarily relevant if the site accepts file uploads."
    },
    {
      "severity": "medium",
      "description": "WordPress version 6.9.4 publicly disclosed",
      "risk": "The exact WordPress version is visible to anyone viewing the page source. This allows attackers to look up known vulnerabilities specific to this version and target them directly."
    },
    {
      "severity": "medium",
      "description": "Data-handling plugins detected: WooCommerce, Contact Form 7",
      "risk": "These plugins collect or process user data (form submissions, bookings, payments). If the site or plugin has a vulnerability, this data could be exposed. Keeping these plugins updated is critical for GDPR compliance."
    },
    {
      "severity": "info",
      "description": "6 WordPress plugins detected",
      "risk": "Each plugin is additional code from a third-party developer. Outdated or abandoned plugins are a common entry point for attackers. Plugins should be reviewed and kept updated."
    },
    {
      "severity": "low",
      "description": "Backend technology exposed: MySQL, PHP",
      "risk": "The server advertises which backend technologies it runs. This gives attackers information about which exploits may be applicable."
    }
  ]
}
```

---

## What This Demonstrates

**Data collection method:** Every data point in this brief was obtained by Layer 1 (passive) scanning — reading the HTTP response headers, HTML source, DNS records, and SSL certificate that the server voluntarily sends to any visitor. This is the same information a browser receives when visiting the website.

**Bucket classification:** This site is Bucket A (self-hosted WordPress with findings). Bucket A prospects are the highest priority for outreach because they have the most actionable findings.

**GDPR sensitivity:** Flagged as GDPR-sensitive because the site runs WooCommerce (e-commerce — processes payment and customer data) and Contact Form 7 (collects form submissions including personal data).

**Findings structure:** Each finding has a severity level (info/low/medium/high/critical), a description, and a plain-language risk explanation. These findings are what Heimdall would share with the business owner — either in a first-contact letter (one finding) or in a full report (all findings, after onboarding).

**What is NOT in this brief:** No vulnerability IDs (CVEs), no exploitation details, no admin panel status, no login page checks, no port scan results. All of those require Layer 2 scanning with written consent.
