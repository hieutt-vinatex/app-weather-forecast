# GitHub-only Free Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Chuyển production sang GitHub Pages + GitHub Actions, giữ dashboard tĩnh và Telegram hoạt động hoàn toàn trên cloud với chi phí định kỳ bằng 0.

**Architecture:** Nhánh `develop` chứa mã nguồn, test và workflow; nhánh `gh-pages` chứa `site/` (bundle + snapshot JSON) và `state/` (ledger Telegram đã HMAC). Python jobs đọc/ghi nhánh này qua `FilesystemJsonStore`, còn custom Pages workflows đóng gói riêng `gh-pages/site/` bằng các Actions chính thức. Frontend đọc manifest tĩnh theo base path của repository; mọi thao tác làm mới/gửi ngay chạy từ `workflow_dispatch`.

**Tech Stack:** Python 3.12, Pydantic 2, aiohttp, pytest, React 18, TypeScript 5, TanStack Query 5, Vite 5, Vitest, GitHub Actions, GitHub Pages.

**Spec:** `docs/superpowers/specs/2026-11-02-github-only-free-deployment-design.md`

## Global Constraints

- Production chỉ dùng GitHub; không phụ thuộc Vercel, Cloudflare Worker/KV, FastAPI luôn chạy hoặc máy local.
- Repository phải public để dùng GitHub Pages miễn phí; `develop` phải tiếp tục là default branch để schedule chạy.
- Node phải là 20.x; Python workflow phải là 3.12; múi giờ nghiệp vụ là `Asia/Ho_Chi_Minh`.
- Vite production base path là `/app-weather-forecast/` và URL mặc định là `https://hieutt-vinatex.github.io/app-weather-forecast/`.
- Dữ liệu công khai giữ tối đa 90 ngày, ba snapshot 30/60/90 và ba publication version gần nhất.
- Incremental sync giữ lịch khoảng 5 phút trong 17:47–19:02; độ trễ hiển thị 10–15 phút được chấp nhận.
- Telegram thử từ 09:07 đến 12:07, dùng kỳ hoàn chỉnh mới nhất dù đã cũ, ghi rõ kỳ dữ liệu và chống trùng theo kỳ + target.
- Manual Telegram không cập nhật scheduled ledger; người dùng có thể nhận thêm một tin cùng kỳ.
- Chỉ `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_IDS`, `NOTIFICATION_LEDGER_HMAC_KEY` là production secrets; `NOTIFICATION_DRY_RUN` mặc định `true`.
- Không raw `chat_id`, token, recipient display hoặc provider refresh token nào được ghi vào Git, Pages artifact, log hay frontend bundle.
- Mọi writer của `gh-pages` dùng cùng concurrency group, chỉ push fast-forward và không force-push.
- Pages Settings dùng **Source: GitHub Actions**; không dùng Pages build trực tiếp từ branch.
- Giữ snapshot hợp lệ cuối cùng khi upstream, build, deploy hoặc push lỗi; không công bố output sinh dở.
- Thực hiện TDD, commit sau mỗi task và không đưa generated publication data vào `develop`.

## Review Focus

- Manifest active bị thiếu/hỏng trong lúc CDN lan truyền phải fallback về `previousPublication`, không làm dashboard trắng — test ở Task 4.
- Incremental sync thất bại phải giữ manifest/snapshot active nhưng công bố job status `failed` để freshness hạ xuống `delayed` — test ở Task 2 và Task 4.
- Snapshot mới nhất cũ hơn hôm qua vẫn phải gửi scheduled Telegram đúng một lần cho mỗi target, không lộ target trong ledger — test ở Task 3.
- Hai workflow cùng ghi `gh-pages` không được force-push hoặc ghi đè `site/data`, `state` hay bundle của nhau — kiểm tra workflow ở Task 7.
- URL dưới repository subpath và cache CDN phải luôn tải manifest mới theo bucket nhưng cache snapshot versioned bất biến — test ở Task 4 và Task 5.

---

## File structure

### Python publication and jobs

