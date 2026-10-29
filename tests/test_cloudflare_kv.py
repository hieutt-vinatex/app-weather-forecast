from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

import pytest

from app.cloud.cloudflare_kv import (
    CloudflareKVAuthError,
    CloudflareKVDecodeError,
    CloudflareKVStore,
    CloudflareKVTransientError,
)
from app.config import Settings


class FakeResponse:
    def __init__(
        self,
        status: int,
        payload: Any = None,
        *,
        enter_error: Exception | None = None,
    ) -> None:
        self.status = status
        self._payload = payload
        self._enter_error = enter_error

    async def __aenter__(self):
        if self._enter_error is not None:
            raise self._enter_error
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def json(self, *, content_type=None):
        del content_type
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


@dataclass
class RecordedRequest:
    method: str
    url: str
    headers: dict[str, str]
    params: dict[str, str] | None
    data: bytes | None


class FakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = list(responses)
        self.requests: list[RecordedRequest] = []

    def request(self, method, url, *, headers, params=None, data=None):
        self.requests.append(RecordedRequest(method, url, headers, params, data))
        return self.responses.pop(0)


def make_store(session: FakeSession, sleeps: list[float] | None = None):
    async def fake_sleep(delay: float) -> None:
        if sleeps is not None:
            sleeps.append(delay)

    return CloudflareKVStore(
        "account",
        "namespace",
        "secret",
        session,  # type: ignore[arg-type]
        max_retries=1,
        sleep=fake_sleep,
    )


async def test_get_json_returns_none_for_404():
    store = make_store(FakeSession([FakeResponse(404)]))

    assert await store.get_json("missing") is None


async def test_put_json_uses_encoded_namespace_values_endpoint():
    session = FakeSession([FakeResponse(200, {"success": True})])
    store = make_store(session)

    await store.put_json("manifest:v1", {"version": "v1"}, expiration_ttl=60)

    request = session.requests[0]
    assert request.method == "PUT"
    assert request.url.endswith("/values/manifest%3Av1")
    assert request.headers["Authorization"] == "Bearer secret"
    assert request.params == {"expiration_ttl": "60"}
    assert json.loads(request.data or b"") == {"version": "v1"}


async def test_get_json_rejects_malformed_json_with_safe_error():
    store = make_store(FakeSession([FakeResponse(200, ValueError("secret body"))]))

    with pytest.raises(CloudflareKVDecodeError) as exc_info:
        await store.get_json("manifest:v1")

    assert "secret body" not in str(exc_info.value)


@pytest.mark.parametrize("status", [401, 403])
async def test_auth_failures_are_not_retried(status):
    session = FakeSession([FakeResponse(status), FakeResponse(200, {})])
    store = make_store(session)

    with pytest.raises(CloudflareKVAuthError):
        await store.get_json("manifest:v1")

    assert len(session.requests) == 1


@pytest.mark.parametrize("transient_status", [429, 500])
async def test_transient_status_is_retried_then_succeeds(transient_status):
    sleeps: list[float] = []
    session = FakeSession(
        [FakeResponse(transient_status), FakeResponse(200, {"version": "current"})]
    )
    store = make_store(session, sleeps)

    assert await store.get_json("manifest:v1") == {"version": "current"}
    assert len(session.requests) == 2
    assert len(sleeps) == 1


async def test_timeout_exhaustion_raises_safe_transient_error():
    session = FakeSession(
        [
            FakeResponse(0, enter_error=asyncio.TimeoutError("token=secret")),
            FakeResponse(0, enter_error=asyncio.TimeoutError("token=secret")),
        ]
    )
    store = make_store(session)

    with pytest.raises(CloudflareKVTransientError) as exc_info:
        await store.get_json("manifest:v1")

    assert len(session.requests) == 2
    assert "secret" not in str(exc_info.value)


async def test_list_keys_reads_all_cursor_pages():
    session = FakeSession(
        [
            FakeResponse(
                200,
                {
                    "success": True,
                    "result": [{"name": "snapshot:v1:a:30"}],
                    "result_info": {"cursor": "next"},
                },
            ),
            FakeResponse(
                200,
                {
                    "success": True,
                    "result": [{"name": "snapshot:v1:b:30"}],
                    "result_info": {"cursor": ""},
                },
            ),
        ]
    )
    store = make_store(session)

    assert await store.list_keys("snapshot:v1:") == [
        "snapshot:v1:a:30",
        "snapshot:v1:b:30",
    ]
    assert session.requests[1].params == {
        "prefix": "snapshot:v1:",
        "cursor": "next",
    }


def test_cloud_settings_are_optional_until_cloud_job_is_required():
    settings = Settings(_env_file=None)
    assert settings.app_port == 8000

    with pytest.raises(ValueError) as exc_info:
        settings.require_cloud_job_config()

    message = str(exc_info.value)
    assert "CLOUDFLARE_ACCOUNT_ID" in message
    assert "CLOUDFLARE_KV_NAMESPACE_ID" in message
    assert "CLOUDFLARE_API_TOKEN" in message


def test_cloud_settings_return_unwrapped_secret_only_to_job_config():
    settings = Settings(
        _env_file=None,
        cloudflare_account_id="account",
        cloudflare_kv_namespace_id="namespace",
        cloudflare_api_token="super-secret",
    )

    config = settings.require_cloud_job_config()

    assert config.account_id == "account"
    assert config.namespace_id == "namespace"
    assert config.api_token == "super-secret"
    assert "super-secret" not in repr(settings)
