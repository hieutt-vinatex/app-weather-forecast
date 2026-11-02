#!/usr/bin/env python3
"""Run bounded cloud data and Telegram jobs from GitHub Actions."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Awaitable, Callable, TypeVar

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.cloud.data_jobs import DataJobResult, run_data_job  # noqa: E402
from app.cloud.filesystem_store import FilesystemJsonStore  # noqa: E402
from app.cloud.notification_jobs import (  # noqa: E402
    CloudNotificationResult,
    run_manual_notification,
    run_scheduled_notification,
)
from app.config import Settings, get_settings  # noqa: E402

JobResult = DataJobResult | CloudNotificationResult
ResultT = TypeVar("ResultT")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run finite cloud jobs")
    subparsers = parser.add_subparsers(dest="command", required=True)
    sync = subparsers.add_parser("sync", help="publish data snapshots")
    sync.add_argument("--mode", choices=("full", "incremental"), required=True)
    sync.add_argument("--request-id")
    sync.add_argument("--store-root", type=Path, required=True)
    telegram = subparsers.add_parser("telegram", help="send Telegram reports")
    telegram.add_argument("--mode", choices=("scheduled", "manual"), required=True)
    telegram.add_argument("--request-id")
    telegram.add_argument("--store-root", type=Path, required=True)
    return parser


async def _run_sync(args: argparse.Namespace, settings: Settings) -> DataJobResult:
    config = settings.github_job_config()
    store = FilesystemJsonStore(
        args.store_root,
        max_value_bytes=config.max_value_bytes,
    )
    return await run_data_job(
        settings,
        store,
        mode=args.mode,
        request_id=args.request_id,
        clock=lambda: datetime.now(settings.tzinfo),
    )


async def _run_telegram(
    args: argparse.Namespace, settings: Settings
) -> CloudNotificationResult:
    config = settings.github_job_config()
    store = FilesystemJsonStore(
        args.store_root,
        max_value_bytes=config.max_value_bytes,
    )
    clock = lambda: datetime.now(settings.tzinfo)
    if args.mode == "scheduled":
        return await run_scheduled_notification(
            settings, store, clock=clock
        )
    if not args.request_id:
        raise ValueError("--request-id is required for manual Telegram mode")
    return await run_manual_notification(
        settings,
        store,
        args.request_id,
        clock=clock,
    )


def _run_async(awaitable: Awaitable[ResultT], timeout: float) -> ResultT:
    return asyncio.run(asyncio.wait_for(awaitable, timeout=timeout))


def main(
    argv: list[str] | None = None,
    *,
    settings_factory: Callable[[], Settings] = get_settings,
    run_async: Callable[[Awaitable[JobResult], float], JobResult] = _run_async,
) -> int:
    args = build_parser().parse_args(argv)
    try:
        settings = settings_factory()
        config = settings.github_job_config()
        if not args.store_root.is_dir():
            raise ValueError("publication root is not a directory")
        if args.command == "telegram":
            settings.require_notification_ledger_hmac_key()
        coroutine = (
            _run_sync(args, settings)
            if args.command == "sync"
            else _run_telegram(args, settings)
        )
        result = run_async(coroutine, config.job_timeout_seconds)
    except ValueError as exc:
        print(f"cloud job configuration error: {exc}", file=sys.stderr)
        return 2
    except asyncio.TimeoutError:
        print("cloud job timed out", file=sys.stderr)
        return 1
    except Exception:
        print("cloud job failed", file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "status": result.status,
                "mode": result.mode,
                "version": getattr(result, "version", None),
                "recordCount": getattr(result, "record_count", None),
                "deliveredCount": getattr(result, "delivered_count", None),
                "failedCount": getattr(result, "failed_count", None),
                "reason": result.reason,
            },
            ensure_ascii=False,
        )
    )
    successful_statuses = {
        "succeeded",
        "no_change",
        "delivered",
        "already_delivered",
        "dry_run",
        "not_due",
        "waiting",
        "expired",
        "no_match",
    }
    return 0 if result.status in successful_statuses else 1


if __name__ == "__main__":
    raise SystemExit(main())
