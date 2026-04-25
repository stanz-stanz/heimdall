# Hetzner Hosting Plan — Heimdall (Pi5 → Hetzner full landing)

**Date:** 2026-04-25 (decisions locked) | **Author:** cloud-devsec | **Status:** ready for commit

## Scope and revision status

This file now includes:

- the original hosting target,
- a repo-grounded architecture review,
- explicit gaps and concerns,
- design optimizations to close those gaps.

The goal is one executable plan, not a draft plus separate review notes.

## Context

Pi5 has been the production scanner host for Heimdall through pilot prep. It is a burning platform: home internet dependency, single host failure mode, no data-center controls, and poor scaling headroom.

The onboarding decisions (D17/D19, 2026-04-23) already selected Hetzner Cloud (Falkenstein/Nurnberg) for EU-resident hosting of signup flows. The short-term target is full stack landing on Hetzner and Pi5 retirement.

## Reviewed and optimized target architecture

```
                                   PUBLIC INTERNET
                                          │
                              ┌───────────┴───────────┐
                              ▼                       ▼
             signup.<heimdall-domain>        api.<heimdall-domain>
                  (signup UX)                (console + webhook ingress)
                              │                       │
                  ┌───────────┴────────┐    ┌─────────┴──────────────┐
                  │ Hetzner CAX11       │    │ Hetzner CAX31           │
                  │ signup box           │    │ backend box             │
                  │ caddy (static SPA)   │    │ caddy + heimdall stack  │
                  │ tailscale            │    │ redis/scheduler/worker  │
                  │                      │    │ api/delivery/prom/graf  │
                  └─────────┬────────────┘    └─────────┬──────────────┘
                            │                           │
                            └──────── Tailscale ────────┘
                                          │
                                          ▼
                              Hetzner Storage Box BX11
                          (off-host SQLite + Redis backups)
```

Key optimization: the backend no longer assumes "same compose and same published ports as Pi5". Public ingress is terminated by Caddy on `443`; operational surfaces stay non-public.

## Critical decisions (locked)

1. Two Hetzner arm64 boxes (CAX11 + CAX31), both in FSN1.
2. Tailscale for operator SSH and east-west trust.
3. SQLite remains primary datastore on backend box.
4. Deployment policy on cloud hosts is immutable pull-by-SHA from GHCR (no local build on prod hosts).
5. Public health contract is `GET /health` for backend API in current codebase.

## Review findings and concern log (documented in-plan)

| ID | Finding | Impact | Resolution in this plan |
|---|---|---|---|
| R1 | Plan used `/healthz` for backend checks while API exposes `/health`. | False outage alarms, failed go-live gates. | Verification and synthetic checks now use `/health`. |
| R2 | Plan claimed backend ingress is `443` only while current compose exposes `8000/8080/3000/9090`. | Unintended internet exposure. | Add backend ingress Caddy and split public vs ops overlays; only `443` public. |
| R3 | Plan specified `payment_events.event_id UNIQUE`; schema has `external_id`, no unique key. | Webhook retries can duplicate events. | `UNIQUE (provider, external_id, event_type)` index on `payment_events` — added in `src/db/migrate.py` as a new migration step. |
| R4 | Plan assumed Prometheus already scrapes node/container endpoints on both hosts. | Missing host metrics and blind spots. | Enable `metrics-addr: 127.0.0.1:9323` and `experimental: true` in `/etc/docker/daemon.json`; Prometheus scrapes `127.0.0.1:9323`. This is the same approach used on Pi5 since 2026-03-27 (decision log: cAdvisor rejected — incompatible with Pi OS overlayfs/containerd snapshotter). Add node exporter targets for both boxes. |
| R5 | Plan stated sink-level PII redaction; current Redis sink forwards raw message/context. | PII leak risk in central logs. | Two-scope fix: (1) sink-level regex redaction in `src/logging/redis_sink.py` for `email`, `cvr`, `telegram_chat_id`, magic-link tokens, and URL paths embedding CVR; (2) caller-side discipline pass on `src/**` to ensure callers log structured `extra={...}` rather than f-string-formatted PII in message strings — sink-level regex cannot strip PII baked into formatted strings. Exclude `consent_records.authorised_by_email` and `consent_records.authorised_by_name` from redaction — Valdí ruled these are §263 forensic evidence and must be preserved. |
| R6 | Deploy model mismatch (current Pi5 aliases build locally; plan assumed pull). | Inconsistent rollback and provenance. | Lock immutable pull-by-SHA policy for Hetzner deploy scripts and runbook. |
| R7 | Pre-push gate extension was ambiguous for two deployment targets. | Operator confusion and accidental pushes. | Define branch mapping and approval variables per target in runbook + hook messaging. |
| R8 | `scripts/healthcheck.sh` still checks removed `ct-collector`. | Noisy or stale health signal. | Refresh health check inventory as part of migration workstream. |
| R9 | Some security controls were assigned to Caddy though they require app context (e.g. nonce, semantic throttles). | Control drift and false confidence. | Split controls by layer: edge transport/header controls vs app-level semantic controls. |

