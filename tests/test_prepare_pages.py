from __future__ import annotations

from pathlib import Path

import pytest

from scripts.prepare_pages import install_site


def _files(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def test_install_site_replaces_bundle_and_preserves_publication_state(
    tmp_path: Path,
):
    publication = tmp_path / "publication"
    (publication / "site/assets").mkdir(parents=True)
    (publication / "site/data/versions/v1").mkdir(parents=True)
    (publication / "state").mkdir(parents=True)
    (publication / "site/index.html").write_text("old", encoding="utf-8")
    (publication / "site/assets/old.js").write_text("old", encoding="utf-8")
    (publication / "site/data/manifest.json").write_text("{}", encoding="utf-8")
    (publication / "site/data/versions/v1/snapshot-30.json").write_text(
        "{}", encoding="utf-8"
    )
    (publication / "state/telegram-ledger.json").write_text(
        '{"version":1,"events":{},"providers":{}}', encoding="utf-8"
    )

    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("new bundle", encoding="utf-8")
    (dist / "assets/new.js").write_text("new asset", encoding="utf-8")

    install_site(publication, dist)

    assert (publication / "site/index.html").read_text(encoding="utf-8") == "new bundle"
    assert (publication / "site/404.html").read_text(encoding="utf-8") == "new bundle"
    assert (publication / "site/.nojekyll").is_file()
    assert (publication / "site/assets/new.js").is_file()
    assert not (publication / "site/assets/old.js").exists()
    assert (publication / "site/data/manifest.json").read_text(encoding="utf-8") == "{}"
    assert (publication / "site/data/versions/v1/snapshot-30.json").is_file()
    assert (publication / "state/telegram-ledger.json").is_file()


def test_install_site_rejects_dist_without_index_and_keeps_tree_unchanged(
    tmp_path: Path,
):
    publication = tmp_path / "publication"
    (publication / "site/data").mkdir(parents=True)
    (publication / "site/index.html").write_text("stable", encoding="utf-8")
    (publication / "site/data/manifest.json").write_text("{}", encoding="utf-8")
    before = _files(publication)
    dist = tmp_path / "dist"
    dist.mkdir()

    with pytest.raises(ValueError, match="index.html"):
        install_site(publication, dist)

    assert _files(publication) == before


def test_install_site_keeps_original_tree_when_staging_validation_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    publication = tmp_path / "publication"
    (publication / "site/data").mkdir(parents=True)
    (publication / "site/index.html").write_text("stable", encoding="utf-8")
    (publication / "site/data/manifest.json").write_text("{}", encoding="utf-8")
    before = _files(publication)
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("new", encoding="utf-8")

    def fail_validation(_site: Path) -> None:
        raise ValueError("staged site is invalid")

    monkeypatch.setattr("scripts.prepare_pages._validate_staged_site", fail_validation)

    with pytest.raises(ValueError, match="staged site"):
        install_site(publication, dist)

    assert _files(publication) == before
