#!/usr/bin/env python3
"""Run bounded cloud data and Telegram jobs from GitHub Actions."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

import aiohttp

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.cloud.cloudflare_kv import CloudflareKVStore  # noqa: E402
from app.cloud.data_jobs import DataJobResult, run_data_job  # noqa: E402
from app.config import Settings, get_settings  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run finite cloud jobs")
    subparsers = parser.add_subparsers(dest="command", required=True)
    sync = subparsers.add_parser("sync", help="publish data snapshots")
    sync.add_argument("--mode", choices=("full", "incremental"), required=True)
    sync.add_argument("--request-id")
    return parser


async def _run_sync(args: argparse.Namespace, settings: Settings) -> DataJobResult:
    config = settings.require_cloud_job_config()
    timeout = aiohttp.ClientTimeout(total=settings.source_timeout_seconds + 5)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        store = CloudflareKVStore(
            config.account_id,
            config.namespace_id,
            config.api_token,
            session,
        )
        return await run_data_job(
            settings,
            store,
            mode=args.mode,
            request_id=args.request_id,
            clock=lambda: datetime.now(settings.tzinfo),
        )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        settings = get_settings()
        config = settings.require_cloud_job_config()
        result = asyncio.run(
            asyncio.wait_for(
                _run_sync(args, settings),
                timeout=config.job_timeout_seconds,
            )
        )
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
                "version": result.version,
                "recordCount": result.record_count,
                "reason": result.reason,
            },
            ensure_ascii=False,
        )
    )
    return 0 if result.status in {"succeeded", "no_change"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
