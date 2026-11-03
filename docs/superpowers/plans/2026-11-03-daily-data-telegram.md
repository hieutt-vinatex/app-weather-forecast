# Daily Data Update and Telegram Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Chỉ cập nhật dữ liệu một lần thành công trong cửa sổ 18:45–23:45, cảnh báo Telegram khi lần đầu thất bại, và luôn gửi báo cáo `>=20 ngày` lúc 09:00 sáng hôm sau, kể cả khi phải dùng snapshot cũ hoặc không có ứng viên.

**Architecture:** Data workflow và Telegram workflow tiếp tục tách quyền, dùng chung nhánh `gh-pages` qua `FilesystemJsonStore`. Data workflow ghi atomically `site/data/**` cùng `state/daily-data-update.json`; Telegram workflow đọc trạng thái công khai này, ghi delivery ledger HMAC vào `state/telegram-ledger.json`, và dùng hai event namespace độc lập cho cảnh báo thất bại và báo cáo hằng ngày. Runtime guard theo `Asia/Ho_Chi_Minh` ngăn scheduled run bị trễ sang sai ngày; manual jobs vẫn bỏ qua guard.

**Tech Stack:** Python 3.12, Pydantic 2, pytest, aiohttp, GitHub Actions, GitHub Pages, Bash workflow steps, Telegram Bot API.

**Spec:** `docs/superpowers/specs/2026-11-03-daily-data-telegram-design.md`

## Global Constraints

- Production vẫn GitHub-only, repository public, không cần máy local hoặc scheduler trả phí.
- Múi giờ nghiệp vụ duy nhất là `Asia/Ho_Chi_Minh`; không suy ngày từ UTC trong job logic.
- Scheduled data chỉ được fetch trong `18:30 <= local time <= 23:59`; manual `full|incremental` không bị guard này chặn.
- Mỗi ngày nghiệp vụ chỉ cần một publication có `sourceReferenceDate` đúng ngày; mọi retry sau đó phải no-op trước network fetch.
- Active manifest và snapshot hợp lệ cuối cùng không được thay đổi khi upstream lỗi.
- `state/daily-data-update.json` là dữ liệu công khai: chỉ chứa timestamp, ngày, version và mã lỗi an toàn; không URL, body, exception text hoặc secret.
- Telegram workflow là workflow duy nhất được nhận `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_IDS` và `NOTIFICATION_LEDGER_HMAC_KEY`.
- Daily report khóa theo ngày gửi; failure alert khóa theo ngày nghiệp vụ. Mỗi target HMAC được ghi ledger riêng để retry chỉ target chưa thành công.
- Delivery giữ chính sách best-effort at-least-once: chỉ ghi ledger sau provider success; chấp nhận khả năng trùng hiếm để tránh mất tin âm thầm.
- Ngưỡng là min-only `>=20`, duyệt đủ `00`–`99`; số chưa từng thấy chỉ hiển thị cận dưới từ độ phủ lịch sử, không khẳng định số ngày chính xác.
- Manual Telegram dùng cùng phép tính `>=20` nhưng không tiêu thụ daily-report ledger.
- Mọi writer của `gh-pages` tiếp tục dùng concurrency group `github-pages-publication`, không force-push, và retry fast-forward tối đa ba lần.
- Thực hiện TDD RED/GREEN, commit sau mỗi task; không commit publication data, secret hoặc output sinh từ dry-run lên `develop`.

## Review Focus

- Một data retry sau lần thành công không được fetch hay tăng `attemptCount`; test thuộc Task 3.
- Scheduled data run bị GitHub trì hoãn qua nửa đêm không được ghi trạng thái cho ngày mới hoặc fetch sai ngày; test thuộc Task 3.
- Phép tính phải chọn 20, 21 và trên 25 ngày, loại 19 ngày, đồng thời gắn `>=N` cho số chưa từng thấy; test thuộc Task 2.
- Daily report và failure alert phải dedupe độc lập theo từng HMAC target, đồng thời retry đúng target giao thất bại; test thuộc Task 4.
- `workflow_run` phải chỉ tin workflow/branch/repository cố định, data workflow không có Telegram secret, và rebase/push không được ghi đè ledger khác; test thuộc Task 5.

---

## File structure

### Daily state and data orchestration

