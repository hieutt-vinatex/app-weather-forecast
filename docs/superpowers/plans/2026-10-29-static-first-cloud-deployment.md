# Static-first Zero-cost Cloud Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Chuyển ứng dụng sang kiến trúc static-first miễn phí gồm Vercel frontend, Cloudflare Worker/KV, GitHub Actions thu thập dữ liệu và gửi Telegram, không cần FastAPI chạy liên tục.

**Architecture:** Python hiện có được tách thành các job hữu hạn để tạo snapshot 30/60/90 ngày, xuất bản dữ liệu theo phiên bản vào Workers KV và gửi Telegram. Cloudflare Worker chỉ đọc KV, tính trạng thái freshness và chuyển yêu cầu quản trị sang GitHub Actions; React frontend thay SSE bằng polling thích ứng. Các task phụ thuộc cùng hợp đồng dữ liệu nên được thực hiện tuần tự trong một kế hoạch, nhưng mỗi task tạo ra một deliverable kiểm thử độc lập.

**Tech Stack:** Python 3.12, Pydantic 2, aiohttp, pytest, TypeScript, Cloudflare Workers + KV, Vitest Workers pool, React 18, TanStack Query, Vite 5, GitHub Actions, Vercel.

**Spec:** `docs/superpowers/specs/2026-10-29-static-first-cloud-deployment-design.md`

## Global Constraints

- Chi phí cloud định kỳ phải bằng 0 trong giới hạn free tier của dự án cá nhân, phi thương mại.
- Không chạy FastAPI, scheduler hoặc SSE server liên tục trong production.
- Lịch sử tối đa là 90 ngày; API và UI chỉ cần các phạm vi `30`, `60`, `90`.
- Dữ liệu hôm qua và các ngày đã lưu phải đọc ngay từ KV; không scrape khi người dùng đổi phạm vi.
- Trong 17:45–19:00 `Asia/Ho_Chi_Minh`, job có cadence mục tiêu 5 phút và độ trễ hiển thị bình thường được chấp nhận là 5–10 phút.
- Ngoài giờ quay, một full sync hằng ngày phải giữ lịch sử hiện hành.
- Telegram thử từ khoảng 09:07, lặp mỗi 15 phút tới 12:07 và dừng sau khi đã ghi thành công.
- Telegram dùng best-effort at-least-once: chấp nhận duplicate rất hiếm sau crash mơ hồ để tránh bỏ sót.
- Freshness trong giờ quay: `current <=10m`, `delayed >10m..20m`, `stale >20m`; ngoài giờ: `current <=26h`, `delayed >26h..48h`, `stale >48h`.
- Một sync thất bại chuyển dữ liệu còn đúng tuổi sang `delayed`, không làm mất snapshot hợp lệ gần nhất.
- Không đưa Telegram token, Cloudflare write token, GitHub dispatch token hoặc admin token vào bundle frontend, URL, log hay Git.
- Manifest chỉ được đổi sau khi toàn bộ history và ba snapshot versioned đã ghi và kiểm tra thành công.
- Generated JSON không được commit vào Git.
- Production Python và Node versions lần lượt là `3.12` và `20`.
- Thực thi trong worktree riêng tạo từ commit chứa spec; audit đã xác nhận 113 thay đổi hiện tại chỉ khác CRLF, không có khác biệt nội dung sau khi bỏ `\r`.

## Review Focus

- Upstream trả HTML thiếu/malformed hoặc kỳ quay chưa đủ 27 giải: Task 4 phải giữ manifest cũ và ghi job failure/partial an toàn.
- KV lỗi ở giữa publication hoặc dữ liệu version mới chưa đồng bộ toàn cầu: Task 2 phải chứng minh manifest-last không lộ snapshot dở dang.
- GitHub schedule bị chạy trùng, trễ hoặc retry sau khi Telegram đã nhận: Task 5 và Task 8 phải pin concurrency, per-target state và at-least-once semantics.
- Trình duyệt hidden/offline hoặc snapshot quá tuổi: Task 9 và Task 10 phải dừng polling khi cần và hiển thị đúng freshness thay vì xóa dữ liệu cũ.
- Admin endpoint bị gọi sai origin/token hoặc liên tục: Task 7 phải từ chối trước khi tạo operation hay gọi GitHub và không làm lộ secret trong lỗi.

## File Structure Map

### Python domain and cloud jobs

- Create `app/services/snapshot_builder.py`: assembly thuần từ `DayOutcome` sang `SnapshotResponse`.
- Modify `app/services/gdb_service.py`: delegate assembly hiện tại sang builder thuần.
- Create `app/cloud/__init__.py`: package cloud jobs.
- Create `app/cloud/contracts.py`: stored history, manifest, job/operation và JSON store protocol.
- Create `app/cloud/publisher.py`: versioned publication, active manifest và pruning.
- Create `app/cloud/cloudflare_kv.py`: Workers KV REST adapter.
- Create `app/cloud/data_jobs.py`: full/incremental finite sync jobs.
- Create `app/cloud/notification_store.py`: notification state trên JSON store.
- Create `app/cloud/notification_jobs.py`: scheduled/manual Telegram finite jobs.
- Create `scripts/cloud_job.py`: CLI duy nhất cho GitHub Actions.
- Create `requirements-cloud.txt`: runtime dependencies tối thiểu của cloud jobs.
- Modify `app/config.py`: cloud job settings và validation helpers.
- Modify `app/notifications/state_store.py`: state protocol dùng chung.
- Modify `app/notifications/channels.py`: type against protocol, giữ logic provider hiện có.

### Cloudflare Worker

- Create `cloudflare/worker/package.json`: Worker scripts/dependencies.
- Create `cloudflare/worker/tsconfig.json`: strict TypeScript config.
- Create `cloudflare/worker/wrangler.jsonc`: KV binding và non-secret vars.
- Create `cloudflare/worker/src/contracts.ts`: KV/public response types.
- Create `cloudflare/worker/src/freshness.ts`: timezone window và freshness policy.
- Create `cloudflare/worker/src/auth.ts`: secret comparison, origin và request validation.
- Create `cloudflare/worker/src/github.ts`: repository dispatch client.
- Create `cloudflare/worker/src/index.ts`: routes, KV reads, ETag/CORS và operation lifecycle.
- Create `cloudflare/worker/test/*.test.ts`: Worker contract, freshness và security tests.

