"""Scraper Circuito Cinema Bologna.

Backend: ccb.18tickets.it con sottodomini per ogni sala
(rialto, odeon, europa, roma). Si recuperano i 4 in parallelo
e si fondono i risultati nel modello standard.
"""

from __future__ import annotations

import time
from typing import ClassVar

import requests

from ._tickets18_base import MultiTheaterScraper


class CircuitoCinemaScraper(MultiTheaterScraper):
    name = "Circuito Cinema Bologna"
    slug = "circuito"
    label = "Circuito Cinema"
    theaters: ClassVar[dict[str, str]] = {
        "Rialto": "https://rialto.ccb.18tickets.it/",
        "Odeon": "https://odeon.ccb.18tickets.it/",
        "Europa": "https://europa.ccb.18tickets.it/",
        "Roma D'Azeglio": "https://roma.ccb.18tickets.it/",
    }

    def _fetch_html(self, url: str) -> str:
        return self._get_with_retry(url)

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
