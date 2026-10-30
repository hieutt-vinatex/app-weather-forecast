# Static-first zero-cost cloud deployment design

**Date:** 2026-10-29

**Status:** Final design awaiting explicit user approval

**Selected approach:** Vercel static frontend, GitHub Actions jobs, and a
Cloudflare Worker backed by Workers KV

## Intent and why

The application currently assumes one continuously running FastAPI process. It
keeps realtime state and SSE subscribers in memory, polls the upstream lottery
source, runs the Telegram scheduler, and persists notification idempotency to a
local JSON file. That model is a poor fit for zero-cost serverless hosting and
for free container services that sleep and discard their files.

The user has selected a static-first architecture because the primary
constraint is a recurring cloud cost of zero. The application may trade
second-level realtime updates for a target five-minute collection cadence and
an accepted typical visibility delay of approximately five to ten minutes
during the active draw window. It must deploy and operate from cloud services
after the initial account setup, without depending on a local machine.

## Goals

- Serve the React/Vite dashboard as a static Vercel deployment.
- Remove the production requirement for an always-running FastAPI process.
- Refresh current draw data on an approximately five-minute schedule during the
  active draw window, with an accepted typical end-to-end delay of five to ten
  minutes, and perform a complete history reconciliation daily.
- Preserve the current `SnapshotResponse` contract for 30-, 60-, and 90-day
  views so most presentation and chart code can remain unchanged.
- Send scheduled and explicitly requested Telegram reports without exposing the
  Telegram token or cloud write credentials to the browser.
- Persist snapshots, job status, and notification idempotency outside an
  ephemeral filesystem.
- Keep generated data out of Git history.
- Deploy from GitHub: pushes update the frontend and Worker, and scheduled
  GitHub Actions update data and send Telegram messages.
- Fail safely: an unsuccessful refresh must leave the last valid snapshot
  available and report freshness according to the confirmed age thresholds.
- Stay within the documented free allowances for a small personal application.

## Non-goals

- Second-level realtime delivery or a permanent SSE connection.
- A continuously running Python web server in production.
- Exact-to-the-minute execution guarantees from a free scheduled runner.
- High-traffic, commercial, multi-tenant, or SLA-backed operation.
- Replacing the upstream lottery data provider or changing the statistical
  meaning of the dashboard.
- Storing secrets in the repository, Vite environment variables, generated
  JavaScript, or public KV values.

## Anti-goals

- Do not use artificial keep-alive traffic to circumvent a free host's sleep
  policy.
- Do not trigger an expensive scrape on every visitor request.
- Do not commit frequently changing generated JSON to the application branch.
- Do not silently serve partially generated snapshots.
- Do not knowingly resend the same scheduled Telegram event merely because a
  job was retried or a deployment restarted. A rare duplicate is preferable to
  silently losing a message when Telegram accepts delivery immediately before
  the job fails to persist its success state.
- Do not normalize or overwrite the existing dirty working tree without first
  distinguishing user changes from line-ending-only changes.

## Constraints and assumptions

- GitHub is the source of truth and already has an `origin` remote.
- The working tree currently reports 113 modified files with equal aggregate
  insertions and deletions, strongly suggesting broad line-ending conversion.
  This must be audited and preserved before implementation commits are made.
- GitHub scheduled workflows may start late or, under high load, be dropped.
  The UI and alerting must treat schedule precision as best effort.
- The selected free Worker runtime is suitable for small KV reads and GitHub
  dispatch calls, not for HTML scraping or statistics computation.
- Workers KV is eventually consistent. Workflow concurrency and explicit
  publication ordering will be used; the system will not claim transactional
  semantics that KV does not provide.
- The upstream timezone and schedule remain `Asia/Ho_Chi_Minh`.
- Ninety days is the confirmed maximum history requirement. Yesterday and all
  other dates already present in the published 30/60/90-day snapshots must be
  immediately readable from KV and must not wait for a new scrape.
- Only the current draw is subject to the accepted five-to-ten-minute update
  delay. Selecting another stored day or changing between 30/60/90-day ranges
  reads a precomputed snapshot.
