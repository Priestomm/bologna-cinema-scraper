"""Orchestratore del ciclo di scraping: esegue tutti gli scraper in parallelo
e salva l'esito (compresi gli avvisi) nella cache.
"""

from __future__ import annotations

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta

import pytz

from config import settings
from database import Cache, CacheSnapshot
from scrapers import ALL_SCRAPERS, ScraperResult
from scrapers.base import Screening
from utils import get_logger

logger = get_logger("bot.pipeline")
_TZ = pytz.timezone(settings.timezone)


def today() -> date:
    return datetime.now(_TZ).date()


def _scrape_one_day(target: date, cache: Cache) -> CacheSnapshot:
    """Esegue gli scraper per un singolo giorno e salva in cache."""
    logger.info("--- Scraping %s ---", target.isoformat())

    results: list[ScraperResult] = []
    scrapers = [cls() for cls in ALL_SCRAPERS]

    with ThreadPoolExecutor(max_workers=len(scrapers)) as pool:
        futures = {pool.submit(s.run, target): s for s in scrapers}
        for fut in as_completed(futures):
            results.append(fut.result())

    snapshot = cache.store(target, results)
    logger.info(
        "  %s: %d film, %d avvisi",
        target.isoformat(),
        len(snapshot.screenings),
        len(snapshot.warnings),
    )
    return snapshot


def run_scrape_pipeline(
    target_date: date | None = None, *, days: int = 1
) -> CacheSnapshot | list[CacheSnapshot]:
    """Esegue lo scraping per *days* giorni a partire da *target_date* (default: oggi).

    Se days == 1 restituisce un singolo CacheSnapshot (retro-compatibile).
    Se days > 1 restituisce la lista dei snapshot, uno per giorno.
    """
    start = target_date or today()
    cache = Cache()

    if days == 1:
        return _scrape_one_day(start, cache)

    snapshots: list[CacheSnapshot] = []
    for i in range(days):
        d = start + timedelta(days=i)
        snapshots.append(_scrape_one_day(d, cache))

    logger.info(
        "Pipeline completata: %d giorni, %d film totali",
        days,
        sum(len(s.screenings) for s in snapshots),
    )
    return snapshots


def run_multi_day_pipeline(
    target_date: date | None = None, *, days: int = 7
) -> list[CacheSnapshot]:
    """Scrapa ogni circuito UNA sola volta ed estrae N giorni dall'HTML.

    Evita 429 rate-limit: 4-8 richieste HTTP totali invece di 4*N.
    """
    start = target_date or today()
    cache = Cache()

    # 1) Chiamata singola per scraper — tutti i giorni insieme
    all_by_date: dict[date, list[Screening]] = defaultdict(list)
    warnings: list[str] = []

    def _run_scraper(scraper_cls: type) -> None:
        scraper = scraper_cls()
        logger.info("Scraping multi-giorno: %s", scraper.name)
        try:
            dates = scraper.fetch_all_dates(start, days)
            for d, screenings in dates.items():
                all_by_date[d].extend(screenings)
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"Circuito non disponibile: {scraper.name} ({exc})")
            logger.warning("Scraper %s fallito: %s", scraper.slug, exc)

    scrapers = [cls() for cls in ALL_SCRAPERS]
    with ThreadPoolExecutor(max_workers=len(scrapers)) as pool:
        pool.map(_run_scraper, [cls for cls in ALL_SCRAPERS])

    # 2) Salva ogni giorno in cache con il formato atteso
    snapshots: list[CacheSnapshot] = []
    for i in range(days):
        d = start + timedelta(days=i)
        day_screenings = all_by_date.get(d, [])

        results: list[ScraperResult] = []
        if day_screenings:
            results.append(
                ScraperResult(
                    name="Tutti i circuiti",
                    slug="all",
                    screenings=day_screenings,
                    success=True,
                )
            )

        # Aggiungi warning globali (scraper falliti)
        if warnings:
            results.append(
                ScraperResult(
                    name="Avvisi",
                    slug="warnings",
                    screenings=[],
                    success=False,
                    error="; ".join(warnings),
                )
            )

        snapshot = cache.store(d, results)
        logger.info(
            "  %s: %d film, %d avvisi",
            d.isoformat(),
            len(snapshot.screenings),
            len(snapshot.warnings),
        )
        snapshots.append(snapshot)

    logger.info(
        "Pipeline multi-giorno completata: %d giorni, %d film totali",
        days,
        sum(len(s.screenings) for s in snapshots),
    )
    return snapshots
