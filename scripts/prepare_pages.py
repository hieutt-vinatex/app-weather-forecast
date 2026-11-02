#!/usr/bin/env python3
"""Install a Vite bundle into a publication checkout without losing data."""

from __future__ import annotations

import argparse
import os
import shutil
import tempfile
from pathlib import Path


def install_site(publication_root: Path, dist_root: Path) -> None:
    """Replace ``site/`` from a validated sibling staging directory.

    Existing ``site/data`` is copied into staging and ``state`` is never touched.
    The current site is moved aside only after the staged tree is complete.
    """
    publication_root = Path(publication_root)
    dist_root = Path(dist_root)
    index = dist_root / "index.html"
    if not dist_root.is_dir() or not index.is_file():
        raise ValueError("dist root must contain index.html")

    parent = publication_root.parent
    parent.mkdir(parents=True, exist_ok=True)
    temporary_root = Path(
        tempfile.mkdtemp(prefix=f".{publication_root.name}-site-", dir=parent)
    )
    staged_site = temporary_root / "site"
    current_site = publication_root / "site"
    backup_site = temporary_root / "previous-site"
    installed = False
    try:
        shutil.copytree(dist_root, staged_site, symlinks=False)
        staged_data = staged_site / "data"
        if staged_data.exists():
            if staged_data.is_dir():
                shutil.rmtree(staged_data)
            else:
                staged_data.unlink()
        current_data = current_site / "data"
        if current_data.is_dir():
            shutil.copytree(current_data, staged_data, symlinks=False)

        (staged_site / ".nojekyll").touch()
        shutil.copy2(staged_site / "index.html", staged_site / "404.html")
        _validate_staged_site(staged_site)

        publication_root.mkdir(parents=True, exist_ok=True)
        if current_site.exists():
            os.replace(current_site, backup_site)
        try:
            os.replace(staged_site, current_site)
            installed = True
        except Exception:
            if backup_site.exists() and not current_site.exists():
                os.replace(backup_site, current_site)
            raise
    finally:
        if installed and backup_site.exists():
            shutil.rmtree(backup_site, ignore_errors=True)
        shutil.rmtree(temporary_root, ignore_errors=True)


def _validate_staged_site(site: Path) -> None:
    index = site / "index.html"
    fallback = site / "404.html"
    marker = site / ".nojekyll"
    if not index.is_file() or not fallback.is_file() or not marker.is_file():
        raise ValueError("staged site is missing required Pages files")
    if index.read_bytes() != fallback.read_bytes():
        raise ValueError("staged site fallback does not match index.html")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Install a Vite build into a GitHub Pages publication tree."
    )
    parser.add_argument("--publication-root", required=True, type=Path)
    parser.add_argument("--dist-root", required=True, type=Path)
    args = parser.parse_args(argv)
    install_site(args.publication_root, args.dist_root)
    print("GitHub Pages site prepared")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