- Modify `app/cloud/contracts.py`: thêm `DAILY_DATA_UPDATE_KEY`, `DailyDataUpdateState` và safe reason type.
- Modify `app/cloud/filesystem_store.py`: ánh xạ daily state sang `state/daily-data-update.json`.
- Modify `app/cloud/data_jobs.py`: scheduled guard, attempt state, skip-after-success và manual recovery.
- Modify `scripts/cloud_job.py`: thêm sync mode `scheduled`; giữ `full|incremental` cho manual.
- Modify `scripts/verify_cloud_contracts.py`: validate daily state và secret-safe publication.

### Absence calculation and notifications

- Modify `app/notifications/models.py`: min-only evaluator cho `00`–`99`, lower-bound candidate và formatter fresh/stale/no-data.
- Modify `app/notifications/service.py`: dùng shared min-only contract để local optional path không sai khác quy tắc.
- Modify `app/config.py`: đổi default threshold thành 20 và bỏ max-days khỏi notification rule.
- Modify `app/cloud/notification_store.py`: prune được event key có prefix mới.
- Modify `app/cloud/notification_jobs.py`: daily report, first-failure alert, old snapshot warning và per-target ledger.
- Modify `scripts/cloud_job.py`: Telegram modes `daily|data-failure|manual`.

### Automation and operations

- Modify `.github/workflows/data-sync.yml`: cron 18:45 + hourly retries, scheduled mode và bounded state publication.
- Modify `.github/workflows/telegram.yml`: cron 09:00–12:00, trusted `workflow_run`, daily/failure routing.
- Modify tests for contracts, jobs, CLI, security and documentation.
- Modify `.env.example`, `README.md`, `docs/CLOUD_DEPLOYMENT.md`, `docs/TELEGRAM_GROUP.md`, `docs/DEPLOYMENT_STATUS.md`.

---

### Task 1: Add the public-safe daily update state contract

**Files:**
- Modify: `app/cloud/contracts.py`
- Modify: `app/cloud/filesystem_store.py`
- Modify: `scripts/verify_cloud_contracts.py`
- Modify: `tests/test_filesystem_store.py`
- Modify: `tests/test_cloud_contracts.py`

**Interfaces:**
- Add `DAILY_DATA_UPDATE_KEY = "daily-data-update:v1"`.
- Add `DailyDataUpdateState(CamelModel)` with exact fields:

```python
schema_version: int = 1
business_date: date
status: Literal["pending", "failed", "succeeded"]
attempt_count: int
first_attempt_at: datetime
last_attempt_at: datetime
initial_failure_at: datetime | None = None
last_reason: str | None = None
published_version: str | None = None
source_reference_date: date | None = None
```

- `FilesystemJsonStore.path_for_key(DAILY_DATA_UPDATE_KEY)` maps only to `state/daily-data-update.json`.
- `verify_publication_root()` validates the file when present: schema version 1, timezone-aware timestamps, non-negative attempt count, allowed status/reason, success publication fields, and no unknown/raw diagnostic fields.

- [ ] **Step 1: Write failing mapping and schema round-trip tests**

In `tests/test_filesystem_store.py`, assert the exact new path and list-key round trip. In `tests/test_cloud_contracts.py`, build valid `pending`, `failed`, and `succeeded` documents and assert validation passes. Add invalid fixtures for negative count, naive timestamp, success without version/reference date, raw `exception`, raw URL, bot token and chat ID.

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `python -m pytest -q tests/test_filesystem_store.py tests/test_cloud_contracts.py`

Expected: FAIL because the logical key, model and verifier do not exist.

- [ ] **Step 3: Implement the contract and invariant validation**

Use Pydantic field/model validators so invalid state cannot be persisted by Python jobs. Restrict `lastReason` to safe codes currently emitted by data jobs plus `publication_mismatch` and `update_state_missing`; never serialize an exception message. Keep backward compatibility by treating a missing daily state file as valid during rollout.

- [ ] **Step 4: Extend the filesystem mapping and verifier**

Add the fixed mapping in both directions. In the verifier, load `state/daily-data-update.json` only if it exists, validate with `DailyDataUpdateState`, and report only a stable filename/error code—not offending secret values.

- [ ] **Step 5: Run focused tests and verify GREEN**