### Automation

- Create `.github/workflows/ci.yml`: Python/frontend/Worker tests and builds.
- Create `.github/workflows/data-sync.yml`: full, incremental và manual sync.
- Create `.github/workflows/telegram.yml`: morning catch-up và manual Telegram.
- Create `.github/workflows/deploy-worker.yml`: tested Worker deployment.

### Frontend

- Modify `frontend/src/types/gdb.ts`: freshness và async operation contracts.
- Modify `frontend/src/config.ts`: Worker URL và polling intervals.
- Modify `frontend/src/api/client.ts`: ETag snapshots, 202 operations và status polling.
- Create `frontend/src/utils/freshness.ts`: active-window/polling helpers.
- Create `frontend/src/hooks/usePageActivity.ts`: visibility/online state.
- Create `frontend/src/hooks/useCloudOperation.ts`: queued operation polling.
- Modify `frontend/src/hooks/useGdbSnapshot.ts`: adaptive REST polling.
- Modify `frontend/src/hooks/useManualRefresh.ts`: authenticated async operation.
- Modify `frontend/src/hooks/useSendAbsenceNotification.ts`: authenticated async operation.
- Create `frontend/src/components/AdminOperations.tsx`: shared in-memory admin token and controls.
- Modify `frontend/src/features/dashboard/Dashboard.tsx`: remove SSE dependency and render freshness/admin controls.
- Modify `frontend/src/features/dashboard/DashboardHeader.tsx`: freshness instead of realtime controls.
- Modify `frontend/src/components/StatusBadge.tsx`: current/updating/delayed/stale/offline states.
- Modify `frontend/src/components/Alerts.tsx`: stale/delayed copy.
- Modify `frontend/src/components/AbsenceMonitor.tsx`: remove duplicate admin-token ownership.
- Delete `frontend/src/api/sse.ts`, `frontend/src/api/sse.test.ts`, `frontend/src/hooks/useGdbRealtime.ts` after polling parity tests pass.
- Create `frontend/vercel.json`: SPA fallback.

### Documentation and repository policy

- Create `.gitattributes`: deterministic LF policy.
- Create `docs/CLOUD_DEPLOYMENT.md`: zero-local bootstrap, secrets, staging, production and rollback.
- Modify `README.md`, `docs/INSTALLATION.md`, `docs/TELEGRAM_GROUP.md`: static-first production path and legacy local server notes.
- Modify `.env.example`, `frontend/.env.example`: public/local examples only; no real secret.

---

### Task 1: Extract pure snapshot assembly without behavior change

**Files:**
- Create: `app/services/snapshot_builder.py`
- Modify: `app/services/gdb_service.py:194-276`
- Create: `tests/test_snapshot_builder.py`
- Modify: `tests/test_gdb_service.py`

**Interfaces:**
- Consumes: existing `DayOutcome`, `SnapshotResponse`, `RealtimeState`, `compute_statistics`.
- Produces: `SnapshotBuildContext` dataclass and `assemble_snapshot(days: int, outcomes: Sequence[DayOutcome], context: SnapshotBuildContext) -> SnapshotResponse`.

- [ ] **Step 1: Write failing parity and deterministic-order tests**

```python
def test_assemble_snapshot_preserves_current_contract():
    snapshot = assemble_snapshot(30, outcomes, context)
    assert [record.date for record in snapshot.data] == ["2026-10-28", "2026-10-29"]
    assert snapshot.meta.requested_days == 30
    assert snapshot.meta.incomplete_dates == ["2026-10-29"]
    assert set(snapshot.statistics_by_prize) == {"db", "g1", "g2", "g3", "g4", "g5", "g6", "g7"}

def test_assemble_snapshot_rejects_unsupported_days():
    with pytest.raises(ValueError, match="30, 60, or 90"):
        assemble_snapshot(31, [], context)
```

- [ ] **Step 2: Run the tests and verify missing module/signature failure**

Run: `pytest -q tests/test_snapshot_builder.py`

Expected: FAIL because `app.services.snapshot_builder` does not exist.

- [ ] **Step 3: Implement the pure builder interface**

Create exactly:

```python
@dataclass(frozen=True)
class SnapshotBuildContext:
    fetched_at: datetime
    last_source_check_at: datetime | None
    last_successful_check_at: datetime | None
    last_changed_at: datetime | None
    snapshot_version: int
    source: str
    poll_interval_seconds: float = 0.0
    realtime_enabled: bool = False
    cached: bool = True
    stale: bool = False

def assemble_snapshot(
    days: int,
    outcomes: Sequence[DayOutcome],
    context: SnapshotBuildContext,
) -> SnapshotResponse:
    ...
```

Move the existing `_assemble` calculations without changing field meanings or sorting. Validate only `30`, `60`, `90` and sort outcomes ascending by day.

- [ ] **Step 4: Delegate `GdbService._assemble` to the pure builder**

Construct `SnapshotBuildContext` from `RealtimeState` and current settings; keep `GdbService.build_snapshot()` public behavior unchanged.

- [ ] **Step 5: Run focused and regression tests**

Run: `pytest -q tests/test_snapshot_builder.py tests/test_gdb_service.py tests/test_statistics.py tests/test_api.py`

Expected: PASS.

- [ ] **Step 6: Commit the extraction**

```bash
git add app/services/snapshot_builder.py app/services/gdb_service.py tests/test_snapshot_builder.py tests/test_gdb_service.py
git commit -m "refactor: extract pure snapshot assembly"
```

### Task 2: Define cloud storage contracts and atomic publication boundary

**Files:**
- Create: `app/cloud/__init__.py`
- Create: `app/cloud/contracts.py`
- Create: `app/cloud/publisher.py`
- Create: `tests/test_cloud_publisher.py`