- The upstream provider must permit GitHub-hosted runners to fetch its public
  pages. A deployment smoke test will verify this before cutover.
- Vercel Hobby is appropriate only while this remains a personal,
  non-commercial project. If that changes, hosting must be reconsidered.
- Account creation, authorizing the GitHub repository, and entering secret
  values in Vercel, Cloudflare, and GitHub require the user's authenticated
  participation. No secret value is requested in chat or committed.
- There is no existing production notification instance whose sent-event state
  needs to be migrated at cutover.

## Confirmed operating decisions

- **Notification guarantee:** use single-writer, best-effort at-least-once
  delivery. Retry uncertain deliveries even though a crash between Telegram
  acceptance and state persistence can very rarely produce a duplicate.
- **Morning catch-up:** Telegram may be sent at any reasonable time in the
  morning. Start at approximately 09:07 and retry every 15 minutes through
  12:07 `Asia/Ho_Chi_Minh`; each later attempt becomes a no-op after success.
- **Freshness states:**
  - `updating` while a sync operation is actively running;
  - during 17:45–19:00, `current` at age <=10 minutes, `delayed` at age >10 and
    <=20 minutes, and `stale` at age >20 minutes;
  - outside that window, `current` at age <=26 hours, `delayed` at age >26 and
    <=48 hours, and `stale` at age >48 hours;
  - a failed refresh changes an otherwise current result to `delayed`, not
    directly to `stale`; the age threshold still controls `stale`.
- **History:** the current 30/60/90-day choices are sufficient; no archive older
  than 90 days or arbitrary-date backend query is required.
- **Current-draw latency:** a typical five-to-ten-minute delay is accepted in
  exchange for a zero-cost static-first architecture.

## Approaches considered

### 1. Static-first cloud jobs and KV — selected

Vercel serves the frontend, GitHub Actions performs scraping/statistics and
Telegram delivery, and a Cloudflare Worker exposes a small public read API over
Workers KV.

This requires the largest deliberate refactor, but it removes the always-on
server, sleeping-container behavior, ephemeral notification state, and local
runtime requirement. Current-draw visibility is expected within approximately
five to ten minutes rather than seconds; historical snapshots remain available
immediately.

### 2. Vercel frontend and Render Free FastAPI backend — rejected

This preserves more code and supports SSE while the backend is alive. However,
the free backend sleeps after inactivity, has a cold start, loses local file
state, and cannot reliably own a morning scheduler. It is easier initially but
less predictable and harder to operate correctly at zero cost.

### 3. Entire application as Vercel Functions — rejected

FastAPI can run as a Vercel Function, but the current background poller,
in-memory broker, scheduler, and file state do not survive the function model.
It would still require a durable store and cron redesign, while long-lived SSE
and scraping on the Hobby plan remain poor fits.

### 4. Always-free virtual machine — rejected

A VM would preserve the current architecture, but it introduces operating
system maintenance, account/billing verification, capacity or reclamation
risk, and a greater chance of accidental non-free resource use. It does not
meet the goal of the easiest zero-cost cloud operation as well as the selected
approach.

## Target architecture

```text
GitHub scheduled/manual workflow
        |
        | runs Python fetch/parse/statistics pipeline
        | writes versioned JSON and job state
        v
Cloudflare Workers KV <---- Cloudflare Worker <---- Vercel React frontend
        ^                         |
        |                         | protected repository_dispatch
        |                         v
        +----------------- GitHub Actions

GitHub Actions ---- Telegram Bot API
```

The production request path never scrapes the upstream source. Browser requests
only read validated, already-computed JSON through the Worker.

## Components

### Python data pipeline

The existing fetcher, parser, date helpers, statistical calculations, absence
evaluation, and Telegram adapter remain Python. They will be separated from
FastAPI lifecycle objects so the same domain pipeline can run as a finite CLI
job.

The CLI will expose bounded modes equivalent to:

- `full-sync`: fetch and reconcile up to 90 days, validate, compute 30/60/90
  snapshots, and publish them.