Run: `python -m pytest -q tests/test_filesystem_store.py tests/test_cloud_contracts.py`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/cloud/contracts.py app/cloud/filesystem_store.py scripts/verify_cloud_contracts.py tests/test_filesystem_store.py tests/test_cloud_contracts.py
git commit -m "feat: add daily data update state contract"
```

### Task 2: Replace the bounded 19–25 calculation with a complete >=20 report

**Files:**
- Modify: `app/notifications/models.py`
- Modify: `tests/test_notifications.py`

**Interfaces:**
- Change `AbsenceCandidate.last_seen` to `date | None` and add `is_lower_bound: bool = False`.
- Add `evaluate_minimum_absence_snapshot(snapshot, *, now, min_days, send_time)` and `evaluate_minimum_absence_snapshot_now(snapshot, *, now, min_days)` as the new min-only API. Keep the existing bounded wrappers temporarily so the repository stays green until all callers migrate in Task 4.
- Iterate canonical numbers with `f"{value:02d}" for value in range(100)`.
- For never-seen numbers use `coverage_days = (reference_date - earliest_complete_date).days + 1`; include only when `coverage_days >= min_days`, with `days_absent=coverage_days`, `last_seen=None`, `is_lower_bound=True`.
- Add `DailyUpdateWarning(expected_date, attempt_count, last_reason)`.
- Add `format_daily_report_message(evaluation, *, report_date, min_days, warning=None) -> str`.
- Add `format_no_data_daily_message(*, report_date, expected_date, attempt_count, last_reason) -> str`.
- Add `format_data_failure_message(state, *, latest_reference_date) -> str`.
- Add a min-only immediate formatter; Task 4 migrates the public function name and removes the bounded compatibility surface.

- [ ] **Step 1: Write failing threshold and all-number tests**

In `tests/test_notifications.py`, create complete snapshots that prove all boundaries:

- last seen 19 days ago is excluded;
- 20, 21, 26 and 40 days are included and sorted descending then number;
- a number absent from every one of 90 complete records is returned as `is_lower_bound=True`, `days_absent=90`, and formatted `≥90 ngày – không thấy trong dữ liệu hiện có`;
- history coverage of 19 days does not claim a never-seen candidate;
- incomplete/future records do not become last-seen evidence;
- all 100 numbers are considered, including leading-zero strings.

- [ ] **Step 2: Write failing formatter tests**

Assert exact message fragments for:

- fresh daily report with report date, `Kỳ dữ liệu`, total and `>=20` title;
- zero candidates with `Không có số nào chưa xuất hiện từ 20 ngày trở lên trong kỳ dữ liệu này.`;
- stale report where the warning and `Đang sử dụng dữ liệu cũ` occur before the statistical body;
- no valid snapshot, which warns but contains no invented number;
- immediate manual report using the same `>=20` rule.

- [ ] **Step 3: Run model/service tests and verify RED**

Run: `python -m pytest -q tests/test_notifications.py`

Expected: FAIL on the old max-days signatures, observed-number iteration and no-match formatter.

- [ ] **Step 4: Implement one shared min-only evaluator**

Refactor the pure calculation once and let the new scheduled/immediate wrappers only apply time gates. Use only `drawComplete=true` records at or before the latest complete reference date. Do not read cached statistics. Keep `AlertEvaluation.status` values compatible, but make valid zero-candidate evaluations format-able instead of silently suppressing the report. The old bounded wrappers may delegate to the same internal scanner with an upper bound until Task 4 removes them.

- [ ] **Step 5: Preserve a green compatibility boundary**

Do not change `NotificationService`, cloud jobs or settings in this task. Existing bounded functions and tests must still pass while new min-only tests exercise the approved behavior. This keeps the intermediate commit deployable; all callers switch atomically in Task 4.

- [ ] **Step 6: Run focused tests and verify GREEN**

Run: `python -m pytest -q tests/test_notifications.py tests/test_cloud_notification_jobs.py`

Expected: PASS, including legacy cloud tests through the temporary compatibility wrappers.

- [ ] **Step 7: Commit**

```bash
git add app/notifications/models.py tests/test_notifications.py
git commit -m "feat: report all numbers absent at least twenty days"
```

### Task 3: Coordinate one successful data publication per business day

**Files:**
- Modify: `app/cloud/data_jobs.py`
- Modify: `scripts/cloud_job.py`
- Modify: `tests/test_cloud_data_jobs.py`
- Modify: `tests/test_cloud_cli.py`

**Interfaces:**
- Add `run_scheduled_data_job(settings, store, *, clock) -> DataJobResult`.
- Add CLI sync choice `scheduled` beside existing manual `full|incremental`.
- Add successful no-op statuses `already_succeeded` and `outside_window` to CLI exit-zero handling.
- Scheduled business date is `clock().astimezone(settings.tzinfo).date()`.
- `run_data_job(..., mode="full"|"incremental", request_id=...)` remains the manual entry point and records a recovery only when the resulting manifest has `sourceReferenceDate == local today`.

- [ ] **Step 1: Write failing schedule-guard tests**

Add tests with an injected timezone-aware clock:

- 18:45 first attempt performs one incremental fetch and writes `succeeded`, `attemptCount=1`, correct version/reference date;
- 19:45 after success returns `already_succeeded`, makes zero `_fetch_outcomes` calls and leaves attempt count unchanged;
- 18:20 and 00:05 return `outside_window`, make no fetch, and do not initialize/overwrite another business date;
- naive clocks are rejected before a fetch;
- a correct current-date manifest with missing state heals state to `succeeded` without fetching.

- [ ] **Step 2: Write failing failure/recovery tests**

Cover this sequence against one store: initial invalid upstream data preserves manifest, writes failed state with count 1 and `initialFailureAt`; retry at 19:45 increments to 2 and can publish success; later retry skips. Verify the first failure timestamp is preserved. Add cancellation/timeout coverage that records `job_timeout` without exception text.

- [ ] **Step 3: Write failing manual-recovery and CLI tests**

Assert `sync --mode scheduled` selects the scheduled function, while `full|incremental` remain unguarded manual modes. A manual success with current `sourceReferenceDate` updates the same daily state; a manual publication for another reference date does not falsely mark today successful.

- [ ] **Step 4: Run data/CLI tests and verify RED**

Run: `python -m pytest -q tests/test_cloud_data_jobs.py tests/test_cloud_cli.py`

Expected: FAIL because scheduled coordination and daily state writes are missing.

- [ ] **Step 5: Implement state load, attempt and recovery helpers**

Add private helpers that validate `DailyDataUpdateState`, initialize a new business day, persist `pending` before `_sync`, then persist `failed` or `succeeded`. Before fetch, check both the current daily state and active manifest. On failure, retain active manifest; on success, re-read manifest and require matching `sourceReferenceDate` before marking the day successful.

- [ ] **Step 6: Keep manual and scheduled semantics separate**

Scheduled always uses incremental behavior (which already falls back to full without history). Manual mode bypasses the time guard and retains operation records. Manual recovery may update daily state, but must not increment a failed scheduled attempt unless it actually executes a fetch.

- [ ] **Step 7: Run focused tests and verify GREEN**

Run: `python -m pytest -q tests/test_cloud_data_jobs.py tests/test_cloud_cli.py tests/test_cloud_publisher.py`

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add app/cloud/data_jobs.py scripts/cloud_job.py tests/test_cloud_data_jobs.py tests/test_cloud_cli.py
git commit -m "feat: coordinate one daily data publication"
```