**Interfaces:**
- Consumes: `assemble_snapshot()` and `SnapshotBuildContext` from Task 1.
- Produces:
  - `JsonStore` protocol with async `get_json`, `put_json`, `delete`, `list_keys`.
  - `StoredDayOutcome.from_domain()` / `.to_domain()`.
  - `JobRecord`, `OperationRecord`, `PublicationManifest` Pydantic models.
  - `SnapshotPublisher.publish(outcomes, context, job) -> PublicationManifest` and `load_active_history() -> list[DayOutcome]`.

- [ ] **Step 1: Write failing manifest-last and round-trip tests**

```python
async def test_publish_advances_manifest_only_after_all_payloads_exist():
    store = FailingMemoryStore(fail_on_put=4)
    await store.put_json("manifest:v1", old_manifest.model_dump(mode="json"))
    with pytest.raises(StorageWriteError):
        await publisher.publish(outcomes, context, job)
    assert await store.get_json("manifest:v1") == old_manifest.model_dump(mode="json")

def test_stored_day_outcome_round_trips_domain_values():
    restored = StoredDayOutcome.from_domain(outcome).to_domain()
    assert restored.signature == outcome.signature
    assert restored.complete is outcome.complete
```

- [ ] **Step 2: Run tests and verify contract classes are missing**

Run: `pytest -q tests/test_cloud_publisher.py`

Expected: FAIL importing `app.cloud.contracts`.

- [ ] **Step 3: Implement storage and serialized models**

Use these exact key contracts:

```text
history:v1:<version>
snapshot:v1:<version>:30
snapshot:v1:<version>:60
snapshot:v1:<version>:90
manifest:v1
notification-state:v1
operation:v1:<request-id>
job-status:v1:data
job-status:v1:telegram
```

`PublicationManifest` must include `schema_version=1`, `version`, `generated_at`, `history_key`, `snapshot_keys: dict[int, str]`, `source_reference_date`, `complete`, and `last_job`. Scheduled jobs also update `job-status:v1:data` or `job-status:v1:telegram`; this mutable status is separate from the manifest so a failed job is observable without publishing invalid data.

- [ ] **Step 4: Implement `SnapshotPublisher` with manifest-last publication**

Generate a sortable UTC version ID from `generated_at`; serialize with camelCase aliases used by the frontend. Enforce a configurable maximum serialized value size before any write. Verify each versioned value by reading it back, then write `manifest:v1` last.

- [ ] **Step 5: Add review-focus tests for oversized values and partial write/read failures**

```python
async def test_oversized_payload_fails_before_any_versioned_write():
    with pytest.raises(PayloadTooLargeError):
        await publisher.publish(oversized_outcomes, context, job)
    assert store.keys == {"manifest:v1"}

async def test_load_history_uses_only_manifest_version():
    assert await publisher.load_active_history() == old_outcomes
```

- [ ] **Step 6: Run tests**

Run: `pytest -q tests/test_cloud_publisher.py tests/test_snapshot_builder.py`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add app/cloud tests/test_cloud_publisher.py
git commit -m "feat: add versioned snapshot publication"
```

### Task 3: Implement the Cloudflare KV REST adapter and cloud settings

**Files:**
- Create: `app/cloud/cloudflare_kv.py`
- Modify: `app/config.py:64-92,115-154`
- Create: `tests/test_cloudflare_kv.py`
- Modify: `.env.example`

**Interfaces:**
- Consumes: `JsonStore` from Task 2.
- Produces: `CloudflareKVStore(JsonStore)` and `Settings.require_cloud_job_config() -> CloudJobConfig`.

- [ ] **Step 1: Write failing adapter tests using an injected fake `aiohttp.ClientSession`**

```python
async def test_get_json_returns_none_for_404():
    assert await store.get_json("missing") is None

async def test_put_json_uses_namespace_values_endpoint_without_logging_token():
    await store.put_json("manifest:v1", {"version": "v1"})
    assert request.method == "PUT"
    assert request.url.endswith("/values/manifest%3Av1")
    assert request.headers["Authorization"] == "Bearer secret"
```

- [ ] **Step 2: Run and verify missing adapter failure**

Run: `pytest -q tests/test_cloudflare_kv.py`

Expected: FAIL importing `CloudflareKVStore`.

- [ ] **Step 3: Add cloud settings without breaking local FastAPI defaults**

Add optional environment-backed fields for account ID, namespace ID, API token, 20 MiB safe payload limit, operation TTL `86400`, and job timeout. `require_cloud_job_config()` must raise one masked validation error listing missing variable names only.

- [ ] **Step 4: Implement `CloudflareKVStore`**

Constructor signature:

```python
def __init__(
    self,
    account_id: str,
    namespace_id: str,
    api_token: str,
    session: aiohttp.ClientSession,
) -> None:
    ...
```

Implement URL-escaped keys, JSON encode/decode, optional expiration TTL, pagination for `list_keys`, bounded retry for 429/5xx, and safe typed errors that never contain response headers or request URLs with credentials.

- [ ] **Step 5: Add failure and pagination tests**

Cover malformed JSON, 401/403 non-retryable, 429 retryable, timeout, and two-page key listing.

- [ ] **Step 6: Run settings and adapter tests**

Run: `pytest -q tests/test_cloudflare_kv.py tests/test_api.py tests/test_notifications.py`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add app/cloud/cloudflare_kv.py app/config.py tests/test_cloudflare_kv.py .env.example
git commit -m "feat: add Cloudflare KV storage adapter"
```

### Task 4: Build finite full and incremental data jobs

**Files:**
- Create: `app/cloud/data_jobs.py`
- Create: `scripts/cloud_job.py`
- Create: `requirements-cloud.txt`
- Create: `tests/test_cloud_data_jobs.py`

**Interfaces:**
- Consumes: `GdbService.fetch_day()`, `SnapshotPublisher`, `CloudflareKVStore`.
- Produces:
  - `DataJobResult(status, mode, version, record_count, reason)`.
  - `full_sync(settings, store, *, clock) -> DataJobResult`.
  - `incremental_sync(settings, store, *, clock) -> DataJobResult`.
  - CLI `python scripts/cloud_job.py sync --mode full|incremental [--request-id UUID]`.

