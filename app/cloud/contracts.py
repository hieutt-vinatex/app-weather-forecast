"""Versioned JSON contracts shared by cloud jobs and edge readers."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Protocol

from pydantic import Field

from app.schemas.gdb import CamelModel


MANIFEST_KEY = "manifest:v1"
NOTIFICATION_STATE_KEY = "notification-state:v1"
DATA_JOB_STATUS_KEY = "job-status:v1:data"
TELEGRAM_JOB_STATUS_KEY = "job-status:v1:telegram"


class JsonStore(Protocol):
    async def get_json(self, key: str) -> Any | None: ...

    async def put_json(
        self,
        key: str,
        value: Any,
        *,
        expiration_ttl: int | None = None,
    ) -> None: ...

    async def delete(self, key: str) -> None: ...

    async def list_keys(self, prefix: str = "") -> list[str]: ...


class StoredDayOutcome(CamelModel):
    day: date
    source_url: str
    gdb: str | None = None
    prizes: dict[str, list[str]] = Field(default_factory=dict)
    complete: bool = False
    ok: bool = False
    reason: str | None = None

    @classmethod
    def from_domain(cls, outcome: Any) -> StoredDayOutcome:
        return cls(
            day=outcome.day,
            source_url=outcome.source_url,
            gdb=outcome.gdb,
            prizes={key: list(values) for key, values in outcome.prizes.items()},
            complete=outcome.complete,
            ok=outcome.ok,
            reason=outcome.reason,
        )

    def to_domain(self) -> Any:
        from app.services.gdb_service import DayOutcome

        return DayOutcome(
            day=self.day,
            source_url=self.source_url,
            gdb=self.gdb,
            prizes={key: tuple(values) for key, values in self.prizes.items()},
            complete=self.complete,
            ok=self.ok,
            reason=self.reason,
        )


class JobRecord(CamelModel):
    kind: str
    mode: str
    status: str
    started_at: datetime
    finished_at: datetime | None = None
    version: str | None = None
    record_count: int = 0
    reason: str | None = None


class OperationRecord(CamelModel):
    request_id: str
    kind: str
    status: str
    created_at: datetime
    updated_at: datetime
    message: str | None = None


class PublicationManifest(CamelModel):
    schema_version: int = 1
    version: str
    generated_at: datetime
    history_key: str
    snapshot_keys: dict[int, str]
    source_reference_date: date | None
    complete: bool
    last_job: JobRecord


def history_key(version: str) -> str:
    return f"history:v1:{version}"


def snapshot_key(version: str, days: int) -> str:
    return f"snapshot:v1:{version}:{days}"


def operation_key(request_id: str) -> str:
    return f"operation:v1:{request_id}"