### Task 4: Add first-failure alerts and one daily Telegram report per target

**Files:**
- Modify: `app/config.py`
- Modify: `app/notifications/models.py`
- Modify: `app/notifications/service.py`
- Modify: `app/cloud/notification_store.py`
- Modify: `app/cloud/notification_jobs.py`
- Modify: `scripts/cloud_job.py`
- Modify: `.env.example`
- Modify: `tests/conftest.py`
- Modify: `tests/test_notifications.py`
- Modify: `tests/test_cloud_notification_jobs.py`
- Modify: `tests/test_cloud_cli.py`

**Interfaces:**
- Replace cloud `run_scheduled_notification()` with:

```python
run_daily_report(settings, store, *, clock) -> CloudNotificationResult
run_data_failure_notification(settings, store, *, clock) -> CloudNotificationResult
run_manual_notification(settings, store, request_id, *, clock) -> CloudNotificationResult
```

- CLI Telegram choices become `daily|data-failure|manual`.
- Set `Settings.notification_min_days = 20`; remove `notification_max_days`, its validator, its callers and `NOTIFICATION_MAX_DAYS` example.
- Rename the min-only model functions to the public `evaluate_snapshot`, `evaluate_snapshot_now`, `format_alert_message` and `format_immediate_report_message` names, then remove the temporary bounded API from Task 2.
- Daily runtime window is `09:00 <= local time <= 12:59`; outside it returns exit-zero `outside_window` without sending or marking ledger.
- Daily event key is `daily-report:<report-date>:20-plus`; failure event key is `data-update-failure:<business-date>`. HMAC target remains the nested target key in each event.
- Daily expected data date is `report_date - timedelta(days=1)`.
- `JsonNotificationStateStore._prune()` extracts dates from both new prefixes and preserves legacy date-first events during migration.