- [ ] **Step 1: Write failing full-sync, incremental-merge and invalid-upstream tests**

```python
async def test_full_sync_fetches_90_days_and_publishes_three_ranges():
    result = await full_sync(settings, store, clock=fixed_clock)
    assert result.status == "succeeded"
    assert set(manifest.snapshot_keys) == {30, 60, 90}
    assert len(await publisher.load_active_history()) == 90

async def test_incremental_sync_replaces_dates_without_duplicates():
    result = await incremental_sync(settings, store, clock=next_day_clock)
    dates = [item.day.isoformat() for item in await publisher.load_active_history()]
    assert len(dates) == len(set(dates)) == 90

async def test_malformed_current_draw_keeps_previous_manifest():
    result = await incremental_sync(settings, store, clock=fixed_clock)
    assert result.status == "failed"
    assert (await store.get_json("manifest:v1"))["version"] == "old"
    assert (await store.get_json("job-status:v1:data"))["status"] == "failed"
```

- [ ] **Step 2: Run and verify missing job module failure**

Run: `pytest -q tests/test_cloud_data_jobs.py`

Expected: FAIL importing `app.cloud.data_jobs`.

- [ ] **Step 3: Implement bounded full sync**

Fetch exactly the configured 90-day date range with existing concurrency/retry settings. Preserve incomplete current-day records, but require at least one valid record and valid schema before publication. Set `JobRecord` fields for started, finished, mode, status and safe reason, and always persist the terminal record to `job-status:v1:data` even when publication fails.

- [ ] **Step 4: Implement incremental sync**

Load active history; refresh today and the immediately preceding day without cache; merge by ISO date; retain only the latest 90 requested calendar dates; publish all three snapshots together. If no manifest exists, transparently perform full sync.

- [ ] **Step 5: Implement operation-state lifecycle**

When `--request-id` is present, write `queued -> running -> succeeded|failed` to `operation:v1:<id>` with TTL `86400`; include only masked/safe Vietnamese summaries.

- [ ] **Step 6: Implement CLI parsing and exit codes**

`main(argv: list[str] | None = None) -> int` returns `0` only for succeeded/no-change jobs and non-zero for validation, source, storage or timeout failures. Wrap the async job in the configured overall timeout.

- [ ] **Step 7: Pin cloud runtime dependencies**

Include only aiohttp, beautifulsoup4, pydantic, pydantic-settings, python-dotenv, brotli and tzdata at the versions already used by `requirements.txt`.

- [ ] **Step 8: Run focused and existing fetch/parser tests**

Run: `pytest -q tests/test_cloud_data_jobs.py tests/test_fetcher.py tests/test_parser.py tests/test_gdb_service.py`

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add app/cloud/data_jobs.py scripts/cloud_job.py requirements-cloud.txt tests/test_cloud_data_jobs.py
git commit -m "feat: add finite cloud data sync jobs"
```

### Task 5: Move notification state and Telegram delivery into finite jobs

**Files:**
- Modify: `app/notifications/state_store.py`
- Modify: `app/notifications/channels.py:41-176`
- Create: `app/cloud/notification_store.py`
- Create: `app/cloud/notification_jobs.py`
- Modify: `scripts/cloud_job.py`
- Create: `tests/test_cloud_notification_jobs.py`
- Modify: `tests/test_notifications.py`

**Interfaces:**
- Consumes: active 90-day `SnapshotResponse`, `JsonStore`, existing evaluation/formatting and `NotificationDispatcher`.
- Produces:
  - `NotificationStateProtocol`.
  - `KVNotificationStateStore(NotificationStateProtocol)`.
  - `run_scheduled_notification(settings, store, *, clock) -> CloudNotificationResult`.
  - `run_manual_notification(settings, store, request_id, *, clock) -> CloudNotificationResult`.
  - CLI `python scripts/cloud_job.py telegram --mode scheduled|manual [--request-id UUID]`.

- [ ] **Step 1: Write failing idempotency, partial-target and crash-ambiguity tests**

```python
async def test_scheduled_notification_skips_recorded_target():
    result = await run_scheduled_notification(settings, store, clock=fixed_clock)
    assert result.status == "already_delivered"
    assert dispatcher.sent == []

async def test_partial_failure_retries_only_failed_target():
    first = await run_scheduled_notification(settings, store, clock=fixed_clock)
    second = await run_scheduled_notification(settings, store, clock=fixed_clock)
    assert [target.key for target, _ in dispatcher.sent] == ["telegram:a", "telegram:b", "telegram:b"]

async def test_state_write_failure_after_send_allows_at_least_once_retry():
    with pytest.raises(StorageWriteError):
        await run_scheduled_notification(settings, failing_store, clock=fixed_clock)
    assert len(dispatcher.sent) == 1
```

- [ ] **Step 2: Run and verify missing cloud notification modules**

Run: `pytest -q tests/test_cloud_notification_jobs.py`

Expected: FAIL importing `KVNotificationStateStore`.

- [ ] **Step 3: Extract the state protocol and implement KV state**

Protocol methods must cover `sent_targets`, `mark_sent`, `is_no_match`, `mark_no_match`, `get_provider`, and `update_provider`. Preserve local `NotificationStateStore` behavior; serialize cloud state at `notification-state:v1` and mask target displays.

- [ ] **Step 4: Implement scheduled notification job**

Read the active 90-day snapshot and manifest; evaluate the existing 19–25 day rule at the supplied clock. Return no-op for not-due, incomplete, no-match, or already-delivered. Record each target immediately after provider success. Never pre-record a target before sending. Persist the terminal result to `job-status:v1:telegram` for every scheduled attempt.

- [ ] **Step 5: Implement manual notification job and operation lifecycle**

Use `evaluate_snapshot_now`, keep explicit repeats allowed, and update `operation:v1:<request-id>` through running/succeeded/failed with the existing Vietnamese result summary.

- [ ] **Step 6: Extend the CLI and validate dry-run**

Dry-run must discover targets and format the message without calling Telegram or marking the scheduled target as delivered.

- [ ] **Step 7: Run notification regression suite**

Run: `pytest -q tests/test_cloud_notification_jobs.py tests/test_notifications.py`

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add app/notifications app/cloud/notification_store.py app/cloud/notification_jobs.py scripts/cloud_job.py tests/test_cloud_notification_jobs.py tests/test_notifications.py
git commit -m "feat: run Telegram notifications as cloud jobs"
```

