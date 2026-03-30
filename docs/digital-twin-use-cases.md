# Digital Twin — Use Cases

The digital twin reads a prospect brief JSON and spins up a local website that replicates the prospect's technology stack: CMS version, plugin versions, missing security headers, exposed version strings. It runs as a Docker container on our infrastructure.

**Legal foundation:** Scanning the twin is scanning our own infrastructure. Straffeloven §263 applies to unauthorized access to *another person's data system*. The twin is ours. The consent framework applies only when contacting the prospect's actual servers. Valdí Gate 1 scan-type validation still applies — the *tool* must be approved regardless of target.

---

## Use Case 1: Layer 2 Scanning Without Consent

**The problem:** Without written consent, we can only run Layer 1 passive scans against a prospect's real website. This limits findings to missing headers, exposed versions, and plugin detection. The highest-value findings — specific CVEs, known vulnerable plugin versions, WordPress misconfigurations — require Layer 2 tools (Nuclei, WPScan) which require written consent.

**The solution:** Build a twin from the Layer 1 brief. Run Nuclei and WPScan against the twin. The twin has the same WordPress version, the same plugin versions, the same missing headers. Layer 2 tools will surface the same CVEs and vulnerability matches they would find on the real site.

**What this produces:**
- Specific CVE identifiers for the detected WordPress version
- Known vulnerabilities in the exact plugin versions detected (e.g. Gravity Forms 26.9, Yoast SEO 26.9)
- WPScan vulnerability database matches for every detected plugin
- Nuclei template matches for exposed endpoints (/xmlrpc.php, /wp-json/, /readme.html)

**Accuracy constraint:** Findings are only as accurate as the Layer 1 brief. If webanalyze misidentifies a plugin version, the twin will carry that error forward. This is documented in the output — findings from twin scans are marked as *derived from passive fingerprinting*, not confirmed against the live target.

**When:** Every prospect scan. After the Layer 1 brief is generated, the twin is built and Layer 2 tools run automatically as a pipeline extension.

---

## Use Case 2: Sales — Pre-Consent Vulnerability Report

**The problem:** The initial prospect outreach ("here's what we found on your website") is currently limited to Layer 1 observations: missing headers, exposed versions, plugin counts. These are real findings, but they lack the urgency of specific vulnerabilities.

**The solution:** The twin-derived Layer 2 findings transform the sales brief. Instead of "WordPress version 6.9.4 is publicly disclosed", the report can say "WordPress 6.9.4 has 3 known CVEs affecting your version" with specific references.

**What changes in the outreach:**
- Findings move from "you're missing a header" to "this specific vulnerability exists in your plugin version"
- CVE references add credibility and urgency
- The prospect sees the depth of analysis possible *before* signing a consent agreement
- The consent agreement itself becomes easier to justify: "we've already found X at the surface level — with your permission, we can confirm and go deeper"

**When:** During prospect outreach, as part of the initial brief delivery.

---

## Use Case 3: Pipeline Regression Testing

**The problem:** When scanner code changes (refactored header checks, updated webanalyze parsing, new Nuclei templates), there's no way to verify the pipeline still detects what it should. Real websites change unpredictably — a target might fix their headers between test runs, making before/after comparison impossible.

**The solution:** The twin is deterministic. Same brief, same responses, every time. A test suite can:
1. Spin up a twin from a known brief
2. Run the pipeline against it
3. Assert the output brief matches a baseline fixture
4. Fail the PR if any expected finding disappears

**What this catches:**
- Regressions in header detection logic
- Broken regex patterns in `_extract_page_meta`
- webanalyze/httpx output format changes after tool upgrades
- Nuclei template updates that drop previously-matched findings

**When:** CI pipeline on every PR that touches `src/prospecting/`, `src/worker/`, scan config, or tool versions.

---

## Use Case 4: New Tool Onboarding

**The problem:** When adding a new scanning tool (as with Nuclei in Sprint 3.2, WPScan next), there's no safe target to validate it against. Running untested tool configurations against real websites risks unexpected behaviour, rate-limit violations, or legal exposure.

**The solution:** The twin is a controlled environment. Configure the new tool, run it against the twin, inspect the output. Iterate on configuration (excluded tags, rate limits, output format parsing) without touching a real target.

**What this enables:**
- Validate Nuclei template selections produce expected findings
- Test WPScan output parsing against a known WordPress installation
- Verify rate-limiting and timeout configurations work correctly
- Confirm the tool respects robots.txt and other compliance gates

**When:** Each time a new scanning tool is added to the pipeline, or when updating tool versions/configurations.

---

## Use Case 5: Remediation Verification

**The problem:** When Heimdall offers remediation guidance ("add HSTS header", "update Yoast SEO to version 27.x"), there's currently no way to demonstrate that the fix actually resolves the finding — short of re-scanning the client's live site after they've applied it.

**The solution:** Mutate the brief to reflect the remediation, rebuild the twin, re-scan. The finding should disappear. This can be done *before* the client applies the fix, as a preview: "here's what your scan report will look like after you apply these three changes."

**What this enables:**
- Before/after comparison without touching the live site
- Demonstration to the client that a specific fix resolves a specific finding
- Prioritisation guidance: "fixing these 2 items removes 5 of your 9 findings"
- QA for the Finding Interpreter: verify that resolved findings are correctly excluded from the updated report

**When:** Post-pilot, when Heimdall offers remediation services. The twin infrastructure is already in place — this use case requires no additional code, only brief mutation.

---

## Use Case 6: Finding Interpreter Training

**The problem:** The Finding Interpreter (Claude API / Ollama) generates plain-language reports from raw scan data. Testing it requires known-good scan inputs with expected outputs. Using real scan data means the input changes every time the target website changes.

**The solution:** The twin produces deterministic scan inputs. Run the pipeline against the twin, capture the raw findings, feed them to the Finding Interpreter. Compare the interpretation output against a baseline. This validates that interpreter prompt changes or model upgrades don't degrade output quality.

**What this enables:**
- Stable test fixtures for interpreter prompt engineering
- A/B testing of different Claude models or Ollama models against identical inputs
- Regression testing when interpreter prompts change
- Validation that the interpreter correctly handles edge cases (e.g. no findings, all-critical findings)

**When:** Each time the interpreter prompts, model selection, or tone configuration changes.

---

## Implementation

The twin runs as a Docker Compose profile:

```bash
# Start twin for a specific prospect
BRIEF_FILE=/config/conrads.dk.json docker compose -f infra/docker/docker-compose.yml --profile twin up --build twin

# Or via convenience script
./tools/twin/run.sh conrads.dk.json

# Run Layer 2 tools against it
httpx -u https://localhost:9443 -json -tech-detect -tls-no-verify
nuclei -u https://localhost:9443 -severity low,medium,high,critical -tls-no-verify
wpscan --url https://localhost:9443/ --disable-tls-checks --format json
```

For pipeline integration testing with SSL trust:
```bash
docker cp heimdall-twin-1:/home/heimdall/.certs/cert.pem /tmp/twin-cert.pem
SSL_CERT_FILE=/tmp/twin-cert.pem python -m src.prospecting.main
```

Source: `tools/twin/` — templates, server, tests, slug mapping.
Docker: `infra/docker/Dockerfile.twin` — python:3.11-slim, self-signed cert at build time.
Compose: `infra/docker/docker-compose.yml` — profile `["twin"]`, ports 9080/9443.