## Architecture details

### Signup box (CAX11, ~40 kr/mo)

- 2 vCPU Ampere, 4 GB RAM, 40 GB NVMe.
- Services: `caddy`, `tailscale`. No Node.js runtime. No `signup-app` container.
- SvelteKit uses `adapter-static`. Caddy serves the pre-built static bundle directly from a named volume. The bundle is baked into a `ghcr.io/<owner>/heimdall-signup-static:<short-sha>` image in CI (`npm install` + `svelte-kit build`) — immutable pull-by-SHA on deploy, same discipline as backend services.
- MitID OIDC `redirect_uri` lands on the backend FastAPI (`api.<domain>/api/signup/...`), not on the SvelteKit bundle.
- SvelteKit → backend API path: two options (decided at scaffolding time): (a) Caddy reverse-proxy rule `signup.<domain>/api/* → backend Tailscale IP`; (b) SvelteKit fetches directly to public `api.<domain>`. Both are valid; see "Open items requiring decision".
- Stateful data: only cert/state artifacts (`caddy/data`, tailscale state).
- Firewall: inbound `80/443` world, `22` tailscale only.
- No DB or Redis persistence on this host.

### Backend box (CAX31, ~105 kr/mo)

- 4 vCPU Ampere, 8 GB RAM, 160 GB NVMe.
- Core services: `redis`, `heimdall-scheduler`, `heimdall-worker` x3, `heimdall-api`, `heimdall-delivery`.
- Observability: `prometheus`, `grafana` (and optionally dozzle), not publicly exposed.
- Ingress: `caddy` publishes `443` and proxies only intended API/console/webhook paths.
- Operator console (`/app`): Caddy serves `/app` only when the Host header matches the Tailscale magic-DNS hostname (e.g. `heimdall-backend.<tailnet>.ts.net`). No public hostname for `/app`.
- Scheduler: `deploy.replicas: 1`, `restart: unless-stopped`. The in-process timers (retention 300s cadence, CT-monitor daily, trial-expiry sweep) are not safe to run across concurrent scheduler instances.
- Resilience: Hetzner managed backups (daily, 7d) plus off-host nightly Storage Box backups.

### Transactional email

Backend FastAPI calls the Postmark EU API (`https://api.postmarkapp.com`, EU server region) with a server token stored in Secrets Manager (Docker secrets file, same pattern as other credentials). Templates rendered server-side. Sending subdomain: `mail.<domain>` (exact subdomain set at registrar setup).

DNS records required (set via Simply API at registrar setup):

- SPF: `v=spf1 include:spf.mtasv.net ~all` on `mail.<domain>`
- DKIM: 3 CNAME records (exact targets provided by Postmark on domain verification)
- DMARC: `v=DMARC1; p=quarantine; rua=mailto:dmarc@<domain>; pct=100` on `_dmarc.<domain>`

Postmark cost: free tier covers ~100 emails/mo; ~112 kr/mo at 10k emails/mo. Used by Messages 0, 4, 5, 6, 7, 9, 10, 11 (see locked Sentinel onboarding plan for full message inventory).

### Betalingsservice webhook

Webhook target is Hetzner Caddy `:443` (`api.<domain>/api/webhooks/betalingsservice`). **This supersedes the locked Sentinel plan integration diagram (line 543), which originally routed the webhook to Pi5 via Tailscale Funnel.** That path is no longer used.