### Task 6: Create the Worker public read API and freshness policy

**Files:**
- Create: `cloudflare/worker/package.json`
- Create: `cloudflare/worker/tsconfig.json`
- Create: `cloudflare/worker/wrangler.jsonc`
- Create: `cloudflare/worker/src/contracts.ts`
- Create: `cloudflare/worker/src/freshness.ts`
- Create: `cloudflare/worker/src/index.ts`
- Create: `cloudflare/worker/test/freshness.test.ts`
- Create: `cloudflare/worker/test/public-api.test.ts`

**Interfaces:**
- Consumes: key names and JSON contracts from Tasks 2–5.
- Produces:
  - Worker `fetch(request: Request, env: Env, ctx: ExecutionContext) -> Promise<Response>`.
  - `classifyFreshness(input: FreshnessInput) -> FreshnessStatus`.
  - `GET /api/gdb?days=30|60|90` and `GET /api/health`.

- [ ] **Step 1: Scaffold Worker test config and write failing freshness boundary tests**

```typescript
expect(classifyFreshness(activeAt("18:00", 10, "succeeded"))).toBe("current");
expect(classifyFreshness(activeAt("18:00", 11, "succeeded"))).toBe("delayed");
expect(classifyFreshness(activeAt("18:00", 21, "succeeded"))).toBe("stale");
expect(classifyFreshness(idleAt("08:00", 26 * 60, "succeeded"))).toBe("current");
expect(classifyFreshness(idleAt("08:00", 26 * 60 + 1, "succeeded"))).toBe("delayed");
expect(classifyFreshness(idleAt("08:00", 48 * 60 + 1, "succeeded"))).toBe("stale");
expect(classifyFreshness(activeAt("18:00", 2, "failed"))).toBe("delayed");
```

- [ ] **Step 2: Write failing public API tests**

Assert invalid/missing `days` is 400, missing manifest is 503, valid snapshots preserve the original body contract plus freshness fields, ETag equals quoted manifest version, matching `If-None-Match` returns 304, and disallowed origins receive no CORS allow header.

- [ ] **Step 3: Run Worker tests and verify implementation is missing**

Run: `cd cloudflare/worker && npm install && npm test`

Expected: FAIL because Worker source exports are missing.

- [ ] **Step 4: Implement contracts and freshness**

Use `Intl.DateTimeFormat` with `Asia/Ho_Chi_Minh`; do not infer the active window from the visitor timezone. Include `generatedAt`, `freshnessStatus`, and `lastJobStatus` in `meta` without removing existing fields.

- [ ] **Step 5: Implement GET routes and response caching**

Read `manifest:v1`, `job-status:v1:data`, then the exact manifest snapshot key. Use a short public cache TTL chosen within the spec, ETag/304, `Vary: Origin`, explicit `ALLOWED_ORIGINS`, and safe JSON errors. `/api/health` returns only publication/job/freshness metadata. A failed latest data job must expose `delayed` while leaving the manifest payload unchanged.

- [ ] **Step 6: Add malformed manifest/snapshot and KV exception tests**

Malformed stored JSON or mismatched requested days must return safe 503 and never a partial payload.

- [ ] **Step 7: Run typecheck and tests**

Run: `cd cloudflare/worker && npm run typecheck && npm test`

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add cloudflare/worker
git commit -m "feat: add Worker snapshot read API"
```

### Task 7: Add authenticated Worker operation dispatch

**Files:**
- Create: `cloudflare/worker/src/auth.ts`
- Create: `cloudflare/worker/src/github.ts`
- Modify: `cloudflare/worker/src/contracts.ts`
- Modify: `cloudflare/worker/src/index.ts`
- Create: `cloudflare/worker/test/admin-api.test.ts`
- Create: `cloudflare/worker/test/auth.test.ts`

**Interfaces:**
- Consumes: Worker `Env` and operation key contract.
- Produces:
  - `POST /api/gdb/refresh` -> HTTP 202 `AcceptedOperation`.
  - `POST /api/notifications/send-now` -> HTTP 202 `AcceptedOperation`.
  - `GET /api/operations/<uuid>` -> `OperationRecord`.
  - `dispatchRepositoryEvent(env, eventType, requestId) -> Promise<void>`.

- [ ] **Step 1: Write failing auth and no-side-effect tests**

```typescript
expect(await postRefresh({ token: "wrong" })).toHaveStatus(401);
expect(kv.put).not.toHaveBeenCalled();
expect(github.fetch).not.toHaveBeenCalled();

expect(await postRefresh({ origin: "https://evil.example" })).toHaveStatus(403);
expect(github.fetch).not.toHaveBeenCalled();
```

- [ ] **Step 2: Write failing accepted-operation tests**

Assert UUID request ID, queued operation with TTL 86400, event types exactly `cloud-data-refresh` and `cloud-telegram-send`, 202 response, authenticated operation status, same-type in-flight cooldown, and safe 502 if GitHub rejects dispatch.

- [ ] **Step 3: Run tests and verify missing auth/dispatch modules**

Run: `cd cloudflare/worker && npm test -- admin-api.test.ts auth.test.ts`

Expected: FAIL importing source modules.

- [ ] **Step 4: Implement constant-work secret comparison and origin checks**

Hash supplied and expected secrets with Web Crypto SHA-256, then compare fixed-length bytes without early return. Reject missing/oversized headers and disallowed origins before any KV/GitHub side effect.

- [ ] **Step 5: Implement fine-grained GitHub dispatch client**

Use Worker secrets `GITHUB_TOKEN`, `GITHUB_OWNER`, `GITHUB_REPO`; send `repository_dispatch` with `{event_type, client_payload: {request_id}}`. Never include response bodies or auth headers in user-facing errors.

- [ ] **Step 6: Implement operation routes and cooldown**

Use `operation:v1:<uuid>` and a short `operation-lock:v1:<kind>` key. Require admin token on status reads. Delete the queued operation if dispatch fails; expire locks and operations.

- [ ] **Step 7: Run all Worker checks**

Run: `cd cloudflare/worker && npm run typecheck && npm test`

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add cloudflare/worker/src cloudflare/worker/test
git commit -m "feat: add Worker cloud operation dispatch"
```