- [ ] **Step 1: Write failing first-failure alert tests**

Seed a failed daily state and assert:

- `run_data_failure_notification()` sends the business date, safe reason, latest valid `Kỳ dữ liệu`, and retry-until-23:45 text;
- rerun after successful delivery returns `already_delivered` per target;
- one failed target is retried while a successful target is not;
- later failed data attempts reuse the same event key instead of creating alerts;
- state `pending`, `succeeded`, missing initial failure or mismatched/old business date returns a safe no-op;
- no valid snapshot still sends a failure alert without inventing a reference date.

- [ ] **Step 2: Write failing daily report tests**

Cover these exact cases:

- prior evening succeeded: fresh full report;
- all attempts failed: warning + attempt count/reason + explicit old-data line + full report from the latest valid snapshot;
- daily state missing: stale warning with safe `update_state_missing` semantics;
- no valid snapshot: a warning/no-data Telegram message is still delivered;
- zero candidates: confirmation is delivered and recorded, not returned as `no_match`;
- repeated catch-up same day is `already_delivered`, while next day using the same snapshot sends again;
- outside 09:00–12:59 does not consume the event;
- partial target failure retries only the pending target;
- state-write failure after provider success retains at-least-once retry behavior.

- [ ] **Step 3: Write failing manual and CLI compatibility tests**

Assert manual uses the new evaluator, may resend, and does not mark `daily-report:*`. Pin parser routing for all three modes and safe exit statuses.

Also migrate optional `NotificationService` tests: event keys use `<min>-plus`, values above 25 are delivered, and a valid zero-candidate scheduled evaluation follows the normal confirmation-delivery path. This prevents the optional local path from retaining a different business rule.

- [ ] **Step 4: Run notification/CLI tests and verify RED**

Run: `python -m pytest -q tests/test_cloud_notification_jobs.py tests/test_cloud_cli.py`

Expected: FAIL because old scheduled mode keys by snapshot date and suppresses no-match.

- [ ] **Step 5: Implement shared delivery-by-event helper**

Factor the common target discovery, dry-run, pending-target selection, send, mark-after-success and partial-failure logic into one private helper. The helper accepts a fully formatted message and logical event key; it must never log or persist recipient values.

- [ ] **Step 6: Implement daily state/snapshot reconciliation**

Load manifest, 90-day snapshot and daily state independently. A state/manifest mismatch produces a stale warning rather than a crash. Daily mode must still build a no-data message if manifest/snapshot validation fails. Manual mode may keep returning `waiting` when no valid report can be calculated because it is an explicit on-demand report rather than the guaranteed morning status message.

- [ ] **Step 7: Update ledger pruning for namespaced keys**

Parse `daily-report:YYYY-MM-DD:*`, `data-update-failure:YYYY-MM-DD` and legacy `YYYY-MM-DD:*`; prune only when a valid embedded date is older than 120 days. Unknown keys are retained rather than accidentally deleted.

- [ ] **Step 8: Run focused tests and verify GREEN**

Run: `python -m pytest -q tests/test_notifications.py tests/test_cloud_notification_jobs.py tests/test_cloud_cli.py`

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add app/config.py app/notifications/models.py app/notifications/service.py app/cloud/notification_store.py app/cloud/notification_jobs.py scripts/cloud_job.py .env.example tests/conftest.py tests/test_notifications.py tests/test_cloud_notification_jobs.py tests/test_cloud_cli.py
git commit -m "feat: send daily reports and first failure alerts"
```

### Task 5: Rewire GitHub Actions schedules, trust gates and transactional publication

**Files:**
- Modify: `.github/workflows/data-sync.yml`
- Modify: `.github/workflows/telegram.yml`
- Modify: `tests/test_workflow_security.py`

**Interfaces:**
- Data schedules:

```yaml
- cron: "45 18 * * *"
  timezone: "Asia/Ho_Chi_Minh"