Binding migration constraint: `clients.db` must be live on Hetzner and verified (Step 7 complete + integrity checks passed) before any production webhook URL is registered with NETS. Registering the webhook URL before Step 7 is complete will cause webhook delivery to a backend with no client data.

### Storage Box BX11 (~24 kr/mo)

- 1 TB SSH/SFTP target over tailscale. Located FSN1, co-resident with both compute boxes.
- Stores nightly copies of:
  - `clients.db`
  - `companies.db`
  - Redis RDB dump
  - backup manifest + checksums
- Retention: 5 years for all backups. At ~50 MB/night × 1825 days ≈ 90 GB on a 1 TB Storage Box — within budget.
- GDPR Art 5(1)(e) tension: backups carrying full client PII for 5 years require a documented retention basis. Bogføringsloven covers the financial-records subset (`subscriptions` + `payment_events`) but not the broader scan history. Flagged for legal review by Anders Wernblad (Aumento Law) — see "Open items requiring decision".

### Disaster recovery posture

Accepted risk: single-region FSN1 only, no cross-region backups. Total FSN1 outage = total data unavailability. Recovery is contingent on Hetzner restoring the region.

RTO: bounded by Hetzner regional restore time (no self-imposed SLA number). RPO: last nightly Storage Box backup (up to 24h data loss in a total-loss scenario).

### Networking

- Inter-box traffic: tailscale only.
- Operator SSH: tailscale only, no public SSH.
- Public ingress: Caddy on signup and backend hosts with Let's Encrypt HTTP-01.

## Security baseline (corrected by layer)

| Layer | Concrete controls |
|---|---|
| A. Transport and edge | TLS 1.3, HSTS, HTTP→HTTPS 308, strict host routing in Caddy. |
| B. Edge headers | `X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy`, COOP/CORP via Caddy where static. |
| C. App session and auth | Cookie flags (`Secure`, `HttpOnly`, `SameSite`, `__Host-`), CSRF origin checks, state/nonce PKCE-style handshake for identity flows. |
| D. App input validation | schema-based validation (Zod/Valibot), bounded lengths, CVR/email checks, payload size limits. |
| E. Abuse controls | coarse IP limits at edge; semantic limits (email/cvr token issuance, webhook idempotency) in app/data layer. |
| F. Host and container hardening | read-only filesystems where possible, dropped caps, no docker socket in app containers, security updates window. |

Operator console access: Caddy on backend serves `/app` only when the Host header is the Tailscale magic-DNS hostname. No public hostname exposes `/app`.

Forensic hooks:

- Structured Caddy access logs,
- redacted app logs (see R5 scope below),
- Redis sink redaction before publish,
- Telegram alerts for failed auth/signature events and health regressions.

## Deployment, CI/CD, and branch policy

### Deployment policy

- Hetzner deploy scripts use immutable GHCR tags:
  - `ghcr.io/<owner>/heimdall-<svc>:<short-sha>`
- No local `docker build` on cloud production hosts.
- Snapshot before deploy; rollback via snapshot or prior SHA.

Pi5 (Cortex-A76) and Hetzner Ampere (Neoverse-N1) are both `linux/arm64` Docker targets. Existing CI builds via QEMU emulation on `ubuntu-latest`; the same image runs on both µarches at the Docker layer. Before cutover, confirm that no Python package in `requirements.txt` ships a pre-compiled wheel pinned to a specific arm64 subarch — run `pip install --dry-run` on a Hetzner instance during validation step (Step 5).

### Branch and approval gate policy

- Backend deploy branch: `prod` with `HEIMDALL_APPROVED=1`.
- Signup deploy branch: `prod-signup` with `HEIMDALL_SIGNUP_APPROVED=1`.
- `.githooks/pre-push` must enforce both mappings with explicit error text.

### CI image pipeline

- SvelteKit uses `adapter-static`: CI runs `npm install` + `svelte-kit build` and bakes the static output into `ghcr.io/<owner>/heimdall-signup-static:<short-sha>`. Caddy on the signup box pulls this image and serves the bundle from a named volume. No Node.js runtime on the signup box.
- Image matrix stays at 5 backend service images. The signup-static image is an additional build target but is not a runtime service image.
- Keep tags `<full-sha>`, `<short-sha>`, `:main` (no `:latest`).

## Monitoring and logging (optimized)

### Monitoring

