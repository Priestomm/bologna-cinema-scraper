"""Modello dati standard + classe astratta degli scraper.

Ogni scraper concreto deve:
- ereditare da BaseScraper
- impostare attributi `name` (etichetta cinema) e `slug`
- implementare `_fetch(target_date)` restituendo list[Screening]

`run(target_date)` e `run_all_dates(start, days)` eseguono lo scraper in un
thread isolato con timeout rigido e catturano qualunque eccezione. Il
chiamante riceve sempre un risultato, non solleva mai. Cosi un cinema rotto
non puo far cadere la pipeline.
"""

from __future__ import annotations

import abc
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
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
    poster_url: str = ""
    rating: str = ""
    regista: str = ""
    url: str = ""
    genre: str = ""
    poster_url_tmdb: str = ""
    clean_title_tmdb: str = ""
    overview: str = ""
    runtime: int = 0
    times_urls: dict[str, str] = field(default_factory=dict)
    # Slug dello scraper che l'ha prodotto (lo imposta BaseScraper, non il
    # singolo scraper): `cinema` e' la sala ("Cineteca - Lumiere"), questo e'
    # il circuito, usato dalla pipeline per ripescare dalla cache i dati di un
    # circuito quando il suo scraping fallisce.
    circuito: str = ""

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


@dataclass
class MultiDayResult:
    """Esito di uno scraping multi-giorno: proiezioni raggruppate per data."""

    name: str
    slug: str
    by_date: dict[date, list[Screening]]
    success: bool
    error: str | None = None


def _call_with_timeout[T](fn: Callable[..., T], *args: Any, timeout: float) -> T:
    """Esegue fn in un thread dedicato e smette di aspettarlo dopo `timeout`.

    Niente `with ThreadPoolExecutor(...)`: all'uscita dal blocco il context
    manager chiama shutdown(wait=True), che aspetterebbe comunque la fine di
    fn rendendo il timeout inutile. Il thread scaduto non si puo' uccidere:
    resta in background finche' le sue richieste HTTP (ognuna col proprio
    timeout) non terminano, ma la pipeline va avanti.
    """
    pool = ThreadPoolExecutor(max_workers=1)
    try:
        return pool.submit(fn, *args).result(timeout=timeout)
    finally:
        pool.shutdown(wait=False)


def _clean(screenings: list[Screening], slug: str) -> list[Screening]:
    """Difesa: tiene solo Screening validi e li marca col circuito."""
    clean = [s for s in screenings if isinstance(s, Screening) and s.titolo]
    for s in clean:
        s.circuito = slug
    return clean


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
            screenings = _call_with_timeout(
                self._fetch, target_date, timeout=settings.scraper_timeout
            )
        except FuturesTimeout:
            msg = f"timeout dopo {settings.scraper_timeout}s"
            self.logger.warning("Scraper %s fallito: %s", self.slug, msg)
            return ScraperResult(self.name, self.slug, [], success=False, error=msg)
        except Exception as exc:
            self.logger.exception("Scraper %s fallito", self.slug)
            return ScraperResult(
                self.name, self.slug, [], success=False, error=str(exc)
            )

        clean = _clean(screenings, self.slug)
        self.logger.info("Scraper %s OK: %d film", self.slug, len(clean))
        return ScraperResult(self.name, self.slug, clean, success=True)

    def run_all_dates(self, after_date: date, max_days: int = 7) -> MultiDayResult:
        """Come run(), ma per fetch_all_dates: N giorni con un'unica chiamata.

        Il timeout e' settings.scraper_total_timeout (non scraper_timeout):
        qui uno scraper puo' fare piu' richieste HTTP e retry su 429.
        """
        timeout = settings.scraper_total_timeout
        self.logger.info("Avvio scraping multi-giorno da %s", after_date.isoformat())
        try:
            by_date = _call_with_timeout(
                self.fetch_all_dates, after_date, max_days, timeout=timeout
            )
        except FuturesTimeout:
            msg = f"timeout dopo {timeout}s"
            self.logger.warning("Scraper %s fallito: %s", self.slug, msg)
            return MultiDayResult(self.name, self.slug, {}, success=False, error=msg)
        except Exception as exc:
            self.logger.exception("Scraper %s fallito", self.slug)
            return MultiDayResult(
                self.name, self.slug, {}, success=False, error=str(exc)
            )

        clean = {d: _clean(screenings, self.slug) for d, screenings in by_date.items()}
        total = sum(len(v) for v in clean.values())
        self.logger.info("Scraper %s OK: %d proiezioni", self.slug, total)
        return MultiDayResult(self.name, self.slug, clean, success=True)

    # ---- da implementare ---------------------------------------------

    @abc.abstractmethod
    def _fetch(self, target_date: date) -> list[Screening]:
        """Logica concreta di estrazione dati per il giorno richiesto."""

    def fetch_all_dates(
        self, after_date: date, max_days: int = 7
    ) -> dict[date, list[Screening]]:
        """Versione multi-giorno: chiama _fetch per ogni data.

        Override nelle sottoclassi per fare un'unica richiesta HTML
        ed estrarre tutte le date (evita 429).
        """
        result: dict[date, list[Screening]] = {}
        for i in range(max_days):
            d = after_date + timedelta(days=i)
            result[d] = self._fetch(d)
        return result

    # ---- helper condivisi --------------------------------------------

    def _get(self, url: str, **kwargs: Any) -> requests.Response:
        """Wrapper sopra requests con timeout di default e logging."""
        kwargs.setdefault("timeout", settings.scraper_timeout)
        self.logger.debug("GET %s", url)
        response = self._session.get(url, **kwargs)
        response.raise_for_status()
        return response
