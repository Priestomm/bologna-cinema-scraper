from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path

from database.cache import Cache
from scrapers.base import ScraperResult, Screening


class TestCache:
    def _make_cache(self) -> Cache:
        tmp = Path(tempfile.mkdtemp()) / "test_cache.sqlite3"
        return Cache(db_path=tmp)

    def _ok_result(self, screenings: list[Screening]) -> ScraperResult:
        return ScraperResult(
            name="Test Cinema",
            slug="test",
            screenings=screenings,
            success=True,
        )

    def _fail_result(self) -> ScraperResult:
        return ScraperResult(
            name="Test Cinema",
            slug="test",
            screenings=[],
            success=False,
            error="timeout dopo 15s",
        )

    def test_store_and_load(self) -> None:
        cache = self._make_cache()
        d = date(2026, 6, 8)
        screenings = [Screening(cinema="Rialto", titolo="Parasite", orari=["18:00"])]
        result = self._ok_result(screenings)

        snap = cache.store(d, [result])
        assert snap.screenings == screenings
        assert snap.warnings == []

        loaded = cache.load(d)
        assert loaded is not None
        assert len(loaded.screenings) == 1
        assert loaded.screenings[0].titolo == "Parasite"

    def test_upsert(self) -> None:
        cache = self._make_cache()
        d = date(2026, 6, 8)
        r1 = self._ok_result([Screening(cinema="A", titolo="Old", orari=["10:00"])])
        r2 = self._ok_result([Screening(cinema="A", titolo="New", orari=["10:00"])])

        cache.store(d, [r1])
        cache.store(d, [r2])

        loaded = cache.load(d)
        assert loaded is not None
        assert len(loaded.screenings) == 1
        assert loaded.screenings[0].titolo == "New"

    def test_failed_scraper_adds_warning(self) -> None:
        cache = self._make_cache()
        d = date(2026, 6, 8)
        ok = self._ok_result([Screening(cinema="A", titolo="Film", orari=["10:00"])])
        fail = self._fail_result()

        snap = cache.store(d, [ok, fail])
        assert len(snap.warnings) == 1
        assert "timeout" in snap.warnings[0]

    def test_empty_result_adds_warning(self) -> None:
        cache = self._make_cache()
        d = date(2026, 6, 8)
        empty = self._ok_result([])

        snap = cache.store(d, [empty])
        assert len(snap.warnings) == 1
        assert "Nessuna proiezione" in snap.warnings[0]

    def test_load_nonexistent(self) -> None:
        cache = self._make_cache()
        assert cache.load(date(2099, 1, 1)) is None

    def test_is_empty(self) -> None:
        cache = self._make_cache()
        d = date(2026, 6, 8)
        snap = cache.store(d, [self._ok_result([])])
        assert snap.is_empty is True

    def test_is_not_empty(self) -> None:
        cache = self._make_cache()
        d = date(2026, 6, 8)
        screenings = [Screening(cinema="A", titolo="Film", orari=["10:00"])]
        snap = cache.store(d, [self._ok_result(screenings)])
        assert snap.is_empty is False
