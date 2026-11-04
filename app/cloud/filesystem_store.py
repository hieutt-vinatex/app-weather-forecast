"""Filesystem implementation of the cloud JSON store contract."""

from __future__ import annotations

import errno
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any
from uuid import UUID

from app.cloud.contracts import (
    DAILY_DATA_UPDATE_KEY,
    DATA_JOB_STATUS_KEY,
    MANIFEST_KEY,
    NOTIFICATION_STATE_KEY,
    TELEGRAM_JOB_STATUS_KEY,
)


_VERSION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
_RANGES = {30, 60, 90}
_FIXED_PATHS = {
    MANIFEST_KEY: Path("site/data/manifest.json"),
    DATA_JOB_STATUS_KEY: Path("site/data/status.json"),
    TELEGRAM_JOB_STATUS_KEY: Path("state/telegram-job-status.json"),
    NOTIFICATION_STATE_KEY: Path("state/telegram-ledger.json"),
    DAILY_DATA_UPDATE_KEY: Path("state/daily-data-update.json"),
}
_FIXED_KEYS_BY_PATH = {path: key for key, path in _FIXED_PATHS.items()}


class FilesystemJsonStore:
    """Store logical publication keys under a checked-out ``gh-pages`` root."""

    def __init__(
        self,
        root: Path,
        *,
        max_value_bytes: int = 20 * 1024 * 1024,
    ) -> None:
        if max_value_bytes <= 0:
            raise ValueError("max_value_bytes must be positive")
        self._root = Path(root)
        self._max_value_bytes = max_value_bytes

    def path_for_key(self, key: str) -> Path:
        return self._root / self._relative_path_for_key(key)

    async def get_json(self, key: str) -> Any | None:
        path = self.path_for_key(key)
        try:
            raw = path.read_bytes()
        except FileNotFoundError:
            return None
        if len(raw) > self._max_value_bytes:
            raise ValueError("stored value exceeds safe byte limit")
        return json.loads(raw)

    async def put_json(
        self,
        key: str,
        value: Any,
        *,
        expiration_ttl: int | None = None,
    ) -> None:
        del expiration_ttl
        path = self.path_for_key(key)
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        if len(encoded) > self._max_value_bytes:
            raise ValueError("value exceeds safe byte limit")

        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                temporary.write(encoded)
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_path, path)
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink()

    async def delete(self, key: str) -> None:
        path = self.path_for_key(key)
        try:
            path.unlink()
        except FileNotFoundError:
            pass

        versions_root = self._root / "site/data/versions"
        if path.parent.parent != versions_root:
            return
        try:
            path.parent.rmdir()
        except FileNotFoundError:
            return
        except OSError as exc:
            if exc.errno not in {errno.EEXIST, errno.ENOTEMPTY}:
                raise

    async def list_keys(self, prefix: str = "") -> list[str]:
        if not self._root.exists():
            return []
        keys: list[str] = []
        for path in self._root.rglob("*.json"):
            if not path.is_file():
                continue
            key = self._key_for_relative_path(path.relative_to(self._root))
            if key is not None and key.startswith(prefix):
                keys.append(key)
        return sorted(keys)

    @staticmethod
    def _relative_path_for_key(key: str) -> Path:
        fixed = _FIXED_PATHS.get(key)
        if fixed is not None:
            return fixed

        parts = key.split(":")
        if len(parts) == 3 and parts[:2] == ["history", "v1"]:
            version = FilesystemJsonStore._safe_version(parts[2], key)
            return Path("site/data/versions") / version / "history.json"
        if len(parts) == 4 and parts[:2] == ["snapshot", "v1"]:
            version = FilesystemJsonStore._safe_version(parts[2], key)
            try:
                days = int(parts[3])
            except ValueError:
                days = 0
            if days in _RANGES:
                return (
                    Path("site/data/versions")
                    / version
                    / f"snapshot-{days}.json"
                )
        if len(parts) == 3 and parts[:2] == ["operation", "v1"]:
            try:
                request_id = str(UUID(parts[2]))
            except ValueError:
                pass
            else:
                return Path("state/operations") / f"{request_id}.json"
        raise ValueError(f"unsupported storage key: {key}")

    @staticmethod
    def _safe_version(version: str, key: str) -> str:
        if not _VERSION_PATTERN.fullmatch(version):
            raise ValueError(f"unsupported storage key: {key}")
        return version

    @staticmethod
    def _key_for_relative_path(path: Path) -> str | None:
        fixed = _FIXED_KEYS_BY_PATH.get(path)
        if fixed is not None:
            return fixed

        parts = path.parts
        if len(parts) == 5 and parts[:3] == ("site", "data", "versions"):
            version = parts[3]
            if not _VERSION_PATTERN.fullmatch(version):
                return None
            filename = parts[4]
            if filename == "history.json":
                return f"history:v1:{version}"
            match = re.fullmatch(r"snapshot-(30|60|90)\.json", filename)
            if match:
                return f"snapshot:v1:{version}:{match.group(1)}"
        if len(parts) == 3 and parts[:2] == ("state", "operations"):
            try:
                request_id = str(UUID(Path(parts[2]).stem))
            except ValueError:
                return None
            return f"operation:v1:{request_id}"
        return None
