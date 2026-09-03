"""Modello dati standard + classe astratta degli scraper.

Ogni scraper concreto deve:
- ereditare da BaseScraper
- impostare attributi `name` (etichetta cinema) e `slug`
- implementare `_fetch(target_date)` restituendo list[Screening]

`run(target_date)` esegue lo scraper in un thread isolato con timeout rigido
e cattura qualunque eccezione. Il chiamante riceve sempre uno ScraperResult,
non solleva mai. Cosi un cinema rotto non puo far cadere la pipeline.
"""

from __future__ import annotations

import abc
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

import requests

from config import settings
from utils import get_logger


@dataclass
class Screening:
    """Modello standardizzato richiesto dalla specifica.

    Tutti gli scraper devono produrre oggetti con esattamente questi campi.
    """

    cinema: str
    titolo: str
    orari: list[str] = field(default_factory=list)
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ScraperResult:
    """Esito dell'esecuzione di un singolo scraper."""

    name: str
    slug: str
    screenings: list[Screening]
    success: bool
    error: str | None = None


class BaseScraper(abc.ABC):
    name: str = "unknown"
    slug: str = "unknown"

    def __init__(self) -> None:
        self.logger = get_logger(f"scrapers.{self.slug}")
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": settings.http_user_agent})

    # ---- API pubblica -------------------------------------------------

    def run(self, target_date: date) -> ScraperResult:
        """Esegue lo scraping con timeout rigido e isolamento errori."""
        self.logger.info("Avvio scraping per %s", target_date.isoformat())
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(self._fetch, target_date)
                screenings = future.result(timeout=settings.scraper_timeout)
        except FuturesTimeout:
            msg = f"timeout dopo {settings.scraper_timeout}s"
            self.logger.warning("Scraper %s fallito: %s", self.slug, msg)
            return ScraperResult(self.name, self.slug, [], success=False, error=msg)
        except Exception as exc:
            self.logger.exception("Scraper %s fallito", self.slug)
            return ScraperResult(
                self.name, self.slug, [], success=False, error=str(exc)
            )

        # Difesa: assicura che ogni elemento sia uno Screening valido.
        clean = [s for s in screenings if isinstance(s, Screening) and s.titolo]
        self.logger.info("Scraper %s OK: %d film", self.slug, len(clean))
        return ScraperResult(self.name, self.slug, clean, success=True)

    # ---- da implementare ---------------------------------------------

    @abc.abstractmethod
    def _fetch(self, target_date: date) -> list[Screening]:
        """Logica concreta di estrazione dati per il giorno richiesto."""

    # ---- helper condivisi --------------------------------------------

    def _get(self, url: str, **kwargs: Any) -> requests.Response:
        """Wrapper sopra requests con timeout di default e logging."""
        kwargs.setdefault("timeout", settings.scraper_timeout)
        self.logger.debug("GET %s", url)
        response = self._session.get(url, **kwargs)
        response.raise_for_status()
        return response
