"""HTTP adapters for Telegram, Zalo OA and Facebook/Meta."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
from dataclasses import dataclass
from typing import Any

import aiohttp

from app.config import Settings
from app.notifications.state_store import NotificationStateProtocol


@dataclass(frozen=True)
class NotificationTarget:
    key: str
    channel: str
    kind: str
    recipient: str
    display: str


@dataclass(frozen=True)
class DeliveryResult:
    target: NotificationTarget
    success: bool
    provider_id: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class _Attempt:
    success: bool
    provider_id: str | None = None
    error: str | None = None
    retryable: bool = False


class NotificationDispatcher:
    def __init__(
        self,
        settings: Settings,
        state_store: NotificationStateProtocol,
        *,
        sleep=asyncio.sleep,
        allowed_channels: frozenset[str] | None = None,
        target_key_secret: str | None = None,
    ) -> None:
        self._settings = settings
        self._state_store = state_store
        self._sleep = sleep
        self._allowed_channels = allowed_channels
        self._target_key_secret = target_key_secret
        self._session: aiohttp.ClientSession | None = None
        self._zalo_lock = asyncio.Lock()
        self._zalo_loaded = False
        self._zalo_access_token: str | None = None
        self._zalo_refresh_token: str | None = None

    async def start(self) -> None:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(
                total=self._settings.notification_request_timeout_seconds
            )
            self._session = aiohttp.ClientSession(timeout=timeout)

    async def close(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()
        self._session = None

    def targets(self) -> list[NotificationTarget]:
        targets: list[NotificationTarget] = []

        if self._channel_allowed("telegram") and self._secret(
            self._settings.telegram_bot_token
        ):
            targets.extend(
                self._target("telegram", "chat", chat_id)
                for chat_id in self._settings.telegram_chat_id_list
            )

        has_zalo_auth = bool(
            self._secret(self._settings.zalo_access_token)
            or (
                self._settings.zalo_app_id
                and self._secret(self._settings.zalo_app_secret)
                and self._secret(self._settings.zalo_refresh_token)
            )
        )
        if self._channel_allowed("zalo") and has_zalo_auth:
            targets.extend(
                self._target("zalo", "oa_user", user_id)
                for user_id in self._settings.zalo_recipient_id_list
            )

        facebook_page_id = self._settings.facebook_page_id.strip()
        if (
            self._channel_allowed("facebook")
            and
            self._secret(self._settings.facebook_page_access_token)
            and facebook_page_id
        ):
            targets.extend(
                self._target("facebook", "messenger", recipient_id)
                for recipient_id in self._settings.facebook_messenger_recipient_id_list
            )
            if (
                self._settings.facebook_publish_to_page
                and facebook_page_id
            ):
                targets.append(
                    self._target(
                        "facebook",
                        "page_feed",
                        facebook_page_id,
                    )
                )
        return targets

    async def send(self, target: NotificationTarget, message: str) -> DeliveryResult:
        if self._session is None or self._session.closed:
            await self.start()

        max_attempts = self._settings.notification_max_retries + 1
        attempt_result = _Attempt(success=False, error="not_attempted")
        for attempt_number in range(max_attempts):
            try:
                attempt_result = await self._send_once(target, message)
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                # Avoid exception strings: Telegram embeds its bot token in the
                # request path and some transport errors include the full URL.
                attempt_result = _Attempt(
                    success=False,
                    error=f"transport:{type(exc).__name__}",
                    retryable=True,
                )
            if attempt_result.success or not attempt_result.retryable:
                break
            if attempt_number + 1 < max_attempts:
                await self._sleep(min(2**attempt_number, 8))

        return DeliveryResult(
            target=target,
            success=attempt_result.success,
            provider_id=attempt_result.provider_id,
            error=attempt_result.error,
        )

    async def _send_once(self, target: NotificationTarget, message: str) -> _Attempt:
        if target.channel == "telegram":
            return await self._send_telegram(target, message)
        if target.channel == "zalo":
            return await self._send_zalo(target, message)
        if target.channel == "facebook":
            return await self._send_facebook(target, message)
        return _Attempt(success=False, error="unsupported_channel")

    async def _send_telegram(
        self, target: NotificationTarget, message: str
    ) -> _Attempt:
        token = self._secret(self._settings.telegram_bot_token)
        if not token:
            return _Attempt(success=False, error="telegram_not_configured")
        response_status, payload = await self._post_json(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json_body={
                "chat_id": target.recipient,
                "text": message,
                "disable_web_page_preview": True,
            },
        )
        if response_status < 400 and payload.get("ok") is True:
            provider_id = str(payload.get("result", {}).get("message_id", "")) or None
            return _Attempt(success=True, provider_id=provider_id)
        return _Attempt(
            success=False,
            error=self._provider_error("telegram", response_status, payload),
            retryable=response_status == 429 or response_status >= 500,
        )

    async def _send_zalo(self, target: NotificationTarget, message: str) -> _Attempt:
        access_token = await self._get_zalo_access_token()
        if not access_token:
            return _Attempt(success=False, error="zalo_not_configured")

        result = await self._call_zalo(target, message, access_token)
        if self._zalo_token_expired(result):
            refreshed = await self._refresh_zalo_token(access_token)
            if refreshed:
                result = await self._call_zalo(target, message, refreshed)
        return result

    async def _call_zalo(
        self,
        target: NotificationTarget,
        message: str,
        access_token: str,
    ) -> _Attempt:
        response_status, payload = await self._post_json(
            "https://openapi.zalo.me/v3.0/oa/message/cs",
            json_body={
                "recipient": {"user_id": target.recipient},
                "message": {"text": message},
            },
            headers={"access_token": access_token},
        )
        error_code = payload.get("error")
        if response_status < 400 and error_code in (0, "0"):
            data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
            provider_id = str(data.get("message_id", "")) or None
            return _Attempt(success=True, provider_id=provider_id)
        return _Attempt(
            success=False,
            error=self._provider_error("zalo", response_status, payload),
            retryable=response_status == 429 or response_status >= 500,
        )

    async def _get_zalo_access_token(self) -> str | None:
        async with self._zalo_lock:
            if not self._zalo_loaded:
                stored = await self._state_store.get_provider("zalo")
                same_app = stored.get("appId") == self._settings.zalo_app_id
                self._zalo_access_token = (
                    stored.get("accessToken") if same_app else None
                ) or self._secret(self._settings.zalo_access_token)
                self._zalo_refresh_token = (
                    stored.get("refreshToken") if same_app else None
                ) or self._secret(self._settings.zalo_refresh_token)
                self._zalo_loaded = True
            access_token = self._zalo_access_token
        if access_token:
            return access_token
        # A production setup may intentionally provide only the rotating
        # refresh token plus app credentials.
        return await self._refresh_zalo_token("")

    async def _refresh_zalo_token(self, stale_access_token: str) -> str | None:
        async with self._zalo_lock:
            # Another concurrent Zalo destination may already have refreshed
            # the rotating token while this coroutine waited for the lock.
            if (
                self._zalo_access_token
                and self._zalo_access_token != stale_access_token
            ):
                return self._zalo_access_token
            app_id = self._settings.zalo_app_id.strip()
            app_secret = self._secret(self._settings.zalo_app_secret)
            refresh_token = self._zalo_refresh_token or self._secret(
                self._settings.zalo_refresh_token
            )
            if not app_id or not app_secret or not refresh_token:
                return None

            response_status, payload = await self._post_form(
                "https://oauth.zaloapp.com/v4/oa/access_token",
                data={
                    "app_id": app_id,
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                },
                headers={"secret_key": app_secret},
            )
            access_token = payload.get("access_token")
            if response_status >= 400 or not isinstance(access_token, str):
                return None
            new_refresh = payload.get("refresh_token")
            self._zalo_access_token = access_token
            if isinstance(new_refresh, str) and new_refresh:
                self._zalo_refresh_token = new_refresh
            await self._state_store.update_provider(
                "zalo",
                {
                    "appId": app_id,
                    "accessToken": self._zalo_access_token,
                    "refreshToken": self._zalo_refresh_token,
                },
            )
            return self._zalo_access_token

    @staticmethod
    def _zalo_token_expired(result: _Attempt) -> bool:
        if result.success or result.error is None:
            return False
        return any(
            marker in result.error
            for marker in ("http_401", "http_403", "code_-124", "code_-201", "code_-216")
        )

    async def _send_facebook(
        self, target: NotificationTarget, message: str
    ) -> _Attempt:
        token = self._secret(self._settings.facebook_page_access_token)
        if not token:
            return _Attempt(success=False, error="facebook_not_configured")

        version = self._settings.facebook_graph_api_version.strip().lstrip("/")
        headers = {"Authorization": f"Bearer {token}"}
        if target.kind == "page_feed":
            url = f"https://graph.facebook.com/{version}/{target.recipient}/feed"
            body: dict[str, Any] = {"message": message}
        else:
            page_id = self._settings.facebook_page_id.strip()
            url = f"https://graph.facebook.com/{version}/{page_id}/messages"
            body = {
                "recipient": {"id": target.recipient},
                "messaging_type": "UPDATE",
                "message": {"text": message},
            }

        response_status, payload = await self._post_json(
            url, json_body=body, headers=headers
        )
        if response_status < 400 and "error" not in payload:
            provider_id = str(
                payload.get("message_id") or payload.get("post_id") or payload.get("id") or ""
            ) or None
            return _Attempt(success=True, provider_id=provider_id)
        return _Attempt(
            success=False,
            error=self._provider_error("facebook", response_status, payload),
            retryable=response_status == 429 or response_status >= 500,
        )

    async def _post_json(
        self,
        url: str,
        *,
        json_body: dict[str, Any],
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, Any]]:
        assert self._session is not None
        async with self._session.post(url, json=json_body, headers=headers) as response:
            return response.status, await self._json_payload(response)

    async def _post_form(
        self,
        url: str,
        *,
        data: dict[str, str],
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, Any]]:
        assert self._session is not None
        async with self._session.post(url, data=data, headers=headers) as response:
            return response.status, await self._json_payload(response)

    @staticmethod
    async def _json_payload(response: aiohttp.ClientResponse) -> dict[str, Any]:
        try:
            payload = await response.json(content_type=None)
        except (ValueError, aiohttp.ContentTypeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _provider_error(
        provider: str, status: int, payload: dict[str, Any]
    ) -> str:
        error = payload.get("error")
        if isinstance(error, dict):
            code = error.get("code")
            message = error.get("message")
        else:
            code = error
            message = payload.get("description") or payload.get("message")
        safe_message = str(message or "request_failed").replace("\n", " ")[:160]
        return f"{provider}:http_{status}:code_{code}:{safe_message}"

    @staticmethod
    def _secret(value) -> str | None:
        if value is None:
            return None
        raw = value.get_secret_value().strip()
        return raw or None

    def _channel_allowed(self, channel: str) -> bool:
        return self._allowed_channels is None or channel in self._allowed_channels

    def _target(self, channel: str, kind: str, recipient: str) -> NotificationTarget:
        identity = f"{channel}:{kind}:{recipient}".encode("utf-8")
        digest = (
            hmac.new(
                self._target_key_secret.encode("utf-8"),
                identity,
                hashlib.sha256,
            ).hexdigest()
            if self._target_key_secret is not None
            else hashlib.sha256(identity).hexdigest()[:16]
        )
        suffix = recipient[-4:] if len(recipient) > 4 else recipient
        return NotificationTarget(
            key=f"{channel}:{kind}:{digest}",
            channel=channel,
            kind=kind,
            recipient=recipient,
            display=f"{kind}:…{suffix}",
        )
