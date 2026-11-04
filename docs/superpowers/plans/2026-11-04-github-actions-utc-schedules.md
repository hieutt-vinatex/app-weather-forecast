# GitHub Actions UTC Schedules Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Chuyển lịch data/Telegram sang cron UTC tường minh để các job chạy đúng 18:45 và 09:00 theo giờ Việt Nam.

**Architecture:** GitHub Actions chỉ chịu trách nhiệm kích hoạt bằng UTC; code runtime tiếp tục chuyển clock sang `Asia/Ho_Chi_Minh` và giữ nguyên guard, state cùng ledger. Thay đổi được khóa bằng workflow source contracts và runbook contracts.

**Tech Stack:** GitHub Actions YAML, Python 3.12, pytest, actionlint, Markdown

**Spec:** `docs/superpowers/specs/2026-11-04-github-actions-utc-schedules-design.md`

## Global Constraints

- Data business times remain 18:45 and hourly 19:45–23:45 in `Asia/Ho_Chi_Minh`.
- Telegram business times remain 09:00 through 12:00 in `Asia/Ho_Chi_Minh`.
- Workflow cron values are explicit UTC and contain no `timezone:` field.
- Runtime guards, event routing, concurrency, permissions and secrets remain unchanged.
- Production remains GitHub-only and free.

## Review Focus

- UTC conversion must not shift any business target by one hour: test every exact cron.
- The retry range must cover local 19:45, 20:45, 21:45, 22:45 and 23:45 exactly.
- Telegram catch-up must cover local 09:00–11:45 plus 12:00 without a gap.
- Source workflows must not retain a `timezone:` field that reintroduces scheduler ambiguity.
- Runbooks must distinguish UTC source cron from Vietnamese operator-facing time.

---

### Task 1: Pin and implement explicit UTC workflow schedules

**Files:**
- Modify: `tests/test_workflow_security.py`
- Modify: `.github/workflows/data-sync.yml`
- Modify: `.github/workflows/telegram.yml`

**Interfaces:**
- Produces data cron values `45 11 * * *` and `45 12-16 * * *`.
- Produces Telegram cron values `0-45/15 2-4 * * *` and `0 5 * * *`.
- Preserves all runtime modes and trust/security boundaries.

- [ ] **Step 1: Change workflow contract tests first**

Assert the four exact UTC cron strings, exactly two schedules per workflow and
zero `timezone:` entries. Preserve existing routing, security and bounded-write
assertions.

- [ ] **Step 2: Run the focused test and verify RED**

Run: `.venv/bin/python -m pytest -q tests/test_workflow_security.py`

Expected: FAIL because workflows still contain local-looking cron values and
`timezone:`.

- [ ] **Step 3: Apply the minimal workflow change**

Replace only the cron values, remove both timezone entries from each workflow
and add short UTC+7 comments. Do not alter job steps or runtime code.

- [ ] **Step 4: Verify GREEN and lint workflows**

Run: `.venv/bin/python -m pytest -q tests/test_workflow_security.py`

Run: `docker run --rm -v "$PWD:/repo" -w /repo rhysd/actionlint:latest`

Expected: all tests PASS and actionlint emits no diagnostics.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/data-sync.yml .github/workflows/telegram.yml tests/test_workflow_security.py
git commit -m "fix: schedule cloud jobs with explicit UTC cron"
```

### Task 2: Document UTC source schedules and the missed notification incident

**Files:**
- Modify: `tests/test_github_only_docs.py`
- Modify: `docs/CLOUD_DEPLOYMENT.md`
- Modify: `docs/TELEGRAM_GROUP.md`
- Modify: `docs/DEPLOYMENT_STATUS.md`

**Interfaces:**
- Consumes the exact UTC cron values from Task 1.
- Preserves operator-facing Vietnamese business times.

- [ ] **Step 1: Add failing documentation contract assertions**

Require the runbooks to state that workflow cron is stored in UTC, list the
conversion boundary, and keep the 18:45/09:00 operator times. Require deployment
status to record the 04/11 missed report without claiming the fix is observed.

- [ ] **Step 2: Run docs tests and verify RED**

Run: `.venv/bin/python -m pytest -q tests/test_github_only_docs.py`

Expected: FAIL because active docs currently imply timezone-aware scheduling.

- [ ] **Step 3: Update runbooks and deployment status**

Explain UTC as an implementation detail, keep all operator instructions in
Vietnamese local time and record the evidence links plus pending next cycle.

- [ ] **Step 4: Run docs tests and verify GREEN**

Run: `.venv/bin/python -m pytest -q tests/test_github_only_docs.py`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_github_only_docs.py docs/CLOUD_DEPLOYMENT.md docs/TELEGRAM_GROUP.md docs/DEPLOYMENT_STATUS.md
git commit -m "docs: explain UTC workflow schedules"
```

### Task 3: Verify, review and release

**Files:**
- Modify only files required by review findings.

- [ ] **Step 1: Run full backend and frontend verification**

Run: `.venv/bin/python -m pytest -q`

Run: `cd frontend && npm test && npm run lint && npm run build`

Expected: all suites PASS.

- [ ] **Step 2: Run actionlint and inspect the final diff**

Run: `docker run --rm -v "$PWD:/repo" -w /repo rhysd/actionlint:latest`

Run: `git diff --check`

Expected: no diagnostics.

- [ ] **Step 3: Request one fresh whole-branch review**

Review against the five Review Focus bullets and production incident evidence.
Fix Critical/Important findings via RED→GREEN before continuing.

- [ ] **Step 4: Push `develop` and observe deployment workflows**

Push without force. Confirm remote SHA equality, CI success and Pages success.
Leave the real 18:45 → 09:00 observation pending until those times occur.