### Task 8: Add GitHub Actions schedules, concurrency and CI

**Files:**
- Create: `.github/workflows/ci.yml`
- Create: `.github/workflows/data-sync.yml`
- Create: `.github/workflows/telegram.yml`
- Create: `.github/workflows/deploy-worker.yml`
- Modify: `scripts/cloud_job.py`
- Create: `tests/test_cloud_cli.py`

**Interfaces:**
- Consumes: CLI from Tasks 4–5 and Worker package from Tasks 6–7.
- Produces: cloud schedules, manual dispatch handlers and tested deploy automation.

- [ ] **Step 1: Write CLI tests for event-derived modes and operation status**

```python
def test_sync_cli_returns_nonzero_and_marks_requested_operation_failed():
    code = main(["sync", "--mode", "incremental", "--request-id", REQUEST_ID])
    assert code == 1
    assert operation.status == "failed"

def test_telegram_cli_noop_after_recorded_success_returns_zero():
    assert main(["telegram", "--mode", "scheduled"]) == 0
```

- [ ] **Step 2: Run CLI tests**

Run: `pytest -q tests/test_cloud_cli.py`

Expected: FAIL until CLI dependency injection and final status handling are exposed.

- [ ] **Step 3: Make CLI testable without environment mutation**

Add `build_parser()` and injected `run_async`/settings factory seams; preserve the exact public commands from Tasks 4–5.

- [ ] **Step 4: Create CI workflow**

Use Python 3.12 and Node 20. Run Python tests, `frontend` tests/lint/build, Worker typecheck/tests, and actionlint. Grant `contents: read` only.

- [ ] **Step 5: Create data workflow with exact schedules**

Use `Asia/Ho_Chi_Minh` timezone and these off-minute schedules:

```text
full:        17 3 * * *
incremental: 47-57/5 17 * * *
incremental: 2-57/5 18 * * *
incremental: 2 19 * * *
```

Handle `repository_dispatch: [cloud-data-refresh]` and `workflow_dispatch`. Set one `cloud-data-sync` concurrency group, `cancel-in-progress: false`, overall timeout, and install `requirements-cloud.txt`.

- [ ] **Step 6: Create Telegram workflow with morning catch-up**

Use:

```text
7-52/15 9-11 * * *
7 12 * * *
```

in `Asia/Ho_Chi_Minh`; handle `repository_dispatch: [cloud-telegram-send]` and `workflow_dispatch`; use one `cloud-telegram` concurrency group with `cancel-in-progress: false`.

- [ ] **Step 7: Create tested Worker deployment workflow**

Deploy only from the production branch after Worker checks; use `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID` secrets; never echo Wrangler environment/secrets.

- [ ] **Step 8: Validate workflow syntax and run all local suites available**

Run: `docker run --rm -v "$PWD:/repo" rhysd/actionlint:latest`

Run: `pytest -q tests/test_cloud_cli.py tests/test_cloud_data_jobs.py tests/test_cloud_notification_jobs.py`

Run: `cd cloudflare/worker && npm run typecheck && npm test`

Expected: all PASS; actionlint prints no findings.

- [ ] **Step 9: Commit**

```bash
git add .github/workflows scripts/cloud_job.py tests/test_cloud_cli.py
git commit -m "ci: automate cloud sync and Telegram jobs"
```

### Task 9: Replace SSE contracts with adaptive snapshot polling

**Files:**
- Modify: `frontend/src/types/gdb.ts`
- Modify: `frontend/src/config.ts`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/hooks/useGdbSnapshot.ts`
- Create: `frontend/src/hooks/usePageActivity.ts`
- Create: `frontend/src/utils/freshness.ts`
- Create: `frontend/src/hooks/useCloudOperation.ts`
- Create: `frontend/src/utils/freshness.test.ts`
- Modify: `frontend/src/hooks/hooks.test.tsx`
- Modify: `frontend/src/api/sse.test.ts` temporarily for migration coverage

**Interfaces:**
- Consumes: Worker response contracts and endpoints from Tasks 6–7.
- Produces:
  - `FreshnessStatus = "current" | "updating" | "delayed" | "stale" | "offline"`.
  - `AcceptedOperation`, `OperationRecord` TypeScript interfaces.
  - `pollIntervalMs(input: PollingContext) -> number | false`.
  - `useCloudOperation(kind) -> CloudOperationState`.

- [ ] **Step 1: Write failing timezone/polling tests**

```typescript
expect(pollIntervalMs({ localTime: "18:00", visible: true, online: true })).toBe(30_000);
expect(pollIntervalMs({ localTime: "08:00", visible: true, online: true })).toBe(300_000);
expect(pollIntervalMs({ localTime: "18:00", visible: false, online: true })).toBe(false);
expect(pollIntervalMs({ localTime: "18:00", visible: true, online: false })).toBe(false);
```

- [ ] **Step 2: Write failing client contract tests**

Test cached ETag -> `If-None-Match`, 304 returns cached typed snapshot, invalid body rejects, operation POST handles 202, operation status sends admin header, and 401/403/429/502 map to safe `ApiError`.

- [ ] **Step 3: Run focused frontend tests**

Run: `cd frontend && npm test -- src/utils/freshness.test.ts src/hooks/hooks.test.tsx src/api/sse.test.ts`

Expected: FAIL for missing polling/operation contracts.

- [ ] **Step 4: Extend frontend types and config**

Add Worker-provided `freshnessStatus`, `generatedAt`, `lastJobStatus` to `Meta`; add operation types. Replace SSE reconnection settings with `VITE_ACTIVE_POLL_MS=30000` and `VITE_IDLE_POLL_MS=300000` defaults.

- [ ] **Step 5: Implement ETag-aware REST client**

Keep one in-memory cache entry per `RangeDays`; never persist snapshot/admin data to local storage. Validate requested days and freshness fields before updating cache.

- [ ] **Step 6: Implement page activity and adaptive query hook**

Track `visibilitychange`, `online`, and `offline`; use `Asia/Ho_Chi_Minh` for active-window calculation. Refetch on return to visible/online, preserve previous data during errors, and stop intervals while hidden/offline.

- [ ] **Step 7: Implement generic async operation hook**

Start a 202 operation, poll authenticated status every 2 seconds up to 15 minutes, stop on succeeded/failed, and surface safe Vietnamese messages. Keep the admin token only in hook/component memory.

- [ ] **Step 8: Run frontend tests**

Run: `cd frontend && npm test -- src/utils/freshness.test.ts src/hooks/hooks.test.tsx src/api/sse.test.ts`

Expected: PASS with migration tests proving polling behavior before SSE deletion.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/types frontend/src/config.ts frontend/src/api/client.ts frontend/src/api/sse.test.ts frontend/src/hooks frontend/src/utils
git commit -m "feat: add adaptive cloud snapshot polling"
```

