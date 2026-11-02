"""Notification idempotency state stored through the JSON store contract."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any

from app.cloud.contracts import JsonStore, NOTIFICATION_STATE_KEY
from app.cloud.publisher import StorageReadError


class JsonNotificationStateStore:
    def __init__(self, store: JsonStore) -> None:
        self._store = store
        self._lock = asyncio.Lock()
        self._state: dict[str, Any] | None = None

    async def sent_targets(self, event_key: str) -> set[str]:
        async with self._lock:
            state = await self._load()
            event = state["events"].get(event_key, {})
            targets = event.get("targets", {}) if isinstance(event, dict) else {}
            if not isinstance(targets, dict):
                raise StorageReadError("notification target state is invalid")
            return {key for key in targets if isinstance(key, str)}

    async def mark_sent(
        self,
        event_key: str,
        target_key: str,
        sent_at: datetime,
    ) -> None:
        async with self._lock:
            state = await self._load()
            event = state["events"].setdefault(event_key, {})
            event.setdefault("targets", {})[target_key] = sent_at.isoformat()
            event["updatedAt"] = sent_at.isoformat()
            self._prune(state, sent_at)
            await self._save(state)

    async def is_no_match(self, event_key: str) -> bool:
        async with self._lock:
            state = await self._load()
            event = state["events"].get(event_key, {})
            return bool(event.get("noMatch")) if isinstance(event, dict) else False

    async def mark_no_match(self, event_key: str, checked_at: datetime) -> None:
        async with self._lock:
            state = await self._load()
            event = state["events"].setdefault(event_key, {})
            event["noMatch"] = True
            event["updatedAt"] = checked_at.isoformat()
            self._prune(state, checked_at)
            await self._save(state)

    async def get_provider(self, provider: str) -> dict[str, Any]:
        async with self._lock:
            state = await self._load()
            value = state["providers"].get(provider, {})
            if not isinstance(value, dict):
                raise StorageReadError("notification provider state is invalid")
            return dict(value)

    async def update_provider(self, provider: str, value: dict[str, Any]) -> None:
        async with self._lock:
            state = await self._load()
            state["providers"][provider] = dict(value)
            await self._save(state)

    async def _load(self) -> dict[str, Any]:
        if self._state is not None:
            return self._state
        raw = await self._store.get_json(NOTIFICATION_STATE_KEY)
        if raw is None:
            self._state = {"version": 1, "events": {}, "providers": {}}
            return self._state
        if not isinstance(raw, dict):
            raise StorageReadError("notification state root is invalid")
        events = raw.get("events", {})
        providers = raw.get("providers", {})
        if not isinstance(events, dict) or not isinstance(providers, dict):
            raise StorageReadError("notification state sections are invalid")
        self._state = {
            "version": 1,
            "events": events,
            "providers": providers,
        }
        return self._state

    async def _save(self, state: dict[str, Any]) -> None:
        await self._store.put_json(NOTIFICATION_STATE_KEY, state)

    @staticmethod
    def _prune(state: dict[str, Any], now: datetime) -> None:
        cutoff = (now.date() - timedelta(days=120)).isoformat()
        events = state["events"]
        for key in list(events):
            if key.split(":", 1)[0] < cutoff:
                del events[key]


KVNotificationStateStore = JsonNotificationStateStore
