"""Versioned JSON contracts shared by cloud jobs and edge readers."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal, Protocol

from pydantic import ConfigDict, Field, field_validator, model_validator

from app.schemas.gdb import CamelModel


MANIFEST_KEY = "manifest:v1"
NOTIFICATION_STATE_KEY = "notification-state:v1"
DATA_JOB_STATUS_KEY = "job-status:v1:data"
TELEGRAM_JOB_STATUS_KEY = "job-status:v1:telegram"
DAILY_DATA_UPDATE_KEY = "daily-data-update:v1"


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


class DailyDataUpdateState(CamelModel):
    model_config = ConfigDict(**CamelModel.model_config, extra="forbid")

    schema_version: int = 1
    business_date: date
    status: Literal["pending", "failed", "succeeded"]
    attempt_count: int = Field(ge=0)
    first_attempt_at: datetime
    last_attempt_at: datetime
    initial_failure_at: datetime | None = None
    last_reason: str | None = None
    published_version: str | None = None
    source_reference_date: date | None = None

    @field_validator("schema_version")
    @classmethod
    def _validate_schema_version(cls, value: int) -> int:
        if value != 1:
            raise ValueError("schema_version must equal 1")
        return value

    @field_validator("first_attempt_at", "last_attempt_at", "initial_failure_at")
    @classmethod
    def _validate_aware_timestamp(cls, value: datetime | None) -> datetime | None:
        if value is not None and (
            value.tzinfo is None or value.utcoffset() is None
        ):
            raise ValueError("daily update timestamps must be timezone-aware")
        return value

    @field_validator("last_reason")
    @classmethod
    def _validate_safe_reason(cls, value: str | None) -> str | None:
        allowed = {
            "invalid_upstream_data",
            "job_timeout",
            "cloud_storage_error",
            "job_failed",
            "publication_mismatch",
            "update_state_missing",
        }
        if value is not None and value not in allowed:
            raise ValueError("last_reason must be a safe reason code")
        return value

    @model_validator(mode="after")
    def _validate_state_invariants(self) -> DailyDataUpdateState:
        if self.last_attempt_at < self.first_attempt_at:
            raise ValueError("last_attempt_at cannot precede first_attempt_at")
        if (
            self.initial_failure_at is not None
            and self.initial_failure_at < self.first_attempt_at
        ):
            raise ValueError("initial_failure_at cannot precede first_attempt_at")
        if self.status == "failed" and (
            self.initial_failure_at is None or self.last_reason is None
        ):
            raise ValueError("failed state requires failure metadata")
        if self.status == "succeeded":
            if not self.published_version or self.source_reference_date is None:
                raise ValueError("succeeded state requires publication metadata")
            if self.source_reference_date != self.business_date:
                raise ValueError("source reference date must match business date")
            if self.last_reason is not None:
                raise ValueError("succeeded state cannot retain a failure reason")
        elif self.published_version is not None or self.source_reference_date is not None:
            raise ValueError("unfinished state cannot contain publication metadata")
        return self


class OperationRecord(CamelModel):
    request_id: str
    kind: str
    status: str
    created_at: datetime
    updated_at: datetime
    message: str | None = None


class PreviousPublication(CamelModel):
    version: str
    generated_at: datetime
    snapshot_keys: dict[int, str]
    source_reference_date: date | None
    complete: bool
    last_job: JobRecord


class PublicationManifest(CamelModel):
    schema_version: int = 1
    version: str
    generated_at: datetime
    history_key: str
    snapshot_keys: dict[int, str]
    source_reference_date: date | None
    complete: bool
    last_job: JobRecord
    previous_publication: PreviousPublication | None = None


def history_key(version: str) -> str:
    return f"history:v1:{version}"


def snapshot_key(version: str, days: int) -> str:
    return f"snapshot:v1:{version}:{days}"


def operation_key(request_id: str) -> str:
    return f"operation:v1:{request_id}"