- `incremental-sync`: load the published history, refresh the current and
  immediately preceding draw as needed, merge by draw date, recompute all
  snapshots, and publish a new version.
- `scheduled-telegram`: evaluate the latest valid snapshot using the existing
  completeness and 19–25 day rules, send pending targets, and persist per-target
  success.
- `manual-refresh` and `manual-telegram`: perform the authenticated operations
  requested from the dashboard and publish operation status.

Every mode must have an explicit timeout, bounded retry policy, structured log
summary, and non-zero exit status on failure.

### Versioned publication in Workers KV

Publication uses immutable versioned keys followed by one manifest update:

- `history:v1:<version>` — normalized draw records needed for incremental work.
- `snapshot:v1:<version>:30`
- `snapshot:v1:<version>:60`
- `snapshot:v1:<version>:90`
- `manifest:v1` — active version, generation time, source reference date,
  completeness, last job status, and a pointer to the immediately preceding
  publication.
- `notification-state:v1` — sent targets by event key and rule window.
- `operation:v1:<request-id>` — queued/running/succeeded/failed state for a
  manual dashboard request, with a short retention period.

A job writes and verifies all versioned values before replacing `manifest:v1`.
If any step fails, the manifest remains unchanged and readers continue using the
previous complete version. The implementation must measure serialized value
sizes and fail before approaching KV's per-value limit. If normalized history
ever exceeds the safe threshold, history is sharded by month without changing
the public API.

Because KV propagation is eventually consistent, a reader that observes the
new manifest before its matching snapshot automatically reads the retained
previous-publication pointer. It never combines payloads from two versions.

Old versions are pruned after a small rollback window. Public values contain no
credentials or full secret recipient identifiers.

### Cloudflare Worker API

The Worker performs only lightweight validation, KV reads, response caching,
CORS, and dispatching authenticated manual jobs.

Public endpoints preserve the useful current API shapes:

- `GET /api/gdb?days=30|60|90` returns the matching current
  `SnapshotResponse` plus freshness metadata and an ETag.
- `GET /api/health` reports whether a published manifest exists, its generation
  time, latest successful source check, and whether it is stale.

Administrative endpoints are asynchronous:

- `POST /api/gdb/refresh`
- `POST /api/notifications/send-now`
- `GET /api/operations/<request-id>`

Administrative POST requests require the existing notification/admin token.
The Worker validates the token, creates a request ID, writes a queued operation,
and calls GitHub `repository_dispatch` using a fine-grained GitHub credential
stored only as a Worker secret. It returns HTTP 202 and the request ID. The
frontend polls the operation endpoint until completion and displays a clear
queued, running, success, or failure message.

CORS uses an explicit production-origin allowlist. Preview origins are not
granted administrative access by default. Administrative endpoints have a
cooldown and reject duplicate in-flight requests of the same type.
Queued/running records older than the bounded active-operation window are
marked failed and released so an abandoned dispatch cannot block later work.

### GitHub Actions workflows

Separate workflows keep permissions and failure reporting narrow:

1. **Data sync**
   - Daily full reconciliation at an off-peak minute.
   - Incremental refresh on a target five-minute cadence between 17:45 and
     19:00 `Asia/Ho_Chi_Minh`, avoiding minute zero where practical. GitHub
     queue delay can extend user-visible freshness to approximately ten minutes.
   - Manual `repository_dispatch` refresh.

2. **Telegram notification**
   - First scheduled attempt around 09:07 `Asia/Ho_Chi_Minh`, followed by
     15-minute catch-up attempts through 12:07 until success is recorded.
   - Manual `repository_dispatch` send.
   - A workflow concurrency group serializes notification runs.

3. **Continuous integration**
   - Python tests.
   - Frontend tests, lint, and production build.
   - Worker typecheck/tests.
   - Contract checks for the three published snapshot shapes.

4. **Worker deployment**
   - Deploy only after Worker tests pass on the production branch.

Generated snapshots are sent directly to KV and are never committed. Workflow
permissions are least-privilege. Telegram, Cloudflare, and dispatch credentials
are GitHub or Worker secrets. Scheduled workflows use timeouts and concurrency
groups so retries cannot overlap silently.

