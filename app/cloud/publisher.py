"""Manifest-last publication of immutable snapshot versions."""

from __future__ import annotations

import json
import logging
from datetime import timezone
from typing import Any, Sequence

from pydantic import ValidationError

from app.cloud.contracts import (
    MANIFEST_KEY,
    JobRecord,
    JsonStore,
    PublicationManifest,
    StoredDayOutcome,
    history_key,
    snapshot_key,
)
from app.services.gdb_service import DayOutcome
from app.services.snapshot_builder import SnapshotBuildContext, assemble_snapshot

logger = logging.getLogger("app.cloud.publisher")


class PublicationError(RuntimeError):
    """Base error safe to expose as a cloud job category."""


class StorageWriteError(PublicationError):
    pass


class StorageReadError(PublicationError):
    pass


class PayloadTooLargeError(PublicationError):
    pass


class SnapshotPublisher:
    def __init__(
        self,
        store: JsonStore,
        *,
        max_value_bytes: int = 20 * 1024 * 1024,
        retained_versions: int = 3,
    ):
        if max_value_bytes <= 0:
            raise ValueError("max_value_bytes must be positive")
        if retained_versions <= 0:
            raise ValueError("retained_versions must be positive")
        self._store = store
        self._max_value_bytes = max_value_bytes
        self._retained_versions = retained_versions

    async def publish(
        self,
        outcomes: Sequence[DayOutcome],
        context: SnapshotBuildContext,
        job: JobRecord,
    ) -> PublicationManifest:
        ordered = sorted(outcomes, key=lambda item: item.day)
        version = context.fetched_at.astimezone(timezone.utc).strftime(
            "%Y%m%dT%H%M%S%fZ"
        )
        history_storage_key = history_key(version)
        snapshot_keys = {days: snapshot_key(version, days) for days in (30, 60, 90)}
        history_payload = [
            StoredDayOutcome.from_domain(item).model_dump(mode="json", by_alias=True)
            for item in ordered
        ]
        payloads: dict[str, Any] = {history_storage_key: history_payload}
        for days, key in snapshot_keys.items():
            snapshot = assemble_snapshot(days, ordered[-days:], context)
            payloads[key] = snapshot.model_dump(mode="json", by_alias=True)

        manifest = PublicationManifest(
            version=version,
            generated_at=context.fetched_at,
            history_key=history_storage_key,
            snapshot_keys=snapshot_keys,
            source_reference_date=max((item.day for item in ordered), default=None),
            complete=bool(ordered) and all(item.ok and item.complete for item in ordered),
            last_job=job.model_copy(update={"version": version}),
        )
        manifest_payload = manifest.model_dump(mode="json", by_alias=True)
        self._validate_payload_sizes({**payloads, MANIFEST_KEY: manifest_payload})

        try:
            for key, payload in payloads.items():
                await self._store.put_json(key, payload)
                if await self._store.get_json(key) != payload:
                    raise StorageWriteError("stored payload verification failed")
            await self._store.put_json(MANIFEST_KEY, manifest_payload)
        except StorageWriteError:
            raise
        except Exception as exc:
            raise StorageWriteError("snapshot publication failed") from exc
        try:
            await self._prune_old_versions()
        except Exception:
            logger.warning("snapshot version pruning failed")
        return manifest

    async def load_active_history(self) -> list[DayOutcome]:
        try:
            raw_manifest = await self._store.get_json(MANIFEST_KEY)
            if raw_manifest is None:
                return []
            manifest = PublicationManifest.model_validate(raw_manifest)
            raw_history = await self._store.get_json(manifest.history_key)
            if not isinstance(raw_history, list):
                raise StorageReadError("active history is missing or invalid")
            return [
                StoredDayOutcome.model_validate(item).to_domain()
                for item in raw_history
            ]
        except StorageReadError:
            raise
        except (ValidationError, TypeError, ValueError) as exc:
            raise StorageReadError("active publication is invalid") from exc
        except Exception as exc:
            raise StorageReadError("active publication could not be read") from exc

    def _validate_payload_sizes(self, payloads: dict[str, Any]) -> None:
        for key, payload in payloads.items():
            encoded = json.dumps(
                payload,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
            if len(encoded) > self._max_value_bytes:
                raise PayloadTooLargeError(f"payload exceeds safe limit: {key}")

    async def _prune_old_versions(self) -> None:
        prefix = "history:v1:"
        history_keys = await self._store.list_keys(prefix)
        versions = sorted(
            (key.removeprefix(prefix) for key in history_keys), reverse=True
        )
        for version in versions[self._retained_versions :]:
            await self._store.delete(history_key(version))
            for days in (30, 60, 90):
                await self._store.delete(snapshot_key(version, days))