- Create `app/cloud/filesystem_store.py`: ánh xạ logical JSON keys sang cây `gh-pages`, đọc/ghi atomic, list/delete version.
- Reuse `app/cloud/contracts.py`: `JobRecord` là contract cho public `status.json`; không tạo schema trùng lặp.
- Modify `app/cloud/publisher.py`: tiếp tục manifest-last trên filesystem và giữ ba version.
- Modify `app/cloud/data_jobs.py`: ghi final data job status công khai kể cả khi sync thất bại.
- Modify `app/cloud/notification_store.py`: đổi tên store trung lập KV và giữ ledger/provider sections tương thích.
- Modify `app/cloud/notification_jobs.py`: scheduled mode đánh giá kỳ hoàn chỉnh mới nhất, Telegram-only và HMAC target keys.
- Modify `app/notifications/channels.py`: hỗ trợ allowed channels và keyed target identifier.
- Modify `app/config.py`: cấu hình job GitHub/Pages và secret HMAC, bỏ validation bắt buộc Cloudflare.
- Modify `scripts/cloud_job.py`: dùng filesystem publication root thay cho Cloudflare REST.
- Create `scripts/prepare_pages.py`: cài bundle Vite vào `gh-pages/site/` mà giữ data/state.
- Modify `scripts/verify_cloud_contracts.py`: kiểm tra publication tree, contract và secret leakage.

### Frontend

- Create `frontend/src/api/publication.ts`: manifest/status types, validation và URL resolution.
- Modify `frontend/src/api/client.ts`: tải manifest tĩnh, snapshot immutable và fallback previous version.
- Modify `frontend/src/config.ts`: base/public settings; bỏ API/admin-operation settings.
- Modify `frontend/src/utils/freshness.ts`: tính đầy đủ ngưỡng active/idle ở client.
- Modify `frontend/src/types/gdb.ts`: bỏ operation types; thêm type cần cho public publication nếu không nằm trong `publication.ts`.
- Create `frontend/src/components/GitHubOperationsLinks.tsx`: hai liên kết quản trị tới Actions workflows.
- Modify `frontend/src/features/dashboard/Dashboard.tsx`: bỏ admin form, gắn links mới.
- Modify `frontend/vite.config.ts`: base path GitHub Pages.
- Delete admin-only files listed in Task 5 and `frontend/vercel.json`.

### Automation, verification and docs

- Create `.github/workflows/deploy-pages.yml`: build frontend after green CI, update `gh-pages/site`, upload and deploy custom Pages artifact.
- Modify `.github/workflows/data-sync.yml`: filesystem sync, commit status/data, deploy artifact.
- Modify `.github/workflows/telegram.yml`: filesystem ledger, Telegram secrets and manual/scheduled modes.
- Modify `.github/workflows/ci.yml`: verify active GitHub-only code; remove Worker job after cleanup.
- Delete `.github/workflows/deploy-worker.yml` and `cloudflare/worker/` after parity gates pass.
- Modify `tests/test_workflow_security.py`: permissions, concurrency, secret and forbidden-provider assertions.
- Modify `README.md`, `docs/CLOUD_DEPLOYMENT.md`, `docs/TELEGRAM_GROUP.md`, `.env.example`, `frontend/.env.example`: GitHub-only setup and operations.
- Create `docs/DEPLOYMENT_STATUS.md` only during cutover to record non-secret production verification.

---

### Task 1: Add the filesystem-backed publication store

**Files:**
- Create: `app/cloud/filesystem_store.py`
- Modify: `app/cloud/publisher.py`
- Create: `tests/test_filesystem_store.py`
- Modify: `tests/test_cloud_publisher.py`

**Interfaces:**
- Consumes: `JsonStore`, `MANIFEST_KEY`, `DATA_JOB_STATUS_KEY`, `TELEGRAM_JOB_STATUS_KEY`, `NOTIFICATION_STATE_KEY`, `history_key()`, `snapshot_key()`, `operation_key()` from `app.cloud.contracts`.
- Produces: `FilesystemJsonStore(root: Path, *, max_value_bytes: int = 20 * 1024 * 1024)` implementing `get_json`, `put_json`, `delete`, `list_keys`; `path_for_key(key: str) -> Path` for diagnostics/tests.

- [ ] **Step 1: Write failing key-mapping and CRUD tests**

Add tests asserting these exact mappings under a temporary branch root:

```python
assert store.path_for_key("manifest:v1") == root / "site/data/manifest.json"
assert store.path_for_key("job-status:v1:data") == root / "site/data/status.json"
assert store.path_for_key("notification-state:v1") == root / "state/telegram-ledger.json"
assert store.path_for_key("history:v1:v1") == root / "site/data/versions/v1/history.json"
assert store.path_for_key("snapshot:v1:v1:30") == root / "site/data/versions/v1/snapshot-30.json"
```

Also assert round-trip UTF-8 JSON, sorted `list_keys("history:v1:")`, delete, max-size rejection and rejection of unknown/path-traversal keys.

- [ ] **Step 2: Run the new tests and verify red**

Run: `pytest -q tests/test_filesystem_store.py`

Expected: FAIL because `app.cloud.filesystem_store` does not exist.

- [ ] **Step 3: Implement `FilesystemJsonStore` with atomic writes**