- cron: "45 19-23 * * *"
  timezone: "Asia/Ho_Chi_Minh"
```

- Telegram schedules:

```yaml
- cron: "0-45/15 9-11 * * *"
  timezone: "Asia/Ho_Chi_Minh"
- cron: "0 12 * * *"
  timezone: "Asia/Ho_Chi_Minh"
```

- Telegram also uses `workflow_run` for `Data sync and Pages deploy`, `types: [completed]`.
- Event routing: `schedule -> daily`, trusted `workflow_run -> data-failure`, `workflow_dispatch -> daily|manual`.

- [ ] **Step 1: Replace old workflow assertions with failing new schedule tests**

Pin the exact cron strings and timezone. Assert scheduled data invokes `sync --mode scheduled`; workflow dispatch still exposes only `full|incremental`. Assert Telegram dispatch exposes `daily|manual`, while workflow-run mode cannot be selected by a user input.

- [ ] **Step 2: Add failing trust and least-privilege assertions**

Require Telegram workflow-run jobs to verify the completed run has `head_branch == 'develop'` and `head_repository.full_name == github.repository`. Confirm data workflow text contains none of the three Telegram secret names. Confirm Telegram still has no Pages/id-token permission.

- [ ] **Step 3: Add failing bounded-publication assertions**

Data capture/reapply must include exactly `site/data/**` and `state/daily-data-update.json`, then stage both paths in one commit. It must preserve `state/telegram-ledger.json` fetched from the remote. Telegram capture/reapply may update `state/**` but must preserve `site/data/**`. Both remain in the shared non-cancelling mutex and never force-push.

- [ ] **Step 4: Run workflow tests and verify RED**

Run: `python -m pytest -q tests/test_workflow_security.py`

Expected: FAIL on old cron, old mode routing and absent workflow-run trigger.

- [ ] **Step 5: Implement the data workflow**

Remove the 03:17 and five-minute schedules. Scheduled events always call guarded mode; manual events pass the selected mode. Capture the bounded data tree plus optional daily state into a temporary change root. On each remote retry, reset to remote, reapply only those bounded paths, verify contracts, commit once, push without force, deploy the resulting `site/`, then fail the run if sync itself failed.

- [ ] **Step 6: Implement the Telegram workflow**

Add schedule and workflow-run triggers. Keep source checkout fixed to trusted `develop`; do not execute workflow-run head code. Route modes using `github.event_name`. For workflow-run, enforce repository/branch gate before secret-bearing steps. Verify and safely push state after delivery so partial-target ledger changes survive.

- [ ] **Step 7: Run workflow tests and actionlint**

Run: `python -m pytest -q tests/test_workflow_security.py`

Run: `docker run --rm -v "$PWD:/repo" -w /repo rhysd/actionlint:latest`

Expected: PASS with no actionlint diagnostics.

- [ ] **Step 8: Commit**

```bash
git add .github/workflows/data-sync.yml .github/workflows/telegram.yml tests/test_workflow_security.py
git commit -m "ci: schedule daily data and Telegram workflows"
```

### Task 6: Update operator documentation and rollout checks

**Files:**
- Modify: `README.md`
- Modify: `docs/CLOUD_DEPLOYMENT.md`
- Modify: `docs/TELEGRAM_GROUP.md`
- Modify: `docs/DEPLOYMENT_STATUS.md`
- Modify: `tests/test_github_only_docs.py`
- Modify: `.env.example` if Task 2 did not complete all wording changes

**Interfaces:**
- Operator-visible schedules are 18:45 + hourly through 23:45 and 09:00 + catch-up through 12:00.
- Action UI manual data choices remain `full|incremental`; manual Telegram choices become `daily|manual`.
- Status runbook explains three observable state files: public `site/data/status.json`, private-from-artifact but public-in-branch `state/daily-data-update.json`, and HMAC ledger `state/telegram-ledger.json`.

- [ ] **Step 1: Write failing documentation contract tests**

Replace assertions for 03:17, five-minute refresh, 09:07 and 19–25. Require the new schedule, `>=20`, old-snapshot warning, retry policy, zero-candidate confirmation, runtime-delay caveat and exact Actions manual paths. Assert active docs never claim exact start-time guarantees or expose raw state recipients.

- [ ] **Step 2: Run docs tests and verify RED**

Run: `python -m pytest -q tests/test_github_only_docs.py`

Expected: FAIL because active docs still describe old schedules and bounded threshold.

- [ ] **Step 3: Update the runbooks**

Document normal evening success, first-failure alert, hourly recovery, all-failed morning behavior and how to inspect safe state without copying secrets. State clearly that GitHub scheduled jobs may start late, but runtime guard and catch-up runs preserve the business-day semantics.

- [ ] **Step 4: Update deployment status without claiming unobserved production success**

Record implementation/test status separately from real-cycle observation. Leave the 18:45 and following 09:00 cycle as pending until GitHub run URLs and Telegram receipt are actually observed.

- [ ] **Step 5: Run docs tests and verify GREEN**

Run: `python -m pytest -q tests/test_github_only_docs.py`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add README.md docs/CLOUD_DEPLOYMENT.md docs/TELEGRAM_GROUP.md docs/DEPLOYMENT_STATUS.md tests/test_github_only_docs.py .env.example
git commit -m "docs: explain daily data and Telegram operations"
```

### Task 7: Verify, review and release safely

**Files:**
- Modify only files required by review findings.

- [ ] **Step 1: Run the complete backend suite**

Run: `python -m pytest -q`

Expected: all tests PASS; no warnings promoted to errors.

- [ ] **Step 2: Verify the unchanged frontend contract**

Run: `cd frontend && npm test && npm run lint && npm run build`

Expected: all Vitest tests PASS, ESLint has zero warnings, TypeScript/Vite build succeeds. No frontend behavior change is expected because manifest/snapshot public paths stay stable.

- [ ] **Step 3: Run workflow lint again**

Run: `docker run --rm -v "$PWD:/repo" -w /repo rhysd/actionlint:latest`

Expected: no diagnostics.

- [ ] **Step 4: Run a secret-safe temporary publication simulation**

Using a temporary publication root only, seed a valid old snapshot, simulate failed scheduled data, recovered scheduled data, failure notification dry-run, stale morning dry-run and fresh morning dry-run. Run `scripts/verify_cloud_contracts.py --publication-root <temp-root>` after each state transition. Inspect only safe JSON keys; never inject real Telegram values.

- [ ] **Step 5: Request a fresh code review**

Review specifically against all five Review Focus items and the approved spec. Fix issues with a failing regression test first, then rerun focused and full verification.

- [ ] **Step 6: Commit any review-only fixes**

```bash
git add <reviewed-files>
git commit -m "fix: address daily workflow review findings"
```

Skip this commit if review required no changes.

- [ ] **Step 7: Push `develop` and observe dry-run/manual behavior**

Push normally without force. Confirm CI, Pages and contract verification are green. While `NOTIFICATION_DRY_RUN=true`, run manual data and daily Telegram paths and inspect only status/reason/count fields plus HMAC ledger structure.

- [ ] **Step 8: Enable real delivery and observe one full production cycle**

After dry-run validation, restore `NOTIFICATION_DRY_RUN=false`. Observe a real 18:45 data cycle (including retry behavior if needed) and the following 09:00 report. Record non-secret workflow URLs and outcome in `docs/DEPLOYMENT_STATUS.md`; do not mark rollout complete before both observations.

---

## Expected commit sequence

1. `feat: add daily data update state contract`
2. `feat: report all numbers absent at least twenty days`
3. `feat: coordinate one daily data publication`
4. `feat: send daily reports and first failure alerts`
5. `ci: schedule daily data and Telegram workflows`
6. `docs: explain daily data and Telegram operations`
7. Optional regression-fix and production-observation documentation commits.

## Rollback

Revert the implementation commits on `develop` and let the existing Pages deploy workflow publish the reverted source. Do not delete `gh-pages` state or versioned snapshots: old active data remains readable, and the new namespaced ledger entries do not collide with legacy events. If only Telegram delivery is unsafe, set `NOTIFICATION_DRY_RUN=true` first, then revert notification/workflow changes while preserving the data publication branch.