### Telegram delivery and idempotency

Scheduled delivery retains the existing data completeness rule and event key.
Before sending, the job reads `notification-state:v1`; after each successful
target it records that target. Failed targets remain pending for a later run.
The workflow concurrency group prevents concurrent scheduled delivery jobs, and
the state is checked again immediately before sending.

Because Workers KV is eventually consistent and Telegram delivery cannot be
committed atomically with KV state, the design provides practical single-writer
at-least-once delivery rather than an exactly-once guarantee. A rare duplicate
after an ambiguous crash is accepted so a potentially delivered message is not
silently treated as lost. If future requirements include multiple writers or a
different guarantee, notification state will move behind a transactional
Cloudflare D1 endpoint and the delivery policy will be revisited.

Manual sends remain explicitly repeatable, matching current behavior. The UI
warns that clicking again creates another Telegram message.

### Frontend changes

- `VITE_API_BASE_URL` points to the Worker URL at build time.
- The SSE client and in-memory connection semantics are replaced by adaptive
  REST polling:
  - Faster polling while the page is visible during the active draw window.
  - Slower polling outside the window.
  - No polling while the document is hidden or the browser is offline.
  - ETag/304 support prevents unnecessary payload transfer.
- The connection badge becomes a data freshness badge: current, updating,
  delayed, stale, or offline.
- Freshness follows the confirmed thresholds: during 17:45–19:00, current up to
  10 minutes, delayed through 20 minutes, then stale; outside that window,
  current up to 26 hours, delayed through 48 hours, then stale. A failed refresh
  immediately exposes `delayed` while retaining the last valid payload.
- The dashboard always shows the source reference date and generation time.
- Manual refresh and send-now calls handle HTTP 202, poll operation status, and
  explain that cloud work can take several minutes.
- Existing charts, tables, prize selection, and absence calculations retain
  their user-facing behavior and consume the same snapshot contract.

### Vercel deployment

Vercel builds from the `frontend` directory with `npm run build` and publishes
`dist`. SPA fallback routing is configured in source control. Only the public
Worker base URL is a Vite environment variable; no privileged token is exposed
at build time.

Production deployments originate from the repository's production branch.
Preview deployments can read public snapshot data but cannot invoke
administrative Worker endpoints unless their origin is deliberately added.

### Legacy FastAPI and Docker path

The static-first path becomes the only production deployment. During migration,
the existing FastAPI/Docker implementation remains available as a parity
reference and test source. After production smoke tests prove data and Telegram
parity, documentation will mark the server path as legacy and remove unused
realtime scheduler/broker deployment instructions. Pure Python domain modules
remain; production-only background-process assumptions do not.

## Security model

- Telegram bot token and chat IDs: GitHub Actions secrets only.
- Cloudflare account/API credentials: GitHub Actions secrets only.
- GitHub dispatch credential and admin-token verifier: Cloudflare Worker
  secrets only.
- Browser: public Worker URL plus an admin token entered interactively and held
  in memory for administrative actions. It is never placed in local storage,
  query strings, logs, or analytics.
- Worker logs mask recipient IDs and never log authorization headers or secret
  values.
- All administrative calls require HTTPS, origin validation, authentication,
  request validation, cooldown, and bounded payload size.
- The GitHub credential is fine-grained to the one repository and only the
  permissions required to dispatch workflows.

## Failure behavior and observability

- A failed sync leaves `manifest:v1` pointing to the last valid version.
- The Worker keeps separate last-job metadata so a failed refresh can expose
  `delayed` even though the active manifest remains unchanged.
- The Worker exposes freshness but not stack traces or secrets.
- The frontend remains usable with stale data and displays the timestamp and a
  warning.
- GitHub Actions logs identify the phase, source dates fetched, record count,
  version, and masked delivery outcomes.
- Workflow failure notifications are enabled for the repository owner.
- A manual operation transitions through queued/running/succeeded/failed and
  includes a safe Vietnamese summary.