### Task 10: Migrate dashboard UI to freshness and queued admin operations

**Files:**
- Create: `frontend/src/components/AdminOperations.tsx`
- Create: `frontend/src/components/AdminOperations.test.tsx`
- Modify: `frontend/src/features/dashboard/Dashboard.tsx`
- Modify: `frontend/src/features/dashboard/DashboardHeader.tsx`
- Modify: `frontend/src/components/StatusBadge.tsx`
- Modify: `frontend/src/components/Alerts.tsx`
- Modify: `frontend/src/components/AbsenceMonitor.tsx`
- Modify: `frontend/src/hooks/useManualRefresh.ts`
- Modify: `frontend/src/hooks/useSendAbsenceNotification.ts`
- Modify: `frontend/src/hooks/hooks.test.tsx`
- Delete: `frontend/src/api/sse.ts`
- Delete: `frontend/src/api/sse.test.ts`
- Delete: `frontend/src/hooks/useGdbRealtime.ts`

**Interfaces:**
- Consumes: adaptive snapshot and cloud operation hooks from Task 9.
- Produces: one in-memory admin token owner, freshness UI and no EventSource runtime dependency.

- [ ] **Step 1: Write failing UI tests**

```typescript
expect(screen.getByText("Dữ liệu hiện tại")).toBeInTheDocument();
expect(screen.getByText(/chậm cập nhật/i)).toBeInTheDocument();
expect(screen.getByText(/cập nhật lúc/i)).toHaveTextContent("29/10/2026");
expect(screen.queryByText("Trực tuyến")).not.toBeInTheDocument();
```

Test admin token is not written to `localStorage`, wrong token copy, queued/running/succeeded/failed messages, duplicate manual-send warning, and stored yesterday/history rendering while current sync is delayed.

- [ ] **Step 2: Run UI tests and verify missing component/status behavior**

Run: `cd frontend && npm test -- src/components/AdminOperations.test.tsx src/hooks/hooks.test.tsx`

Expected: FAIL.

- [ ] **Step 3: Implement shared `AdminOperations`**

Own one password input state and pass the trimmed value to manual refresh/send hooks. Clear it on unmount; never log, persist or place it in a URL. Explain that operations run in cloud and may take several minutes.

- [ ] **Step 4: Replace realtime badge/copy with freshness**

Use text plus icon, never color alone. Display generated/source dates. Apply exact `current/updating/delayed/stale/offline` Vietnamese copy and keep historical data visible for delayed/stale states.

- [ ] **Step 5: Remove SSE usage and duplicate admin controls**

Remove `useGdbRealtime` from `Dashboard`, old refresh props from `DashboardHeader`, and notification-token ownership from `AbsenceMonitor`. Delete SSE modules only after no imports remain.

- [ ] **Step 6: Run full frontend validation**

Run: `cd frontend && npm test && npm run lint && npm run build`

Expected: PASS and `rg "EventSource|useGdbRealtime|VITE_SSE" src .env.example` (from `frontend`) returns no production references.

- [ ] **Step 7: Commit**

```bash
git add frontend/src frontend/.env.example
git commit -m "feat: migrate dashboard to cloud freshness"
```

### Task 11: Add Vercel config, repository line-ending policy and deployment documentation

**Files:**
- Create: `.gitattributes`
- Create: `frontend/vercel.json`
- Create: `docs/CLOUD_DEPLOYMENT.md`
- Modify: `README.md`
- Modify: `docs/INSTALLATION.md`
- Modify: `docs/TELEGRAM_GROUP.md`
- Modify: `.env.example`
- Modify: `frontend/.env.example`

**Interfaces:**
- Consumes: all runtime secret names, schedules and URLs from earlier tasks.
- Produces: cloud-only setup path executable from dashboards/GitHub and deterministic text files.

- [ ] **Step 1: Add and validate `.gitattributes`**

Set `* text=auto eol=lf`, preserve binary assets, and specify shell files as LF. In the isolated worktree, run `git add --renormalize .` and confirm the staged diff contains no broad content rewrite beyond intended files.

- [ ] **Step 2: Add Vercel SPA routing**

Configure all non-asset routes to `/index.html`; project root remains `frontend`, build command `npm run build`, output `dist`, Node 20, and only `VITE_API_BASE_URL` is public.

- [ ] **Step 3: Write cloud deployment documentation**

Document, in order: Cloudflare account/namespace creation, Wrangler Worker deployment, Worker secrets, GitHub secrets, staging full sync, Vercel repository connection, preview smoke tests, Telegram dry-run, production enable, schedules, logs, free-tier monitoring, rotation and rollback.

List exact secret names without values:

```text
CLOUDFLARE_ACCOUNT_ID
CLOUDFLARE_API_TOKEN
CLOUDFLARE_KV_NAMESPACE_ID
TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_IDS
NOTIFICATION_ADMIN_TOKEN
GITHUB_DISPATCH_TOKEN
GITHUB_OWNER
GITHUB_REPO
```

- [ ] **Step 4: Mark FastAPI/Docker as legacy local path**