- Prometheus on backend scrapes:
  - Docker built-in Prometheus endpoint (`127.0.0.1:9323`, enabled via `metrics-addr: 127.0.0.1:9323` + `experimental: true` in `/etc/docker/daemon.json`),
  - prometheus itself,
  - node exporter (backend + signup).
- Grafana remains backend-local (tailscale/operator access).
- Synthetic uptime:
  - external probe for `https://api.<domain>/health`,
  - backend probe for `https://signup.<domain>/health` (or service health route).

### Logging

- Keep local `json-file` limits.
- Ship selected logs to Redis channel for console.
- Add deterministic redaction for email/CVR/token-like fields before publish.

## Backups and restore discipline

- Nightly backups from backend to Storage Box.
- Include manifest (`sha256`, file sizes, timestamp, source host).
- Quarterly `restore_drill.sh`:
  - restore into throwaway host,
  - verify SQLite integrity + row counts,
  - destroy throwaway host,
  - alert on mismatch.

## Critical files and actions

### To modify

- `.github/workflows/publish-images.yml`
  - add `heimdall-signup-static` image build step (static bundle, not a runtime service image).
- `.githooks/pre-push`
  - dual gate variables (`HEIMDALL_APPROVED=1` → `prod`; `HEIMDALL_SIGNUP_APPROVED=1` → `prod-signup`) and branch mapping with explicit error text per target.
- `docs/runbook-prod-deploy.md`
  - Hetzner two-box deploy and rollback flow; extend with `prod-signup` branch deploy flow, `HEIMDALL_SIGNUP_APPROVED=1` variable, signup-box SSH target.
- `docs/architecture/pi5-docker-architecture.md`
  - supersede with Hetzner architecture doc.
- `scripts/healthcheck.sh`
  - remove stale `ct-collector` checks; support host/service probes for both boxes.
- `scripts/backup.sh`
  - add remote upload and manifest/checksum outputs.
- `infra/compose/docker-compose.yml`
  - remove direct public exposure assumptions.
- `infra/compose/docker-compose.monitoring.yml`
  - bind observability surfaces for operator-only access.
- `infra/compose/prometheus.yml`
  - add Docker built-in endpoint (`127.0.0.1:9323`) and node exporter targets for both boxes.
- `src/logging/redis_sink.py`
  - add redact-before-publish (sink-level regex for `email`, `cvr`, `telegram_chat_id`, magic-link tokens, URL paths with CVR). Caller-side discipline pass required in parallel — see R5.
- `src/db/migrate.py` (and `docs/architecture/client-db-schema.sql`)
  - add `UNIQUE (provider, external_id, event_type)` index on `payment_events` as a new migration step.
- DNS records at Simply.com (D8 registrar)
  - SPF, DKIM (3 CNAME records), DMARC for `mail.<domain>` via Simply API.
  - DNSSEC enabled; Simply is a DK Hostmaster-accredited registrar. Cost: ~190 kr/yr total for `.dk` + `.com`.
- `src/api/app.py` (optional)
  - add `/healthz` alias only if compatibility is required; canonical remains `/health`.

### To create

- `infra/compose/docker-compose.signup.yml` (caddy + tailscale only; no signup-app container)
- `infra/caddy/Caddyfile.signup` (serves static bundle from volume; no `/api` proxy until inter-box path decided)
- `infra/caddy/Caddyfile.backend` (public `443` for API + webhooks; `/app` restricted to Tailscale magic-DNS hostname)
- `scripts/heimdall-deploy-signup` (pull `heimdall-signup-static:<sha>`, copy bundle to volume, restart caddy)
- `scripts/heimdall-deploy-backend`
- `scripts/restore_drill.sh`
- `docs/architecture/hetzner-architecture.md`
- `docs/runbook-hetzner-migration.md`

## Failure modes (top six)

| Failure | Detection | Recovery | RTO |
|---|---|---|---|
| Signup box hard-down | backend probe + external probe fail | recreate from image + snapshot | ~10 min |
| Backend box hard-down | external probe + telegram alert | recreate CAX31, restore backups, DNS cut | 30-60 min |
| Tailscale partition | inter-box checks fail | auto-reconnect + alert escalation | minutes |
| LE rate-limit or cert issue | Caddy renewal errors | preserve cert volume, avoid repeated re-issue loops | n/a |
| Storage Box outage/full | backup job non-zero | rely on managed backups temporarily | degraded |
| Missed payment webhook | reconciliation mismatch | replay/reconcile by provider reference with idempotency key | async, up to 24h |

