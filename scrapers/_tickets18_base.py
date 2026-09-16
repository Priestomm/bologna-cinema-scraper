"""Classi base per gli scraper costruiti sul parser 18tickets condiviso.

`SingleTheaterScraper` gestisce i circuiti con un'unica pagina che elenca
gia' tutte le sale (es. Nosadella, Pop Up). `MultiTheaterScraper` gestisce
i circuiti con una pagina 18tickets separata per sala, scaricate in
parallelo e fuse nel modello standard (es. Cineteca, Circuito Cinema).
"""

from __future__ import annotations

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from typing import ClassVar

from ._tickets18 import parse_all_dates, parse_day
from .base import BaseScraper, Screening


def _tag_note(screening: Screening, label: str) -> None:
    screening.note = (screening.note + " - " if screening.note else "") + label


class SingleTheaterScraper(BaseScraper):
    """Circuito servito da un'unica pagina 18tickets con tutte le sale."""

    base_url: str = ""
    label: str = ""

    def _post_process(self, screenings: list[Screening]) -> None:
        """Hook opzionale per personalizzare gli screening prima dell'etichetta."""

    def _fetch(self, target_date: date) -> list[Screening]:
        html = self._get(self.base_url).text
        day = parse_day(html, self.name, target_date)
        self._post_process(day)
        for s in day:
            _tag_note(s, self.label)
        return day

    def fetch_all_dates(
        self, after_date: date, max_days: int = 7
    ) -> dict[date, list[Screening]]:
        html = self._get(self.base_url).text
        by_date = parse_all_dates(html, self.name, after_date, max_days)
        for screenings in by_date.values():
            self._post_process(screenings)
            for s in screenings:
                _tag_note(s, self.label)
        return by_date


class MultiTheaterScraper(BaseScraper):
    """Circuito con una pagina 18tickets per sala, scaricate in parallelo."""

    theaters: ClassVar[dict[str, str]] = {}
    label: str = ""

    def _fetch_html(self, url: str) -> str:
        return self._get(url).text

    def _fetch(self, target_date: date) -> list[Screening]:
        results: list[Screening] = []

        def _scrape_one(theater_name: str, url: str) -> list[Screening]:
            html = self._fetch_html(url)
            day = parse_day(html, theater_name, target_date)
            for s in day:
                _tag_note(s, self.label)
            return day

        with ThreadPoolExecutor(max_workers=len(self.theaters)) as pool:
            futures = {
                pool.submit(_scrape_one, name, url): name
                for name, url in self.theaters.items()
            }
            for fut in as_completed(futures):
                theater = futures[fut]
                try:
                    results.extend(fut.result())
                except Exception as exc:  # noqa: BLE001
                    self.logger.warning("Sala %s non disponibile: %s", theater, exc)

        return results

    def fetch_all_dates(
        self, after_date: date, max_days: int = 7
    ) -> dict[date, list[Screening]]:
        results: dict[date, list[Screening]] = defaultdict(list)

        def _scrape_one(theater_name: str, url: str) -> dict[date, list[Screening]]:
            html = self._fetch_html(url)
            by_date = parse_all_dates(html, theater_name, after_date, max_days)
            for screenings in by_date.values():
                for s in screenings:
                    _tag_note(s, self.label)
            return by_date

        with ThreadPoolExecutor(max_workers=len(self.theaters)) as pool:
            futures = {
                pool.submit(_scrape_one, name, url): name
                for name, url in self.theaters.items()
            }
            for fut in as_completed(futures):
                theater = futures[fut]
                try:
                    by_date = fut.result()
                    for d, screenings in by_date.items():
                        results[d].extend(screenings)
                except Exception as exc:  # noqa: BLE001
                    self.logger.warning("Sala %s non disponibile: %s", theater, exc)

        return dict(results)
