from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path
from unittest.mock import patch

from core.backup import backup_cache
from database.cache import Cache
from scrapers.base import ScraperResult, Screening


def _cache(tmp_path: Path) -> Cache:
    cache = Cache(tmp_path / "cache.sqlite3")
    result = ScraperResult(
        name="Rialto",
        slug="rialto",
        screenings=[Screening(cinema="Rialto", titolo="Parasite", orari=["21:00"])],
        success=True,
    )
    cache.store(date(2026, 10, 7), [result])
    return cache


def test_backup_leggibile(tmp_path: Path) -> None:
    cache = _cache(tmp_path)
    with patch("core.backup.today", return_value=date(2026, 10, 7)):
        dest = backup_cache(cache, tmp_path / "backups", keep=14)

    assert dest.name == "cache-2026-10-07.sqlite3"
    snap = Cache(dest).load(date(2026, 10, 7))
    assert snap is not None
    assert [s.titolo for s in snap.screenings] == ["Parasite"]


def test_rotazione_tiene_gli_ultimi(tmp_path: Path) -> None:
    cache = _cache(tmp_path)
    backups = tmp_path / "backups"
    backups.mkdir()
    for day in range(1, 6):
        sqlite3.connect(backups / f"cache-2026-10-0{day}.sqlite3").close()
    (backups / "altro-file.txt").write_text("non toccare")

    with patch("core.backup.today", return_value=date(2026, 10, 7)):
        backup_cache(cache, backups, keep=3)

    assert sorted(p.name for p in backups.iterdir()) == [
        "altro-file.txt",
        "cache-2026-10-04.sqlite3",
        "cache-2026-10-05.sqlite3",
        "cache-2026-10-07.sqlite3",
    ]
