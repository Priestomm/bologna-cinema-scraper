"""Orchestratore del ciclo di scraping: esegue tutti gli scraper in parallelo
e salva l'esito (compresi gli avvisi) nella cache.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime

import pytz

from config import settings
from database import Cache, CacheSnapshot
from scrapers import ALL_SCRAPERS, ScraperResult
from utils import get_logger

logger = get_logger("bot.pipeline")
_TZ = pytz.timezone(settings.timezone)


def today() -> date:
    return datetime.now(_TZ).date()


def run_scrape_pipeline(target_date: date | None = None) -> CacheSnapshot:
    """Esegue tutti gli scraper, salva il risultato in cache e lo restituisce."""
    target = target_date or today()
    logger.info("=== Pipeline scraping per %s ===", target.isoformat())

    results: list[ScraperResult] = []
    scrapers = [cls() for cls in ALL_SCRAPERS]

    # Gli scraper sono indipendenti: massima parallelizzazione.
    with ThreadPoolExecutor(max_workers=len(scrapers)) as pool:
        futures = {pool.submit(s.run, target): s for s in scrapers}
        for fut in as_completed(futures):
            result = fut.result()  # run() non solleva mai
            results.append(result)

    cache = Cache()
    snapshot = cache.store(target, results)
    logger.info(
        "Pipeline completata: %d film, %d avvisi",
        len(snapshot.screenings),
        len(snapshot.warnings),
    )
    return snapshot