Serialize compact UTF-8 JSON to a temporary file in the destination directory, flush/close, then `os.replace()` it. Never resolve a caller-provided key into a raw path; use an explicit key parser. Accept `expiration_ttl` for protocol compatibility but do not depend on filesystem TTL for correctness.

- [ ] **Step 4: Add publisher integration coverage**

Assert `SnapshotPublisher.publish()` creates manifest/history/30/60/90 files at the exact tree, writes manifest last, `load_active_history()` round-trips, and pruning retains three versions without deleting `state/` or `site/assets/`.

- [ ] **Step 5: Run store and publisher tests**

Run: `pytest -q tests/test_filesystem_store.py tests/test_cloud_publisher.py`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/cloud/filesystem_store.py app/cloud/publisher.py tests/test_filesystem_store.py tests/test_cloud_publisher.py
git commit -m "feat: add filesystem publication store"
```

### Task 2: Run data jobs against `gh-pages` state

**Files:**
- Modify: `app/config.py`
- Modify: `app/cloud/data_jobs.py`
- Modify: `scripts/cloud_job.py`
- Modify: `tests/test_cloud_data_jobs.py`
- Modify: `tests/test_cloud_cli.py`
- Modify: `.env.example`

**Interfaces:**
- Consumes: `FilesystemJsonStore` from Task 1 and existing `run_data_job(settings, store, *, mode, request_id, clock)`.
- Produces: CLI `python scripts/cloud_job.py sync --mode full|incremental --store-root PATH`; `GithubJobConfig(max_value_bytes, operation_ttl_seconds, job_timeout_seconds)` returned by `Settings.github_job_config()`.

- [ ] **Step 1: Write failing CLI tests for filesystem mode**

Cover a full sync with a temporary `--store-root`, absence of all Cloudflare env vars, safe missing-path/config errors, timeout exit `1`, and a failed incremental sync that leaves `site/data/manifest.json` unchanged while writing `site/data/status.json` with `status == "failed"`.

- [ ] **Step 2: Run CLI/data tests and verify red**

Run: `pytest -q tests/test_cloud_cli.py tests/test_cloud_data_jobs.py`

Expected: FAIL because the CLI still requires Cloudflare configuration.

- [ ] **Step 3: Replace Cloudflare job configuration with GitHub publication configuration**

Add exact environment-backed settings:

```text
PUBLICATION_MAX_VALUE_BYTES=20971520
PUBLICATION_OPERATION_TTL_SECONDS=86400
GITHUB_JOB_TIMEOUT_SECONDS=1200
```

Keep local FastAPI settings independent. `GithubJobConfig` must never contain provider credentials.

- [ ] **Step 4: Switch sync CLI to `FilesystemJsonStore`**

Parse `--store-root` as `Path`, construct the store with the configured max size and remove the Cloudflare session/import from this execution path. Preserve bounded `asyncio.wait_for`, JSON summary and non-zero status behavior.

- [ ] **Step 5: Pin failure-status behavior**

Ensure the running/terminal `DATA_JOB_STATUS_KEY` is written through the filesystem store. A failed refresh must not update `manifest:v1`; it must leave the last valid snapshots readable and persist a safe reason without exception text containing URLs or credentials.

- [ ] **Step 6: Run focused tests**

Run: `pytest -q tests/test_cloud_cli.py tests/test_cloud_data_jobs.py tests/test_cloud_publisher.py`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add app/config.py app/cloud/data_jobs.py scripts/cloud_job.py tests/test_cloud_data_jobs.py tests/test_cloud_cli.py .env.example
git commit -m "feat: run data sync from Pages publication state"
```

### Task 3: Preserve Telegram delivery with latest-data and public-safe ledger

**Files:**
- Modify: `app/config.py`
- Modify: `app/notifications/channels.py`
- Modify: `app/cloud/notification_store.py`
- Modify: `app/cloud/notification_jobs.py`
- Modify: `scripts/cloud_job.py`
- Modify: `tests/test_notifications.py`
- Modify: `tests/test_cloud_notification_jobs.py`
- Modify: `tests/test_cloud_cli.py`
- Modify: `.env.example`

**Interfaces:**
- Consumes: `FilesystemJsonStore`; `evaluate_snapshot_now()`; existing `NotificationDispatcher.send()`.
- Produces: CLI `python scripts/cloud_job.py telegram --mode scheduled|manual --store-root PATH [--request-id UUID]`; `Settings.require_notification_ledger_hmac_key() -> str`; `NotificationDispatcher(..., allowed_channels=frozenset({"telegram"}), target_key_secret=secret)`.

- [ ] **Step 1: Write failing latest-data and idempotency tests**

Add tests for these observable cases:

- at `2026-11-02 09:07+07:00`, a latest complete snapshot dated `2026-10-30` is evaluated and delivered rather than returning `expired`;
- rerunning scheduled mode for the same data date/target returns `already_delivered`;
- a failed target remains pending while successful targets do not resend;
- manual mode sends even after scheduled success and does not change scheduled ledger;
- dry-run sends nothing and does not mark delivery.

- [ ] **Step 2: Write failing HMAC and Telegram-only tests**

Use a known secret and assert target keys have the expected channel/kind prefix plus a deterministic 64-hex HMAC digest, change when the secret changes, and contain neither full nor last-four raw `chat_id`. Assert cloud jobs expose only Telegram targets even if Zalo/Facebook variables happen to exist, and `telegram-ledger.json` has no sensitive provider data.

- [ ] **Step 3: Run notification tests and verify red**

Run: `pytest -q tests/test_notifications.py tests/test_cloud_notification_jobs.py tests/test_cloud_cli.py`

Expected: FAIL on stale scheduled data and missing HMAC support.

- [ ] **Step 4: Implement keyed target identifiers and Telegram-only cloud dispatch**

Use `hmac.new(secret_bytes, f"{channel}:{kind}:{recipient}".encode(), hashlib.sha256).hexdigest()` for `NotificationTarget.key`. Preserve the unkeyed legacy local path only when the constructor is called without `target_key_secret`; GitHub cloud jobs must fail fast if `NOTIFICATION_LEDGER_HMAC_KEY` is absent.

- [ ] **Step 5: Make scheduled mode use the latest complete snapshot**

Call `evaluate_snapshot_now()` from the scheduled job because the workflow owns the morning time window. Keep event key as `<reference-date>:19-25`, keep the message’s “Kỳ dữ liệu”, and retain completeness checks for every required date.

- [ ] **Step 6: Rename the JSON notification state implementation**

Rename `KVNotificationStateStore` to `JsonNotificationStateStore` with a compatibility alias only if legacy tests still import the old name. Scheduled mode persists only HMAC target keys/no-match flags; manual mode never calls `mark_sent`.

- [ ] **Step 7: Run notification suite**

Run: `pytest -q tests/test_notifications.py tests/test_cloud_notification_jobs.py tests/test_cloud_cli.py`

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add app/config.py app/notifications/channels.py app/cloud/notification_store.py app/cloud/notification_jobs.py scripts/cloud_job.py tests/test_notifications.py tests/test_cloud_notification_jobs.py tests/test_cloud_cli.py .env.example
git commit -m "feat: persist safe Telegram delivery state on GitHub"
```

### Task 4: Read versioned static snapshots in the frontend

**Files:**
- Create: `frontend/src/api/publication.ts`
- Create: `frontend/src/api/publication.test.ts`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/api/client.test.ts`
- Modify: `frontend/src/config.ts`
- Modify: `frontend/src/hooks/useGdbSnapshot.ts`
- Modify: `frontend/src/hooks/hooks.test.tsx`
- Modify: `frontend/src/utils/freshness.ts`
- Modify: `frontend/src/utils/freshness.test.ts`
- Modify: `frontend/src/types/gdb.ts`

**Interfaces:**
- Consumes: static files at `${BASE_URL}data/manifest.json`, `status.json`, and `versions/<version>/snapshot-<days>.json`.
- Produces: `fetchPublication(now?: number, signal?: AbortSignal)`, `snapshotPath(version: string, days: RangeDays)`, `fetchSnapshot(days, signal?) -> Promise<SnapshotResponse>` and exact client-side freshness calculation.

- [ ] **Step 1: Write failing manifest validation/URL tests**

Assert valid schema version `1`, valid active version, optional previous version, all 30/60/90 pointers, and rejection of traversal/invalid version strings. Under base `/app-weather-forecast/`, assert active URL exactly `/app-weather-forecast/data/versions/<version>/snapshot-30.json` and manifest cache-buster remains stable within a 30-second bucket but changes across buckets.

- [ ] **Step 2: Write failing fetch/fallback tests**

Cover active snapshot success, active `404` followed by previous-version success, both invalid leading to a safe `ApiError`, optional missing status file, failed latest job overriding `meta.lastJobStatus`, and preservation of cached data when a later poll fails.

- [ ] **Step 3: Write exact freshness boundary tests**

Pin `17:45–19:00` boundaries at 10/20 minutes and idle boundaries at 26/48 hours. Assert failed job changes otherwise-current to `delayed`, stale age remains `stale`, offline remains `offline`, and malformed timestamps are `stale`.

- [ ] **Step 4: Run frontend focused tests and verify red**