## Cost end-state

| Line | kr./mo |
|---|---|
| CAX11 signup | 40 |
| CAX31 backend | 105 |
| Backend managed backups (~20%) | 21 |
| Storage Box BX11 | 24 |
| DNS registrar (Simply.com, `.dk` + `.com`) | ~16 |
| Tailscale/UptimeRobot free tier | 0 |
| Total hosting | ~190 kr/mo |

Hosting costs only. For the full vendor cost table (Postmark, Dinero, Aumento Law, Betalingsservice, MitID broker, Claude API), see the locked Sentinel onboarding plan. Total platform cost at 0 clients: ~1,205 kr/mo per that plan; hosting share is ~190 kr/mo.

## Migration sequence (revised gates)

1. Approve this plan revision.
2. Write detailed Hetzner design spec (`docs/superpowers/specs/2026-04-25-hetzner-hosting-design.md`).
3. Implement infra/code deltas from "Critical files and actions".
4. Provision signup CAX11 and validate TLS + headers + health route.
5. Provision backend CAX31 with ingress split and monitoring stack.
6. Run backup restore drill successfully on throwaway host.
7. Migrate data — sub-procedure:
   - a. Maintenance window: `docker compose stop scheduler worker` on Pi5.
   - b. Snapshot source DBs: `sqlite3 clients.db ".backup /tmp/clients.db.bak"` and same for `companies.db`.
   - c. Rsync both `.bak` files to Hetzner backend over Tailscale.
   - d. `PRAGMA integrity_check` on Hetzner copies; must return `ok`.
   - e. Row-count diff vs Pi5 source (`SELECT COUNT(*) FROM clients` and key tables).
   - f. Start backend stack on Hetzner; smoke `GET /health`.
   - g. DNS cutover (`api` then `signup`) with low TTL pre-staged.
   - h. Keep Pi5 stack stopped (not deleted) for 7-day stabilization window.
   - **`data/results/` and `data/output/briefs/`:** Start fresh on Hetzner. Historical scan output is not migrated — these directories are large, migration over Tailscale would take hours, and the data has no operational dependency for new scans. Pi5 copy remains accessible during stabilization if historical output is needed.
8. Stabilization window: 7 days clean operation.
9. Retire Pi5 and archive Pi5-specific operator scripts/runbook sections.

## Verification checklist (corrected)

1. `curl https://signup.<heimdall-domain>/health` returns 200 externally.
2. `curl https://api.<heimdall-domain>/health` returns 200 externally.
3. `tailscale status` and `tailscale ping` are green between boxes.
4. Inter-box API call from signup host to backend over tailscale succeeds.
5. Intentional bad deploy rollback drill succeeds within target RTO.
6. Latest Storage Box backup restores cleanly with matching integrity and row-count checks.
7. Valid and invalid webhook signature tests behave as expected (accept/reject + logging).
8. 30-day synthetic uptime target is met (`>99.9%`).
9. Full Heimdall test suite passes (`~1210` tests currently; update count as suite evolves).
10. Code review gate passes for all Python diffs touching `src/**` or `tests/**`.

## Deferred outside this plan

- MitID broker/provider commercial selection.
- Optional split between `api.` and `console.` hostnames.

## Open items requiring decision

1. **GDPR Art 5(1)(e) retention basis for 5-year backups** — Backups carrying full client PII for 5 years require a documented lawful basis. Bogføringsloven covers `subscriptions` + `payment_events`; broader scan history (briefs, findings, enrichment data) is not covered by an obvious statutory basis. Legal review by Anders Wernblad (Aumento Law) required before the first backup is retained past the 30-day default.

2. **Inter-box API path for SvelteKit → backend** — Two options at scaffolding time: (a) Caddy reverse-proxy rule on signup box: `signup.<domain>/api/* → backend Tailscale IP` (adds config surface, keeps SvelteKit bundle generic); (b) SvelteKit fetch directly to public `api.<domain>` (simpler, one less hop, exposes API hostname in bundle). Federico decides at scaffolding time.
