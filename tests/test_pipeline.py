from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from config import settings
from core import pipeline
from database.cache import Cache, CacheSnapshot
from scrapers.base import BaseScraper, Screening

# Data lontana dall'oggi reale: il filtro sugli orari passati del fallback
# vale solo per oggi e qui non deve scattare.
START = date(2099, 3, 2)


class _FakeScraper(BaseScraper):
    """Scraper finto: ogni sottoclasse decide cosa restituire per giorno."""

    behaviour: str = "ok"  # "ok" | "error" | "empty"

    def _fetch(self, target_date: date) -> list[Screening]:
        return self.fetch_all_dates(target_date, 1).get(target_date, [])

    def fetch_all_dates(
        self, after_date: date, max_days: int = 7
    ) -> dict[date, list[Screening]]:
        if self.behaviour == "error":
            raise RuntimeError("HTTP 503")
        if self.behaviour == "empty":
            return {}
        return {
            after_date + timedelta(days=i): [
                Screening(cinema=self.name, titolo=f"Film {self.slug}", orari=["21:00"])
            ]
            for i in range(max_days)
        }


class _Alpha(_FakeScraper):
    name = "Alpha"
    slug = "alpha"


class _Beta(_FakeScraper):
    name = "Beta"
    slug = "beta"


@pytest.fixture
def cache(tmp_path: Path) -> Iterator[Cache]:
    cache = Cache(tmp_path / "cache.sqlite3")
    with (
        patch.object(pipeline, "Cache", return_value=cache),
        patch.object(pipeline, "ALL_SCRAPERS", [_Alpha, _Beta]),
        patch.object(pipeline, "_enrich"),
    ):
        yield cache
    _Beta.behaviour = "ok"


def _titles(snapshot: CacheSnapshot) -> set[str]:
    return {s.titolo for s in snapshot.screenings}


class TestMultiDayFallback:
    def test_tutto_ok(self, cache: Cache) -> None:
        snaps = pipeline.run_multi_day_pipeline(START, days=2)
        assert len(snaps) == 2
        assert _titles(snaps[0]) == {"Film alpha", "Film beta"}
        assert snaps[0].warnings == []
        # Ogni proiezione sa da che circuito arriva.
        assert {s.circuito for s in snaps[0].screenings} == {"alpha", "beta"}

    def test_circuito_fallito_tiene_i_dati_precedenti(self, cache: Cache) -> None:
        pipeline.run_multi_day_pipeline(START, days=2)
        _Beta.behaviour = "error"

        snaps = pipeline.run_multi_day_pipeline(START, days=2)

        for snap in snaps:
            assert _titles(snap) == {"Film alpha", "Film beta"}
            assert len(snap.warnings) == 1
            assert "Circuito non disponibile: Beta (HTTP 503)" in snap.warnings[0]
            assert "ultimo aggiornamento riuscito" in snap.warnings[0]

    def test_zero_proiezioni_conta_come_fallimento(self, cache: Cache) -> None:
        pipeline.run_multi_day_pipeline(START, days=2)
        _Beta.behaviour = "empty"

        snap = pipeline.run_multi_day_pipeline(START, days=2)[0]

        assert _titles(snap) == {"Film alpha", "Film beta"}
        assert "Nessuna proiezione trovata per Beta" in snap.warnings[0]
        assert "selettori" in snap.warnings[0]

    def test_fallimento_senza_snapshot_precedente(self, cache: Cache) -> None:
        _Beta.behaviour = "error"

        snap = pipeline.run_multi_day_pipeline(START, days=1)[0]

        assert _titles(snap) == {"Film alpha"}
        assert snap.warnings == ["Circuito non disponibile: Beta (HTTP 503)."]

    def test_scraping_singolo_giorno_usa_lo_stesso_fallback(self, cache: Cache) -> None:
        pipeline.run_scrape_pipeline(START)
        _Beta.behaviour = "error"

        snap = pipeline.run_scrape_pipeline(START)

        assert isinstance(snap, CacheSnapshot)
        assert _titles(snap) == {"Film alpha", "Film beta"}


class TestFallbackOrariPassati:
    def _previous(self, d: date) -> CacheSnapshot:
        return CacheSnapshot(
            target_date=d,
            updated_at=datetime(2099, 1, 1, tzinfo=UTC),
            screenings=[
                Screening(
                    cinema="Beta",
                    titolo="Mattina",
                    orari=["10:00", "11:00"],
                    circuito="beta",
                ),
                Screening(
                    cinema="Beta",
                    titolo="Sera",
                    orari=["16:00", "21:00"],
                    circuito="beta",
                ),
                Screening(cinema="Alpha", titolo="Altro", orari=["22:00"]),
            ],
            warnings=[],
        )

    def test_oggi_scarta_gli_orari_passati(self) -> None:
        now = datetime(2099, 3, 2, 18, 30, tzinfo=UTC)
        kept = pipeline._fallback(self._previous(now.date()), "beta", now.date(), now)
        assert [(s.titolo, s.orari) for s in kept] == [("Sera", ["21:00"])]

    def test_altri_giorni_restano_intatti(self) -> None:
        now = datetime(2099, 3, 2, 18, 30, tzinfo=UTC)
        d = now.date() + timedelta(days=1)
        kept = pipeline._fallback(self._previous(d), "beta", d, now)
        assert [s.titolo for s in kept] == ["Mattina", "Sera"]


class _Slow(BaseScraper):
    name = "Lento"
    slug = "lento"
    release = threading.Event()

    def _fetch(self, target_date: date) -> list[Screening]:
        self.release.wait(5)
        return []

    def fetch_all_dates(
        self, after_date: date, max_days: int = 7
    ) -> dict[date, list[Screening]]:
        self.release.wait(5)
        return {}


class TestTimeoutRigido:
    """Il timeout deve restituire subito il controllo, non aspettare lo scraper."""

    @pytest.fixture(autouse=True)
    def _release(self) -> Iterator[None]:
        _Slow.release.clear()
        yield
        _Slow.release.set()

    def test_run_all_dates(self) -> None:
        fast = replace(settings, scraper_total_timeout=1)
        with patch("scrapers.base.settings", fast):
            t0 = time.monotonic()
            result = _Slow().run_all_dates(START, 2)
        assert time.monotonic() - t0 < 3
        assert not result.success
        assert result.error is not None and "timeout" in result.error

    def test_run(self) -> None:
        fast = replace(settings, scraper_timeout=1)
        with patch("scrapers.base.settings", fast):
            t0 = time.monotonic()
            result = _Slow().run(START)
        assert time.monotonic() - t0 < 3
        assert not result.success