Run: `cd frontend && npm test -- src/api/publication.test.ts src/api/client.test.ts src/utils/freshness.test.ts src/hooks/hooks.test.tsx`

Expected: FAIL because the frontend still calls `/api/gdb` and freshness lacks delayed thresholds.

- [ ] **Step 5: Implement static publication parsing and immutable snapshot cache**

Validate untrusted JSON before use. Cache snapshots by `<version>:<days>`, fetch manifest/status with `cache: "no-store"` plus the 30-second bucket, fetch versioned snapshots with `cache: "force-cache"`, and only fallback to `previousPublication.version`.

- [ ] **Step 6: Implement client-side freshness**

Derive `current/delayed/stale` from `generatedAt` and Vietnam local time with the exact global thresholds. Respect `lastJobStatus == "failed"` and existing offline/request-failure behavior; never alter the snapshot data itself.

- [ ] **Step 7: Run the frontend data tests**

Run: `cd frontend && npm test -- src/api/publication.test.ts src/api/client.test.ts src/utils/freshness.test.ts src/hooks/hooks.test.tsx`

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/api frontend/src/config.ts frontend/src/hooks frontend/src/utils/freshness.ts frontend/src/utils/freshness.test.ts frontend/src/types/gdb.ts
git commit -m "feat: load dashboard data from GitHub Pages"
```

### Task 5: Remove dashboard administration and configure the Pages subpath

**Files:**
- Create: `frontend/src/components/GitHubOperationsLinks.tsx`
- Create: `frontend/src/components/GitHubOperationsLinks.test.tsx`
- Modify: `frontend/src/features/dashboard/Dashboard.tsx`
- Modify: `frontend/vite.config.ts`
- Modify: `frontend/.env.example`
- Delete: `frontend/src/components/AdminOperations.tsx`
- Delete: `frontend/src/components/AdminOperations.test.tsx`
- Delete: `frontend/src/hooks/useCloudOperation.ts`
- Delete: `frontend/src/hooks/useManualRefresh.ts`
- Delete: `frontend/src/hooks/useSendAbsenceNotification.ts`
- Delete: `frontend/vercel.json`

**Interfaces:**
- Consumes: public GitHub workflow URLs for `data-sync.yml` and `telegram.yml`.
- Produces: a read-only dashboard with two external text links to GitHub Actions and Vite `base: "/app-weather-forecast/"`.

- [ ] **Step 1: Write failing dashboard links test**

Assert the component has no password input and no direct-operation button, and exposes exactly these safe external links with `rel="noreferrer"`:

```text
https://github.com/hieutt-vinatex/app-weather-forecast/actions/workflows/data-sync.yml
https://github.com/hieutt-vinatex/app-weather-forecast/actions/workflows/telegram.yml
```

- [ ] **Step 2: Run component test and verify red**

Run: `cd frontend && npm test -- src/components/GitHubOperationsLinks.test.tsx src/components/AdminOperations.test.tsx`

Expected: FAIL because the new component does not exist and the old admin UI remains.

- [ ] **Step 3: Replace the admin UI and delete operation-only code**

Render a compact “Quản trị qua GitHub Actions” section with explanatory text. Delete operation hooks/types/API functions only after `rg "startOperation|fetchOperation|AdminOperations|useCloudOperation" frontend/src` shows no consumers.

- [ ] **Step 4: Configure Vite and public environment**

Set `base: "/app-weather-forecast/"`; retain only non-secret polling/cache settings in `frontend/.env.example`; remove Vercel routing/config and `VITE_API_BASE_URL`.

- [ ] **Step 5: Run frontend suite and build with Node 20**

Run: `cd frontend && npm test && npm run lint && npm run build`

Expected: all tests/lint pass; `dist/index.html` assets begin with `/app-weather-forecast/`; no `VITE_API_BASE_URL`, admin token copy or `/api/gdb` remains in `dist`.

- [ ] **Step 6: Commit**

```bash
git add -A frontend
git commit -m "feat: prepare dashboard for GitHub Pages"
```

### Task 6: Build and verify the publication tree safely

**Files:**
- Create: `scripts/prepare_pages.py`
- Create: `tests/test_prepare_pages.py`
- Modify: `scripts/verify_cloud_contracts.py`
- Modify: `tests/test_cloud_contracts.py`

**Interfaces:**
- Consumes: Vite `dist/`, branch root and filesystem-store layout from Task 1.
- Produces: `install_site(publication_root: Path, dist_root: Path) -> None`; CLI `python scripts/prepare_pages.py --publication-root PATH --dist-root PATH`; verifier CLI `python scripts/verify_cloud_contracts.py --publication-root PATH`.

- [ ] **Step 1: Write failing site-install tests**

Assert install replaces old HTML/assets, preserves `site/data/**` and `state/**`, creates `.nojekyll`, creates `404.html` from `index.html`, rejects a dist without `index.html`, and leaves the original publication tree unchanged when staging validation fails.

- [ ] **Step 2: Write failing publication-contract/security tests**

Build a realistic temporary tree and assert the verifier checks manifest/status/history/three snapshots, active/previous paths, maximum 90 records, at most three retained versions, ledger schema, and absence of supplied bot token/raw chat IDs/HMAC secret in every publishable file.

- [ ] **Step 3: Run tests and verify red**

Run: `pytest -q tests/test_prepare_pages.py tests/test_cloud_contracts.py`

Expected: FAIL because the installer and publication-root verifier do not exist.

- [ ] **Step 4: Implement staged site installation**

Assemble a sibling temporary `site/`, copy existing `site/data`, copy the new dist, add fallback files, validate, then replace the worktree’s `site/`. Do not run Git commands inside this helper.

- [ ] **Step 5: Extend contract verification for the real tree**

Reuse the existing JSON validators; add path resolution and ledger/status checks rather than duplicating schema logic. Return non-zero with safe filenames/categories only—never echo secret values or raw file content.

- [ ] **Step 6: Run focused verification tests**

Run: `pytest -q tests/test_prepare_pages.py tests/test_cloud_contracts.py`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add scripts/prepare_pages.py scripts/verify_cloud_contracts.py tests/test_prepare_pages.py tests/test_cloud_contracts.py
git commit -m "feat: prepare and verify Pages artifacts"
```

### Task 7: Replace provider workflows with GitHub Pages automation

**Files:**
- Create: `.github/workflows/deploy-pages.yml`
- Modify: `.github/workflows/data-sync.yml`
- Modify: `.github/workflows/telegram.yml`
- Modify: `.github/workflows/ci.yml`
- Delete: `.github/workflows/deploy-worker.yml`
- Modify: `tests/test_workflow_security.py`

**Interfaces:**
- Consumes: CLIs/helpers from Tasks 2, 3 and 6; branch `gh-pages`; GitHub secrets/variable from Global Constraints.
- Produces: CI-gated site deploy, scheduled/manual data deploy and scheduled/manual Telegram ledger updates.

- [ ] **Step 1: Write failing workflow structure/security tests**

Assert all three writers use exact concurrency group `github-pages-publication` with `cancel-in-progress: false`; no `force`, Cloudflare/Vercel secret, `repository_dispatch` or raw secret echo exists; data/site workflows use official `configure-pages@v5`, `upload-pages-artifact@v4`, `deploy-pages@v4`; only deploy jobs receive `pages: write` and `id-token: write`; Telegram receives only `contents: write` plus read defaults.

- [ ] **Step 2: Pin schedule/manual behavior in tests**

Assert full sync `03:17`, incremental `17:47–19:02`, Telegram `09:07–12:07`, data inputs `full|incremental`, Telegram inputs `scheduled|manual`, Node 20, Python 3.12, `NOTIFICATION_DRY_RUN` default true, and all publication commands use `--store-root publication`.

- [ ] **Step 3: Run workflow tests and actionlint to verify red**

Run: `pytest -q tests/test_workflow_security.py`

Run: `docker run --rm -v "$PWD:/repo" -w /repo rhysd/actionlint:latest`

Expected: tests FAIL against provider workflows; existing workflows remain syntactically valid.

- [ ] **Step 4: Implement CI-gated site publication**

Trigger from successful same-repository `CI` push on `develop`; checkout the tested SHA and `gh-pages`, initializing an orphan branch only when absent; build frontend; run `prepare_pages.py`; verify; commit/push fast-forward; upload only `publication/site`; deploy to environment `github-pages`.

- [ ] **Step 5: Implement data sync publication**

Checkout `develop` and `gh-pages`, run filesystem CLI, verify and commit changed data/status, then upload/deploy `publication/site`. Use `continue-on-error` only around the sync command so a failed refresh can still publish `status.json`; after safe deployment, return non-zero when the sync failed. Never change manifest on failure.

- [ ] **Step 6: Implement Telegram workflow**

Checkout the same publication state, pass only Telegram/HMAC secrets, run scheduled/manual mode, verify ledger contains no secret material, commit `state/` if changed and do not deploy Pages because `state/` is excluded from the artifact.

- [ ] **Step 7: Implement fast-forward conflict handling**

Before each push, fetch `origin/gh-pages`; if remote advanced, reload and reapply the bounded site/data/ledger change at most three times. Fail rather than force-push. The workflow log may print commit IDs and paths but no environment values.

- [ ] **Step 8: Run workflow gates**

Run: `pytest -q tests/test_workflow_security.py`

Run: `docker run --rm -v "$PWD:/repo" -w /repo rhysd/actionlint:latest`

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add .github/workflows tests/test_workflow_security.py
git commit -m "ci: deploy dashboard and jobs with GitHub only"
```

### Task 8: Rewrite deployment and operations documentation

**Files:**
- Modify: `README.md`
- Modify: `docs/CLOUD_DEPLOYMENT.md`
- Modify: `docs/TELEGRAM_GROUP.md`
- Modify: `docs/INSTALLATION.md`
- Modify: `.env.example`
- Modify: `frontend/.env.example`
- Create: `tests/test_github_only_docs.py`

**Interfaces:**
- Consumes: final workflow names, inputs, secrets, schedules and URLs from Tasks 5–7.
- Produces: an end-to-end setup/runbook that requires only GitHub UI after code is pushed.

- [ ] **Step 1: Write failing documentation contract tests**

Assert active docs name all three secrets, dry-run variable, Pages **Source: GitHub Actions**, public repository requirement, default branch requirement, bootstrap order, both Run workflow paths, schedules, 10–15 minute delay, latest-data Telegram behavior, rollback and scheduled-workflow delay/disable caveats. Assert active docs do not instruct setup of Vercel/Cloudflare.

- [ ] **Step 2: Run docs test and verify red**

Run: `pytest -q tests/test_github_only_docs.py`

Expected: FAIL because current runbook describes three providers.

- [ ] **Step 3: Rewrite the production runbook**

Document this exact order: make repository public; confirm `develop` default; select Pages GitHub Actions source; add secrets/variable; push code; wait for CI/site deploy; run full sync; check 30/60/90; run Telegram dry-run; enable real Telegram; observe schedules; use Actions UI for manual refresh/send; rollback via commit/manifest.

- [ ] **Step 4: Update Telegram and local documentation**

Keep BotFather/group instructions but replace Cloudflare references with Actions Secrets and HMAC ledger. Make local FastAPI clearly optional and not required for production.

- [ ] **Step 5: Run documentation and secret scans**

Run: `pytest -q tests/test_github_only_docs.py tests/test_workflow_security.py tests/test_cloud_contracts.py`

Expected: PASS; no actual secret values or raw recipient IDs are present.

- [ ] **Step 6: Commit**

```bash
git add README.md docs .env.example frontend/.env.example tests/test_github_only_docs.py
git commit -m "docs: document GitHub-only deployment"
```

### Task 9: Verify integration and perform the GitHub cutover

**Files:**
- Create during cutover: `docs/DEPLOYMENT_STATUS.md`
- Modify only if real UI differs: `docs/CLOUD_DEPLOYMENT.md`

**Interfaces:**
- Consumes: completed GitHub production path, authenticated repository and user-entered Secrets/Variable; legacy provider source remains available only as rollback reference until this task passes.
- Produces: live Pages URL, bootstrapped `gh-pages` state, verified manual/scheduled operations and a non-secret deployment record.

- [ ] **Step 1: Run the complete local verification matrix**

Run: `pytest -q`

Run: `cd frontend && npm ci && npm test && npm run lint && npm run build`

Run: `docker run --rm -v "$PWD:/repo" -w /repo rhysd/actionlint:latest`

Expected: all commands PASS on Python 3.12/Node 20; `git status --short` contains only intentional plan execution changes.

- [ ] **Step 2: Push `develop` and verify CI**

Push normal fast-forward commits to `origin/develop`. Confirm CI uses the pushed SHA and all jobs are green; do not bypass failures or force-push.

- [ ] **Step 3: Complete authenticated GitHub settings**

In repository Settings: keep repository public; confirm default branch `develop`; select Pages **GitHub Actions** source; add `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_IDS`, `NOTIFICATION_LEDGER_HMAC_KEY`; set `NOTIFICATION_DRY_RUN=true`. Values are entered by the user and never pasted into chat/log/commands.

- [ ] **Step 4: Bootstrap the site and data**

Wait for **Deploy GitHub Pages** to create/update `gh-pages`; run **Cloud data sync** manually with `mode=full`; verify workflow green, Pages deployment URL is returned and public manifest/status/30/60/90 snapshot requests are HTTP 200 with valid contracts.

- [ ] **Step 5: Smoke-test the live dashboard**

Open `https://hieutt-vinatex.github.io/app-weather-forecast/`; verify direct refresh, assets under the repository base, 30/60/90 switching, yesterday/history immediate display, freshness labels, no admin password field and working links to both workflows.

- [ ] **Step 6: Verify Telegram safely**

Run scheduled and manual modes with dry-run; inspect only safe summary fields. After the user confirms the target group, set `NOTIFICATION_DRY_RUN=false`, run one manual send, confirm the message and “Kỳ dữ liệu”, then run scheduled mode twice to verify the second scheduled attempt is a no-op for the same target/event.

- [ ] **Step 7: Verify failure and rollback paths**

Run `pytest -q tests/test_cloud_data_jobs.py::test_malformed_current_draw_keeps_previous_manifest tests/test_cloud_contracts.py` to prove a failed sync leaves active manifest unchanged and exposes failed status without touching production data. Then re-run a healthy full sync from Actions and confirm the live manifest advances normally. Verify no workflow uses force-push.

- [ ] **Step 8: Observe one automatic cycle**

Confirm one incremental draw-window run and one morning Telegram window from Actions logs. A delayed start is acceptable; record actual start/end, published version and delivery status without secrets.

- [ ] **Step 9: Record non-secret deployment status**

Write `docs/DEPLOYMENT_STATUS.md` with live URL, deployed commit, first manifest version, workflow run links, verification date and remaining operational caveats. Do not record tokens, chat IDs or HMACs.

- [ ] **Step 10: Commit any verified documentation differences**

```bash
git add docs/DEPLOYMENT_STATUS.md docs/CLOUD_DEPLOYMENT.md
git commit -m "docs: record GitHub Pages cutover"
```

Skip the commit if no file changed.

### Task 10: Remove inactive Cloudflare/Vercel production code after cutover

**Files:**
- Delete: `app/cloud/cloudflare_kv.py`
- Delete: `tests/test_cloudflare_kv.py`
- Delete: `cloudflare/worker/`
- Modify: `app/config.py`
- Modify: `.env.example`
- Modify: `.gitignore`
- Modify: `.github/workflows/ci.yml`
- Modify: `tests/test_workflow_security.py`
- Modify: `docs/DEPLOYMENT_STATUS.md`

**Interfaces:**
- Consumes: successful Pages, data and Telegram smoke tests plus one observed automatic cycle from Task 9.
- Produces: one active production path with no Cloudflare/Vercel build/deploy dependency; local FastAPI/Docker remains available only for legacy development.

- [ ] **Step 1: Add a failing legacy-provider absence test**

Assert active source/workflows/env examples contain no import/reference to `CloudflareKVStore`, Wrangler, `CLOUDFLARE_*`, `VITE_API_BASE_URL` or Vercel deployment. Exclude archived `docs/superpowers/specs/2026-10-29-*` and `docs/superpowers/plans/2026-10-29-*` from this assertion.

- [ ] **Step 2: Run the absence test and verify red**

Run: `pytest -q tests/test_workflow_security.py -k legacy_provider`

Expected: FAIL while legacy provider code/config remains.

- [ ] **Step 3: Delete provider-specific production code and settings**

Remove Worker source/lockfiles/tests, Cloudflare adapter/tests, Cloudflare settings/dataclass fields and obsolete CI job. Keep `aiohttp` because source fetching and Telegram delivery still use it; keep FastAPI/Docker local path untouched. Do not delete external Cloudflare/Vercel resources automatically; the user may retire them manually after the rollback window.

- [ ] **Step 4: Run all automated suites**

Run: `pytest -q`

Run: `cd frontend && npm test && npm run lint && npm run build`

Run: `docker run --rm -v "$PWD:/repo" -w /repo rhysd/actionlint:latest`

Expected: PASS with no Worker suite required.

- [ ] **Step 5: Commit and push the cleanup**

```bash
git add -A app/cloud app/config.py tests cloudflare .env.example .gitignore .github/workflows/ci.yml docs/DEPLOYMENT_STATUS.md
git commit -m "refactor: remove inactive cloud providers"
git push origin develop
```

Confirm the cleanup CI is green and the already-live Pages/data/Telegram paths remain healthy before considering the migration complete.

---

## Final verification gate

Before claiming completion:

1. `pytest -q` passes.
2. `cd frontend && npm test && npm run lint && npm run build` passes on Node 20.
3. actionlint passes all workflows.
4. `rg -n "CLOUDFLARE_|workers.dev|vercel.app|VITE_API_BASE_URL|repository_dispatch" .github app frontend/src .env.example docs/CLOUD_DEPLOYMENT.md docs/TELEGRAM_GROUP.md README.md` returns no active production dependency.
5. Publication verifier passes against the bootstrapped `gh-pages` checkout.
6. GitHub Pages serves active and previous version fallback paths.
7. Telegram real-send is performed only after dry-run and explicit target confirmation.
8. Local `develop`, `origin/develop` and deployed SHA are recorded and reconciled without force-push.

