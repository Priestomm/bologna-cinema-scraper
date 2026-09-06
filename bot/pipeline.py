"""Orchestratore del ciclo di scraping: esegue tutti gli scraper in parallelo
e salva l'esito (compresi gli avvisi) nella cache.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta

import pytz

from config import settings
from database import Cache, CacheSnapshot
from scrapers import ALL_SCRAPERS, ScraperResult
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
