# Filesystem Retention Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent the fourth and later filesystem publications from failing the three-version contract because of an empty pruned directory.

**Architecture:** Keep retention ownership in `SnapshotPublisher` and make the filesystem store fully remove a deleted version once its last recognized payload is gone. Keep the verifier strict so any real fourth version still blocks publication.

**Tech Stack:** Python 3.12, pytest, filesystem-backed JSON store, GitHub Actions

**Spec:** `docs/superpowers/specs/2026-11-04-filesystem-retention-cleanup-design.md`

## Global Constraints

- Retain at most three complete snapshot versions.
- Never weaken `verify_cloud_contracts.py` or delete non-empty directories.
- Do not change cron, parser, schemas, Telegram state, or unrelated publication files.
- Deliver directly to `develop` without force-push.

## Review Focus

- A fourth publication leaves exactly three version directories, not three versions plus an empty directory.
- Each retained directory still contains history and all three snapshots.
- Unrelated site assets and Telegram state survive pruning.
- Deleting a missing key remains idempotent.
- Real fourth-version content still fails the verifier if retention is genuinely exceeded.

---

### Task 1: Remove empty pruned version directories

**Files:**
- Modify: `tests/test_cloud_publisher.py`
- Modify: `app/cloud/filesystem_store.py:97-101`

**Interfaces:**
- Consumes: `FilesystemJsonStore.delete(key: str) -> None`
- Produces: the same interface, with complete cleanup of an empty version directory

- [ ] **Step 1: Extend the real filesystem regression test**

In `test_filesystem_publication_keeps_three_versions_and_unrelated_files`,
assert that four publishes leave exactly three directories and that each contains
`history.json`, `snapshot-30.json`, `snapshot-60.json`, and `snapshot-90.json`.

- [ ] **Step 2: Run the test and verify RED**

Run: `.venv/bin/python -m pytest -q tests/test_cloud_publisher.py::test_filesystem_publication_keeps_three_versions_and_unrelated_files`

Expected: FAIL because four directories remain and the oldest is empty.

- [ ] **Step 3: Implement the minimal filesystem cleanup**

After unlinking a versioned JSON path in `FilesystemJsonStore.delete`, call
`Path.rmdir()` on its parent and ignore `OSError` when it is still non-empty.
Only attempt this for paths directly under `site/data/versions/<version>`.

- [ ] **Step 4: Verify GREEN and related contracts**

Run: `.venv/bin/python -m pytest -q tests/test_cloud_publisher.py tests/test_cloud_contracts.py`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/cloud/filesystem_store.py tests/test_cloud_publisher.py docs/superpowers/specs/2026-11-04-filesystem-retention-cleanup-design.md docs/superpowers/plans/2026-11-04-filesystem-retention-cleanup.md
git commit -m "fix: remove pruned snapshot directories"
```

### Task 2: Verify, review and release

**Files:**
- Modify only files required by review findings.

**Interfaces:**
- Consumes: Task 1 filesystem retention behavior
- Produces: verified `develop` release ready for the next full or scheduled sync

- [ ] **Step 1: Run full local verification**

Run: `.venv/bin/python -m pytest -q`

Run: `cd frontend && npm test && npm run lint && npm run build`

Run: `docker run --rm -v "$PWD:/repo" -w /repo rhysd/actionlint:latest`

Run: `git diff --check`

Expected: all commands PASS with no new diagnostics.

- [ ] **Step 2: Request one fresh whole-branch review**

Review the regression, directory cleanup boundary, non-empty directory safety,
and preservation of unrelated publication files. Fix Critical/Important findings.

- [ ] **Step 3: Push and verify cloud delivery**

Push `develop` without force. Confirm local/remote SHA equality, CI success and
Pages success. Then use a full data sync (manual when an authenticated dispatcher
is available, otherwise the next 18:45 schedule) and verify that production
manifest/history contains a complete 03/11/2026 record.
