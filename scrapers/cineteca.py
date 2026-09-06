"""Scraper Cineteca di Bologna.

Backend: cinetecabologna.18tickets.it. La programmazione del giorno e'
distribuita sui sottodomini delle due sale (Lumiere e Modernissimo);
il root mostra solo "in arrivo" e link generici, quindi scrapiamo i
sottodomini in parallelo.
"""

from __future__ import annotations

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

from ._tickets18 import parse_all_dates, parse_day
from .base import BaseScraper, Screening

_THEATERS = {
    "Cineteca - Lumiere": "https://lumiere.cinetecabologna.18tickets.it/",
    "Cineteca - Modernissimo": "https://modernissimo.cinetecabologna.18tickets.it/",
}


class CinetecaScraper(BaseScraper):
    name = "Cineteca di Bologna"
    slug = "cineteca"

    def _fetch(self, target_date: date) -> list[Screening]:
        results: list[Screening] = []

        def _scrape_one(theater_name: str, url: str) -> list[Screening]:
            html = self._get(url).text
            day = parse_day(html, theater_name, target_date)
            for s in day:
                # Etichetta esplicita del circuito per il render finale.
                s.note = (s.note + " - " if s.note else "") + "Cineteca"
            return day

        with ThreadPoolExecutor(max_workers=len(_THEATERS)) as pool:
            futures = {
                pool.submit(_scrape_one, name, url): name
                for name, url in _THEATERS.items()
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
            html = self._get(url).text
            by_date = parse_all_dates(html, theater_name, after_date, max_days)
            for screenings in by_date.values():
                for s in screenings:
                    s.note = (s.note + " - " if s.note else "") + "Cineteca"
            return by_date

        with ThreadPoolExecutor(max_workers=len(_THEATERS)) as pool:
            futures = {
                pool.submit(_scrape_one, name, url): name
                for name, url in _THEATERS.items()
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