Do not delete it yet. Remove any claim that it is the selected production path; link all production setup to `docs/CLOUD_DEPLOYMENT.md`.

- [ ] **Step 5: Verify docs contain no secret-like values and builds still pass**

Run: `rg -n "[0-9]{6,}:[A-Za-z0-9_-]{20,}|replace_me|localhost:8000" docs README.md frontend/.env.example .env.example`

Expected: only explicitly labeled safe examples/legacy-local references.

Run: `cd frontend && npm run build`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add .gitattributes frontend/vercel.json docs README.md .env.example frontend/.env.example
git commit -m "docs: add zero-cost cloud deployment setup"
```

### Task 12: Verify the integrated system and prepare cloud cutover

**Files:**
- Modify if failures reveal gaps: tests and source files owned by Tasks 1–11 only.
- Create: `scripts/verify_cloud_contracts.py`
- Create: `tests/test_cloud_contracts.py`

**Interfaces:**
- Consumes: Python publication contract, Worker public API contract and frontend validator.
- Produces: one offline contract verifier and a release-ready staging checklist.

- [ ] **Step 1: Write failing cross-language fixture test**

Generate 30/60/90 snapshot fixtures using Python, pass them through Worker response shaping, and validate the result with the same structural expectations as frontend `isSnapshotResponse`.

```python
def test_all_published_ranges_match_public_contract():
    report = verify_fixture_directory(fixtures)
    assert report.valid_ranges == {30, 60, 90}
    assert report.errors == []
```

- [ ] **Step 2: Run and verify missing verifier failure**

Run: `pytest -q tests/test_cloud_contracts.py`

Expected: FAIL importing verifier.

- [ ] **Step 3: Implement the bounded verifier**

Check manifest keys, schema version, requested range, sorted/unique dates, maximum 90 dates, statistics keys, generated timestamp, freshness fields, absence of secret variable names/values, and per-value byte limit.

- [ ] **Step 4: Run complete local verification**

Run: `pytest -q`

Run: `cd cloudflare/worker && npm run typecheck && npm test`

Run: `cd frontend && npm test && npm run lint && npm run build`

Run: `docker run --rm -v "$PWD:/repo" rhysd/actionlint:latest`

Expected: all PASS with no warnings treated as errors.

- [ ] **Step 5: Run security and repository checks**

Run: `git diff --check`

Run: `git grep -nE '(TELEGRAM_BOT_TOKEN|CLOUDFLARE_API_TOKEN|GITHUB_DISPATCH_TOKEN)=' -- ':!*.example' ':!docs/**'`

Expected: no assigned secret values.

- [ ] **Step 6: Commit verifier**

```bash
git add scripts/verify_cloud_contracts.py tests/test_cloud_contracts.py
git commit -m "test: verify cloud publication contracts"
```

### Task 13: Deploy staging, validate production, and cut over safely

**Files:**
- No secret-bearing local files.
- Update only `docs/CLOUD_DEPLOYMENT.md` if observed dashboard steps differ.

**Interfaces:**
- Consumes: authenticated GitHub, Cloudflare and Vercel accounts plus completed code.
- Produces: live static dashboard, Worker API, scheduled jobs and tested Telegram delivery.

- [ ] **Step 1: Create staging KV and Worker resources from cloud dashboards**

Record only resource IDs in GitHub/Cloudflare secrets. Do not paste credentials into chat, shell history, repository files or build logs.

- [ ] **Step 2: Configure GitHub secrets and run CI**

Expected: CI green; Worker deployment job can authenticate; no scheduled production Telegram workflow enabled yet.

- [ ] **Step 3: Manually dispatch staging full sync**

Verify Worker `/api/health`, then `days=30`, `60`, `90`; expected valid manifest, all three ranges, yesterday available without a new job, and no secret fields.

- [ ] **Step 4: Connect Vercel and validate preview**

Set project root `frontend`, Node 20, `VITE_API_BASE_URL` to staging Worker. Verify routing, charts, history pagination, adaptive polling, delayed/stale copy and no EventSource requests.

- [ ] **Step 5: Validate administrative operations**

Use the admin token in the UI; verify refresh returns queued/running/succeeded and wrong token/origin is rejected. Confirm token disappears after page reload and never appears in browser storage/network URLs.

- [ ] **Step 6: Validate Telegram dry-run and one real test**

First keep `NOTIFICATION_DRY_RUN=true`; verify formatted candidate result and no Telegram call. Then use the designated test target with dry-run false for one message and inspect masked logs/state.

- [ ] **Step 7: Enable production schedules and observe one cycle**

Enable data and morning Telegram workflows. Confirm later morning attempts no-op after success, current-draw jobs publish within the accepted 5–10 minute normal target, and failure leaves the last valid snapshot visible.

- [ ] **Step 8: Mark cutover and rollback point**

Record production Worker/Vercel URLs and active manifest version in the deployment log. Keep the prior manifest versions for rollback and document how to disable Telegram independently.

- [ ] **Step 9: Update docs only if actual cloud UI differs, then commit when changed**

```bash
git add docs/CLOUD_DEPLOYMENT.md
git commit -m "docs: record verified cloud cutover steps"
```

If the cloud UI exactly matches the checked-in instructions, record the verification in the deployment log and skip this commit.

## Self-review Record

- **Spec coverage:** Tasks 1–5 cover finite Python jobs, manifest-last KV publication and Telegram; Tasks 6–8 cover Worker/API/automation; Tasks 9–10 cover polling/freshness/UI; Tasks 11–13 cover deployment, verification and rollback.
- **Step scan:** Every implementation step names an exact interface, command or observable result; cloud account actions are isolated to Task 13.
- **Type consistency:** `PublicationManifest`, key names, `FreshnessStatus`, operation event names and CLI commands are defined once and consumed with identical names in later tasks.
- **Review Focus:** Malformed upstream, partial KV publication, duplicate schedules, hidden/offline browser state and admin abuse each have an explicit owning-task test.
- **Proportion:** The plan specifies signatures and assertions, not function bodies; algorithms remain with the implementer except manifest-last ordering and exact schedules fixed by the spec.
