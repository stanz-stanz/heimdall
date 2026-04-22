# Console Hardening — Design

**Date:** 2026-04-22
**Scope:** Operator console (`src/api/frontend/`, `src/api/console.py`) + scheduler reliability
**Status:** Implemented. See PR #42.

---

## 1. Context

Follow-up work after the v1.1 design-system rollout (`2026-04-21-design-system-v1.1-rollout-design.md`) surfaced that the console was visually refreshed but operationally broken:

- Run Pipeline button silently hung — scheduler container had exited 137 hours earlier with `restart: "no"` and nothing revived it.
- Page refresh lost every view (in-memory Svelte state, no URL persistence).
- Dashboard stat cards were inert; clicking "Briefs" or "Critical" went nowhere.
- The dev pipeline, when triggered, read from the production-scale enriched DB and queued ~1,179 real SMB domains for scanning — breaching the documented "dev uses a 30-site fixture" agreement.

This spec bundles the fixes that landed for the above, plus the design-system v1.2 follow-up that was needed once explanatory prose started showing up in places the v1.1 scale never covered.

---

## 2. Design System v1.2 (additive to v1.1)

v1.2 extends the 11-row utility scale with a single new class and tightens the readability rules that v1.1 left as axioms.

### 2.1 `.t-help` — explanatory prose utility

```css
.t-help {
  font: 400 13px/1.5 var(--sans);
  color: var(--text-dim);
  max-width: 60ch;
}
```

Bundles three things that v1.1 required separately:

1. Size / weight / family (13/400 sans) — matches `.t-body`.
2. Colour `var(--text-dim)` (≥6.8:1 contrast on `--bg-raised`, passes AA).
3. `max-width: 60ch` — the readability-rule §11.4 cap is now enforced by the class itself.

Applied to any rule that wraps explanatory prose an operator reads (card subtitles, form descriptions, empty states, inline hints).

### 2.2 §11.2 tightened

The v1.1 text already said `--text-muted` is "for non-essential decoration only." v1.2 adds:

- A named fix pattern: prose → `.t-help`; short categorical labels → `--text-dim` colour swap.
- `--text-muted` on operator-essential information is now an explicit §11.7 reviewer-checklist failure.

### 2.3 Migration

~15 rules across `global.css`, 5 component files, and `Settings.svelte` migrated from `--text-muted` → `--text-dim` (labels) or full `.t-help` treatment (prose). Legit decorative uses of `--text-muted` retained (`--` null placeholders, search field placeholder, decorative borders).

---

## 3. Console UX

### 3.1 Hash router (`#/view?k=v`)

Replaces pure in-memory Svelte state with a hash-backed router that:

- Parses `window.location.hash` on module load (`#/prospects?critical=1`).
- Exposes a `router.params` object for deep-link query params.
- Listens to `hashchange` events to react to back/forward nav.
- Writes the hash on `navigate()` so state survives refresh and is shareable.

Views opted in to `router.params`:

- `Prospects.svelte` — filters client-side on `critical=1`, shows a dismissable filter banner.
- `Logs.svelte` — initialises `activeSources` from `source=<worker|scheduler|delivery|…>`.
- `Briefs.svelte` — toggles the critical-only query param.

### 3.2 StatCard → clickable

`StatCard.svelte` accepts an optional `onclick` prop. When set, the card becomes `role="button" tabindex="0"`, renders a hover/focus ring, and handles Enter/Space keyboard activation.

### 3.3 Dashboard deep-link wiring

Every indicator links to a populated view:

| Card | Target |
|------|--------|
| Prospects | `#/campaigns` (campaign picker — Prospects itself is campaign-scoped) |
| Briefs | `#/briefs` |
| Clients | `#/clients` |
| Critical | `#/briefs?critical=1` |
| Scan queue | `#/logs?source=worker` |
| Enrichment queue | `#/logs?source=scheduler` |
| Interpretation cache | `#/logs?source=delivery` |
| Activity feed item | its view (pipeline/delivery/campaign/logs) |

### 3.4 Briefs view (new)

`src/api/frontend/src/views/Briefs.svelte` backed by new endpoint `GET /console/briefs/list?critical&limit&offset`. Reads from `v_current_briefs` — not scoped to campaign, so the Dashboard's aggregate Briefs/Critical counts land on a list that actually reflects them.

Columns: domain, bucket, CMS, hosting, severity badges (critical/high/medium), finding count, scan date. Ordered critical desc, then high desc, then total findings desc.

Reachable only via Dashboard links today. No Sidebar nav entry — if it earns one, revisit.

---

## 4. Scheduler Reliability

### 4.1 Restart policy

Scheduler was `restart: "no"` — a SIGKILL (container cycle) put it down permanently. Flipped to `restart: unless-stopped` to match redis/worker/api/delivery. `docker compose run --rm scheduler --mode prospect` one-shot path unchanged (ephemeral containers ignore service restart policies).

### 4.2 Dev-fixture guard

`JobCreator.extract_prospect_domains` gets a new resolution order:

1. `HEIMDALL_DEV_DATASET` env var — if set and the file exists, read the flat 30-domain list from the dev fixture JSON.
2. Pre-enriched SQLite DB.
3. Legacy Excel.

`docker-compose.dev.yml` scheduler block sets `HEIMDALL_DEV_DATASET=/app/config/dev_dataset.json`. Prod overlay leaves it unset.

4 unit tests cover: happy path, missing-file fall-through, dedup/order, committed-fixture regression guard (fails if the fixture ever exceeds 30 domains).

---

## 5. Integration Test

`tests/integration/test_pipeline_button_flow.py` — the end-to-end test that was missing. Asserts, against the live dev stack:

1. `POST /console/commands/run-pipeline` with Basic auth → 200 + `{"status": "queued"}`.
2. A `command_result` event for `run-pipeline` arrives on `console:command-results` within 10 seconds.
3. `queue:operator-commands` drains to 0 within 2 seconds (scheduler actually BRPOPped).

Failure message names the three possible link-breaks (dead scheduler, lost Redis connection, queue-name drift) so the operator reading a red CI output knows where to look. Scope guard: fixture clears `queue:operator-commands` at setup/teardown but deliberately leaves `queue:scan` / `queue:enrichment` alone — the scheduler's pipeline handler is synchronous after the `started` publish, so clearing downstream queues would hang `wait_for_enrichment`.

---

## 6. Out of Scope

- `make dev-seed` writing to `data/dev/clients.db` (host) while the dev api container reads the `heimdall_dev_client-data` docker volume — pre-existing; surfaced during debugging; left for a follow-up.
- A dedicated `/console/prospects` (campaign-less) listing — current Prospects view remains campaign-scoped. Dashboard's Prospects card now points to Campaigns picker as an interim.
- Sidebar nav entry for the Briefs view.
- `.gitignore` gap on `data/results/prospect/` — addressed in wrap-up hygiene commit, not this design.

---

## 7. Acceptance

- PR #42 merged to `main`.
- `grep -rE 'font-size:\s*\d+px' src/api/frontend/src` → 0 matches.
- `npm run build` green.
- Integration test passes against `make dev-up`.
- Scheduler logs show `dev_dataset_loaded path=/app/config/dev_dataset.json domains=30` when the console triggers a pipeline run.
- Dashboard cards all land on populated views (verified manually in browser).
- §11.2 reviewer checklist (`.t-help` for prose, no `--text-muted` on info) passes on the rolled-up diff.
