from __future__ import annotations

from pathlib import Path

import pytest

from app.cloud.filesystem_store import FilesystemJsonStore


def test_logical_keys_map_to_public_and_private_branch_paths(tmp_path: Path):
    store = FilesystemJsonStore(tmp_path)

    assert store.path_for_key("manifest:v1") == tmp_path / "site/data/manifest.json"
    assert store.path_for_key("job-status:v1:data") == tmp_path / "site/data/status.json"
    assert (
        store.path_for_key("notification-state:v1")
        == tmp_path / "state/telegram-ledger.json"
    )
    assert (
        store.path_for_key("history:v1:v1")
        == tmp_path / "site/data/versions/v1/history.json"
    )
    assert (
        store.path_for_key("snapshot:v1:v1:30")
        == tmp_path / "site/data/versions/v1/snapshot-30.json"
    )


async def test_json_round_trip_listing_and_delete_are_stable(tmp_path: Path):
    store = FilesystemJsonStore(tmp_path)
    first = {"text": "Tiếng Việt", "nested": {"ok": True}}

    await store.put_json("history:v1:v2", {"version": 2})
    await store.put_json("history:v1:v1", first)

    assert await store.get_json("history:v1:v1") == first
    assert await store.list_keys("history:v1:") == [
        "history:v1:v1",
        "history:v1:v2",
    ]
    assert "Tiếng Việt" in store.path_for_key("history:v1:v1").read_text(
        encoding="utf-8"
    )

    await store.delete("history:v1:v1")

    assert await store.get_json("history:v1:v1") is None
    assert await store.list_keys("history:v1:") == ["history:v1:v2"]


async def test_oversized_value_is_rejected_before_replacing_existing_file(
    tmp_path: Path,
):
    store = FilesystemJsonStore(tmp_path, max_value_bytes=32)
    await store.put_json("manifest:v1", {"version": "old"})

    with pytest.raises(ValueError, match="safe byte limit"):
        await store.put_json("manifest:v1", {"payload": "x" * 64})

    assert await store.get_json("manifest:v1") == {"version": "old"}


@pytest.mark.parametrize(
    "key",
    [
        "unknown:v1",
        "history:v1:..",
        "history:v1:../../secret",
        "snapshot:v1:v1:31",
        "operation:v1:not-a-uuid",
    ],
)
def test_unknown_or_unsafe_keys_are_rejected(tmp_path: Path, key: str):
    store = FilesystemJsonStore(tmp_path)

    with pytest.raises(ValueError, match="unsupported storage key"):
        store.path_for_key(key)
