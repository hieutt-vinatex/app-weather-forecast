"""Application configuration loaded and validated from the environment.

All tunables live here so the rest of the code never reads ``os.environ``
directly. Settings are validated once at import/startup time; invalid values
fail fast instead of surfacing as obscure runtime errors later.
"""

from __future__ import annotations

from datetime import time as dt_time
from functools import lru_cache
from typing import List
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _parse_hhmm(value: str) -> dt_time:
    """Parse a ``HH:MM`` string into a ``datetime.time``."""
    parts = value.strip().split(":")
    if len(parts) != 2:
        raise ValueError(f"Expected HH:MM, got {value!r}")
    hour, minute = int(parts[0]), int(parts[1])
    return dt_time(hour=hour, minute=minute)


class Settings(BaseSettings):
    """Strongly-typed application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "INFO"

    cors_origins: str = "http://localhost:5173"

    source_base_url: str = "https://xsmn.mobi"
    source_timeout_seconds: float = 8.0
    source_connect_timeout_seconds: float = 3.0
    source_max_retries: int = 3
    source_max_concurrency: int = 10

    history_cache_ttl_seconds: float = 300.0

    realtime_enabled: bool = True
    realtime_timezone: str = "Asia/Ho_Chi_Minh"
    realtime_active_start: str = "17:45"
    realtime_active_end: str = "19:00"
    realtime_active_poll_seconds: float = 1.0
    realtime_idle_poll_seconds: float = 30.0
    realtime_heartbeat_seconds: float = 15.0
    realtime_min_poll_seconds: float = 1.0

    manual_refresh_cooldown_seconds: float = 5.0

    # Server-side absence notifications. Delivery credentials remain on the
    # backend and are never exposed through the API/frontend.
    notifications_enabled: bool = False
    notification_dry_run: bool = True
    notification_min_days: int = 19
    notification_max_days: int = 25
    notification_send_time: str = "09:00"
    notification_check_interval_seconds: float = 60.0
    notification_retry_interval_seconds: float = 300.0
    notification_request_timeout_seconds: float = 10.0
    notification_max_retries: int = 2
    notification_state_path: str = ".data/notification-state.json"
    notification_admin_token: SecretStr | None = None

    telegram_bot_token: SecretStr | None = None
    telegram_chat_ids: str = ""

    zalo_access_token: SecretStr | None = None
    zalo_refresh_token: SecretStr | None = None
    zalo_app_id: str = ""
    zalo_app_secret: SecretStr | None = None
    zalo_recipient_ids: str = ""

    facebook_graph_api_version: str = "v26.0"
    facebook_page_access_token: SecretStr | None = None
    facebook_messenger_recipient_ids: str = ""
    facebook_page_id: str = ""
    facebook_publish_to_page: bool = False

    # ------------------------------------------------------------------ #
    # Validators
    # ------------------------------------------------------------------ #
    @field_validator("realtime_timezone")
    @classmethod
    def _validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"Invalid timezone {value!r}: {exc}") from exc
        return value

    @field_validator(
        "realtime_active_start",
        "realtime_active_end",
        "notification_send_time",
    )
    @classmethod
    def _validate_hhmm(cls, value: str) -> str:
        _parse_hhmm(value)  # raises on bad format
        return value

    @model_validator(mode="after")
    def _validate_ranges(self) -> "Settings":
        if self.realtime_active_poll_seconds < self.realtime_min_poll_seconds:
            raise ValueError(
                "REALTIME_ACTIVE_POLL_SECONDS "
                f"({self.realtime_active_poll_seconds}) must be >= "
                f"REALTIME_MIN_POLL_SECONDS ({self.realtime_min_poll_seconds})"
            )
        if self.realtime_idle_poll_seconds < self.realtime_min_poll_seconds:
            raise ValueError(
                "REALTIME_IDLE_POLL_SECONDS must be >= REALTIME_MIN_POLL_SECONDS"
            )
        start = _parse_hhmm(self.realtime_active_start)
        end = _parse_hhmm(self.realtime_active_end)
        if start >= end:
            raise ValueError(
                "REALTIME_ACTIVE_START must be strictly before "
                "REALTIME_ACTIVE_END (overnight windows are not supported)"
            )
        if self.source_max_retries < 0:
            raise ValueError("SOURCE_MAX_RETRIES must be >= 0")
        if self.source_max_concurrency < 1:
            raise ValueError("SOURCE_MAX_CONCURRENCY must be >= 1")
        if self.notification_min_days < 1:
            raise ValueError("NOTIFICATION_MIN_DAYS must be >= 1")
        if self.notification_max_days < self.notification_min_days:
            raise ValueError(
                "NOTIFICATION_MAX_DAYS must be >= NOTIFICATION_MIN_DAYS"
            )
        if self.notification_max_days > 88:
            raise ValueError("NOTIFICATION_MAX_DAYS must be <= 88")
        if self.notification_check_interval_seconds < 5:
            raise ValueError("NOTIFICATION_CHECK_INTERVAL_SECONDS must be >= 5")
        if self.notification_retry_interval_seconds < 5:
            raise ValueError("NOTIFICATION_RETRY_INTERVAL_SECONDS must be >= 5")
        if self.notification_request_timeout_seconds <= 0:
            raise ValueError("NOTIFICATION_REQUEST_TIMEOUT_SECONDS must be > 0")
        if self.notification_max_retries < 0:
            raise ValueError("NOTIFICATION_MAX_RETRIES must be >= 0")
        return self

    # ------------------------------------------------------------------ #
    # Derived helpers
    # ------------------------------------------------------------------ #
    @property
    def cors_origin_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def tzinfo(self) -> ZoneInfo:
        return ZoneInfo(self.realtime_timezone)

    @property
    def active_start_time(self) -> dt_time:
        return _parse_hhmm(self.realtime_active_start)

    @property
    def active_end_time(self) -> dt_time:
        return _parse_hhmm(self.realtime_active_end)

    @property
    def notification_send_time_value(self) -> dt_time:
        return _parse_hhmm(self.notification_send_time)

    @staticmethod
    def _csv(value: str) -> List[str]:
        return list(dict.fromkeys(part.strip() for part in value.split(",") if part.strip()))

    @property
    def telegram_chat_id_list(self) -> List[str]:
        return self._csv(self.telegram_chat_ids)

    @property
    def zalo_recipient_id_list(self) -> List[str]:
        return self._csv(self.zalo_recipient_ids)

    @property
    def facebook_messenger_recipient_id_list(self) -> List[str]:
        return self._csv(self.facebook_messenger_recipient_ids)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide singleton settings instance."""
    return Settings()
