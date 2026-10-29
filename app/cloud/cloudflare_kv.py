"""Cloudflare Workers KV REST implementation of the JSON store contract."""

from __future__ import annotations

import asyncio
import json
from typing import Any, Awaitable, Callable
from urllib.parse import quote

import aiohttp


class CloudflareKVError(RuntimeError):
    """Base error whose message never contains credentials or response bodies."""


class CloudflareKVAuthError(CloudflareKVError):
    pass


class CloudflareKVTransientError(CloudflareKVError):
    pass


class CloudflareKVRequestError(CloudflareKVError):
    pass


class CloudflareKVDecodeError(CloudflareKVError):
    pass


class CloudflareKVStore:
    def __init__(
        self,
        account_id: str,
        namespace_id: str,
        api_token: str,
        session: aiohttp.ClientSession,
        *,
        max_retries: int = 2,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if not account_id or not namespace_id or not api_token:
            raise ValueError("Cloudflare KV credentials must be non-empty")
        if max_retries < 0:
            raise ValueError("max_retries must be non-negative")
        account = quote(account_id, safe="")
        namespace = quote(namespace_id, safe="")
        self._base_url = (
            "https://api.cloudflare.com/client/v4/accounts/"
            f"{account}/storage/kv/namespaces/{namespace}"
        )
        self._headers = {"Authorization": f"Bearer {api_token}"}
        self._session = session
        self._max_retries = max_retries
        self._sleep = sleep

    async def get_json(self, key: str) -> Any | None:
        return await self._request_json(
            "GET",
            f"/values/{quote(key, safe='')}",
            allow_not_found=True,
        )

    async def put_json(
        self,
        key: str,
        value: Any,
        *,
        expiration_ttl: int | None = None,
    ) -> None:
        params = None
        if expiration_ttl is not None:
            if expiration_ttl <= 0:
                raise ValueError("expiration_ttl must be positive")
            params = {"expiration_ttl": str(expiration_ttl)}
        encoded = json.dumps(
            value, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
        await self._request_json(
            "PUT",
            f"/values/{quote(key, safe='')}",
            params=params,
            data=encoded,
            expect_json=False,
            content_type="application/json",
        )

    async def delete(self, key: str) -> None:
        await self._request_json(
            "DELETE",
            f"/values/{quote(key, safe='')}",
            expect_json=False,
        )

    async def list_keys(self, prefix: str = "") -> list[str]:
        keys: list[str] = []
        cursor = ""
        while True:
            params = {"prefix": prefix}
            if cursor:
                params["cursor"] = cursor
            payload = await self._request_json("GET", "/keys", params=params)
            if not isinstance(payload, dict) or payload.get("success") is not True:
                raise CloudflareKVDecodeError("Cloudflare KV list response is invalid")
            result = payload.get("result")
            if not isinstance(result, list):
                raise CloudflareKVDecodeError("Cloudflare KV key list is invalid")
            for item in result:
                if not isinstance(item, dict) or not isinstance(item.get("name"), str):
                    raise CloudflareKVDecodeError("Cloudflare KV key entry is invalid")
                keys.append(item["name"])
            result_info = payload.get("result_info")
            if result_info is None:
                cursor = ""
            elif isinstance(result_info, dict):
                next_cursor = result_info.get("cursor", "")
                if not isinstance(next_cursor, str):
                    raise CloudflareKVDecodeError("Cloudflare KV cursor is invalid")
                cursor = next_cursor
            else:
                raise CloudflareKVDecodeError("Cloudflare KV pagination is invalid")
            if not cursor:
                return keys

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        data: bytes | None = None,
        allow_not_found: bool = False,
        expect_json: bool = True,
        content_type: str | None = None,
    ) -> Any | None:
        headers = dict(self._headers)
        if content_type is not None:
            headers["Content-Type"] = content_type

        for attempt in range(self._max_retries + 1):
            try:
                async with self._session.request(
                    method,
                    f"{self._base_url}{path}",
                    headers=headers,
                    params=params,
                    data=data,
                ) as response:
                    if 200 <= response.status < 300:
                        if not expect_json:
                            return None
                        try:
                            return await response.json(content_type=None)
                        except (ValueError, TypeError) as exc:
                            raise CloudflareKVDecodeError(
                                "Cloudflare KV returned invalid JSON"
                            ) from exc
                    if response.status == 404 and allow_not_found:
                        return None
                    if response.status in (401, 403):
                        raise CloudflareKVAuthError(
                            "Cloudflare KV authentication was rejected"
                        )
                    if response.status == 429 or response.status >= 500:
                        if attempt < self._max_retries:
                            await self._sleep(min(0.25 * (2**attempt), 2.0))
                            continue
                        raise CloudflareKVTransientError(
                            "Cloudflare KV transient request failed"
                        )
                    raise CloudflareKVRequestError(
                        f"Cloudflare KV request failed with status {response.status}"
                    )
            except (
                CloudflareKVAuthError,
                CloudflareKVDecodeError,
                CloudflareKVRequestError,
                CloudflareKVTransientError,
            ):
                raise
            except (asyncio.TimeoutError, aiohttp.ClientError) as exc:
                if attempt < self._max_retries:
                    await self._sleep(min(0.25 * (2**attempt), 2.0))
                    continue
                raise CloudflareKVTransientError(
                    "Cloudflare KV request timed out or failed"
                ) from exc
        raise AssertionError("unreachable retry state")
