"""Small atomic JSON store for notification idempotency and Zalo tokens."""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


class NotificationStateStore:
    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self._lock = asyncio.Lock()
        self._state: dict[str, Any] | None = None

    async def sent_targets(self, event_key: str) -> set[str]:
        async with self._lock:
            state = self._load()
            event = state.get("events", {}).get(event_key, {})
            return set(event.get("targets", {}))

    async def mark_sent(self, event_key: str, target_key: str, sent_at: datetime) -> None:
        async with self._lock:
            state = self._load()
            event = state.setdefault("events", {}).setdefault(event_key, {})
            event.setdefault("targets", {})[target_key] = sent_at.isoformat()
            event["updatedAt"] = sent_at.isoformat()
            self._prune(state, sent_at)
            self._save(state)

    async def is_no_match(self, event_key: str) -> bool:
        async with self._lock:
            state = self._load()
            return bool(state.get("events", {}).get(event_key, {}).get("noMatch"))

    async def mark_no_match(self, event_key: str, checked_at: datetime) -> None:
        async with self._lock:
            state = self._load()
            event = state.setdefault("events", {}).setdefault(event_key, {})
            event["noMatch"] = True
            event["updatedAt"] = checked_at.isoformat()
            self._prune(state, checked_at)
            self._save(state)

    async def get_provider(self, provider: str) -> dict[str, Any]:
        async with self._lock:
            state = self._load()
            return dict(state.get("providers", {}).get(provider, {}))

    async def set_provider(self, provider: str, value: dict[str, Any]) -> None:
        async with self._lock:
            state = self._load()
            state.setdefault("providers", {})[provider] = value
            self._save(state)

    def _load(self) -> dict[str, Any]:
        if self._state is not None:
            return self._state
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("state root must be an object")
            self._state = raw
        except FileNotFoundError:
            self._state = {"version": 1, "events": {}, "providers": {}}
        except (OSError, ValueError, json.JSONDecodeError):
            # Keep the unreadable file for inspection and start safely with an
            # empty in-memory state. The next successful write replaces it.
            self._state = {"version": 1, "events": {}, "providers": {}}
        return self._state

    def _save(self, state: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        payload = json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True)
        with temp_path.open("w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.chmod(temp_path, 0o600)
        except OSError:
            pass
        os.replace(temp_path, self.path)

    @staticmethod
    def _prune(state: dict[str, Any], now: datetime) -> None:
        cutoff = (now.date() - timedelta(days=120)).isoformat()
        events = state.setdefault("events", {})
        for key in list(events):
            reference_date = key.split(":", 1)[0]
            if reference_date < cutoff:
                del events[key]
