"""Scraper Circuito Cinema Bologna.

Backend: ccb.18tickets.it con sottodomini per ogni sala
(rialto, odeon, europa, roma). Si recuperano i 4 in parallelo
e si fondono i risultati nel modello standard.
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

import requests

from .base import BaseScraper, Screening
from ._tickets18 import parse_day

_THEATERS = {
    "Rialto": "https://rialto.ccb.18tickets.it/",
    "Odeon": "https://odeon.ccb.18tickets.it/",
    "Europa": "https://europa.ccb.18tickets.it/",
    "Roma D'Azeglio": "https://roma.ccb.18tickets.it/",
}


class CircuitoCinemaScraper(BaseScraper):
    name = "Circuito Cinema Bologna"
    slug = "circuito"

    def _get_with_retry(self, url: str, attempts: int = 3) -> str:
        """GET con retry su 429 / errori transitori (backoff progressivo)."""
        last_exc: Exception | None = None
        for i in range(attempts):
            try:
                return self._get(url).text
            except requests.HTTPError as exc:
                status = exc.response.status_code if exc.response is not None else 0
                if status not in (429, 502, 503, 504) or i == attempts - 1:
                    raise
                last_exc = exc
                wait = 0.7 * (i + 1)
                self.logger.debug("Retry %s (HTTP %s) tra %.1fs", url, status, wait)
                time.sleep(wait)
        raise RuntimeError(f"retry esauriti: {last_exc}")

    def _fetch(self, target_date: date) -> list[Screening]:
        results: list[Screening] = []

        def _scrape_one(theater_name: str, url: str) -> list[Screening]:
            html = self._get_with_retry(url)
            day = parse_day(html, theater_name, target_date)
            for s in day:
                # Rietichetta esplicita del circuito di appartenenza.
                s.note = (s.note + " - " if s.note else "") + "Circuito Cinema"
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
                    self.logger.warning(
                        "Sala %s non disponibile: %s", theater, exc
                    )

        return results