- Rate limits, invalid upstream data, Telegram 429/5xx, and transient KV errors
  use bounded exponential retry; schema/validation errors do not retry blindly.

## Repository and deployment configuration

Expected additions or changes include:

```text
.github/workflows/ci.yml
.github/workflows/data-sync.yml
.github/workflows/telegram.yml
.github/workflows/deploy-worker.yml
cloudflare/worker/...
scripts/cloud_job.py
frontend/vercel.json
docs/cloud-deployment.md
```

Exact module boundaries and filenames inside the Python and Worker packages are
left to the implementation plan, provided the finite-job/domain separation and
public contracts above remain intact.

Before any of these changes, implementation must audit the existing working
tree, preserve real user edits, add an explicit line-ending policy if needed,
and establish a trustworthy baseline. Deployment automation must never push an
unreviewed mass line-ending rewrite.

## Verification strategy

- Unit tests for parsing, merge-by-date, statistics, completeness, absence
  evaluation, serialization, and notification idempotency.
- Contract fixtures proving cloud-generated 30/60/90 responses remain accepted
  by the frontend.
- Tests proving a partial publication never advances the manifest.
- Tests for stale-data, malformed-source, duplicate-schedule, partial Telegram
  failure, and retry behavior.
- Worker tests for CORS, ETag, invalid `days`, missing manifest, authentication,
  cooldown, dispatch failure, and safe error bodies.
- Frontend tests for visibility-aware polling, 304 responses, stale badges,
  queued operations, completion, and failure.
- A cloud dry run that writes a non-production KV namespace and uses
  `NOTIFICATION_DRY_RUN=true` or a dedicated test Telegram target.
- Production smoke checks for `/api/health`, all three day ranges, frontend
  rendering, one manual refresh, and one Telegram test before enabling the
  scheduled Telegram workflow.

## Rollout and rollback

1. Audit Git state and establish a clean, reviewable baseline.
2. Extract and test the finite Python data/notification jobs without changing
   the current production path.
3. Create a staging KV namespace and deploy the Worker read API.
4. Run full and incremental jobs manually in GitHub Actions against staging.
5. Switch a preview frontend to polling the staging Worker and verify parity.
6. Configure production KV/Worker/Vercel secrets and deploy production.
7. Run Telegram in dry-run/test-target mode, then enable the scheduled workflow.
8. Mark FastAPI/Docker production deployment as legacy after an observation
   period.

Rollback is changing the frontend API base back to the last known deployment or
restoring a previous `manifest:v1` version. Old snapshots remain for the small
rollback window. Telegram scheduling can be disabled independently without
affecting dashboard reads.

## Success criteria

- The public dashboard works when the developer's computer is off.
- No always-on paid server, paid database, or persistent disk is required.
- During the draw window, successful jobs make new data visible within roughly
  one scheduled interval plus normal GitHub queue delay; five to ten minutes is
  the accepted normal target rather than a hard upper bound.
- Outside the draw window, daily reconciliation keeps 90-day history current.
- Yesterday and any stored date within the selected 30/60/90-day range can be
  viewed immediately without launching or waiting for a sync job.
- The dashboard clearly reports freshness and continues serving the last valid
  snapshot after a failed refresh.
- Scheduled Telegram uses the documented best-effort at-least-once policy:
  recorded targets are skipped, failed or uncertain targets can retry
  independently, and a rare ambiguous duplicate is accepted over a missed
  message.
- Manual refresh and Telegram actions are authenticated and expose no cloud or
  Telegram credentials.
- All deployments and scheduled operations can be performed from GitHub and
  cloud dashboards without a local runtime.
- CI passes for Python, Worker, and frontend packages before production deploy.

## Left to the builder

- The exact internal Python package split and CLI library.
- The Worker test harness and TypeScript project layout.
- The exact cron expressions, while preserving the specified timezone, windows,
  and off-minute scheduling intent.
- Cache-Control durations and polling intervals within the stated free-tier and
  freshness goals.
- The safe version retention count and cleanup implementation.
- Styling details for freshness and asynchronous-operation states.
