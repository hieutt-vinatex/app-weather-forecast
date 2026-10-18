"""FastAPI application entrypoint.

Wires the shared aiohttp session, data service, event broker and centralized
realtime poller together via the lifespan, and mounts the REST + SSE routers.

Run locally:
    uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

Production (in-memory architecture requires a single worker):
    uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.gdb_router import router as gdb_router
from app.api.notification_router import router as notification_router
from app.api.realtime_router import router as realtime_router
from app.config import get_settings
from app.notifications import NotificationService
from app.realtime.broker import EventBroker
from app.services.gdb_service import GdbService
from app.services.realtime_service import RealtimeService
from app.utils.fetcher import Fetcher


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    _configure_logging(settings.log_level)
    logger = logging.getLogger("app.main")

    fetcher = Fetcher(
        total_timeout=settings.source_timeout_seconds,
        connect_timeout=settings.source_connect_timeout_seconds,
        max_retries=settings.source_max_retries,
        max_concurrency=settings.source_max_concurrency,
    )
    await fetcher.start()

    gdb_service = GdbService(settings, fetcher)
    broker = EventBroker()
    realtime = RealtimeService(settings, gdb_service, broker)
    notifications = NotificationService(settings, realtime)

    app.state.settings = settings
    app.state.fetcher = fetcher
    app.state.gdb_service = gdb_service
    app.state.broker = broker
    app.state.realtime = realtime
    app.state.notifications = notifications

    await realtime.start()
    await notifications.start()
    # Warm history in the background so startup is not blocked by 90 fetches.
    import asyncio

    warm_task = asyncio.create_task(realtime.warm(), name="history-warm")
    app.state.warm_task = warm_task

    logger.info("Application startup complete (env=%s)", settings.app_env)
    try:
        yield
    finally:
        logger.info("Application shutting down")
        warm_task.cancel()
        try:
            await warm_task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass
        await notifications.stop()
        await realtime.stop()
        await fetcher.close()
        logger.info("Application shutdown complete")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="XSMB Realtime Results & Statistics API",
        description=(
            "Thu thập đầy đủ ĐB, G1–G7; thống kê và phát trực tiếp tần suất "
            "2 số cuối của từng số XSMB. "
            "Chỉ phục vụ mục đích thống kê, không dự đoán kết quả."
        ),
        version="2.0.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )
    app.include_router(gdb_router)
    app.include_router(realtime_router)
    app.include_router(notification_router)
    return app


app = create_app()
