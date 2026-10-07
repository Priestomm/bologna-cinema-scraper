"""Orchestratore del ciclo di scraping: esegue tutti gli scraper in parallelo
e salva l'esito (compresi gli avvisi) nella cache.

Se un circuito fallisce (errore, timeout o zero proiezioni), le sue
proiezioni vengono ripescate dallo snapshot precedente dello stesso giorno
invece di sparire: il refresh gira ogni 15 minuti, e un sito lento per un
minuto non deve svuotare il sito o il broadcast delle 8:00.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
from datetime import date, datetime, timedelta

import pytz

from config import settings
from core.timeslots import parse_time
from database import Cache, CacheSnapshot
from scrapers import ALL_SCRAPERS, MultiDayResult, ScraperResult
from scrapers.base import Screening
from scrapers.tmdb import TmdbClient
from utils import get_logger

logger = get_logger("core.pipeline")
_TZ = pytz.timezone(settings.timezone)


def today() -> date:
    return datetime.now(_TZ).date()


def _minutes(ora: str) -> int:
    """Minuti da mezzanotte; un orario illeggibile si tiene (vale 24:00)."""
    try:
        return parse_time(ora)
    except ValueError:
        return 24 * 60


def _fallback(
    previous: CacheSnapshot | None, slug: str, d: date, now: datetime
) -> list[Screening]:
    """Proiezioni del circuito `slug` nello snapshot precedente di `d`.

    Per oggi scarta gli orari gia' passati: i siti dei cinema smettono di
    elencarli, e il fallback non deve farli ricomparire.
    """
    if previous is None:
        return []
    kept = [s for s in previous.screenings if s.circuito == slug]
    if d != now.date():
        return kept
    now_minutes = now.hour * 60 + now.minute
    result = []
    for s in kept:
        orari = [o for o in s.orari if _minutes(o) >= now_minutes]
        if orari:
            result.append(replace(s, orari=orari))
    return result


def _store_day(
    cache: Cache,
    d: date,
    fresh: list[Screening],
    failures: dict[str, str],
) -> CacheSnapshot:
    """Salva un giorno: proiezioni fresche + fallback per i circuiti falliti.

    `failures` mappa lo slug del circuito fallito all'avviso da mostrare.
    """
    previous = cache.load(d) if failures else None
    screenings = list(fresh)
    warnings: list[str] = []
    now = datetime.now(_TZ)
    for slug, message in failures.items():
        kept = _fallback(previous, slug, d, now)
        screenings.extend(kept)
        if kept:
            message += " Mostro gli orari dell'ultimo aggiornamento riuscito."
        warnings.append(message)

    snapshot = cache.store_snapshot(d, screenings, warnings)
    logger.info(
        "  %s: %d film, %d avvisi",
        d.isoformat(),
        len(snapshot.screenings),
        len(snapshot.warnings),
    )
    return snapshot


def _enrich(screenings: list[Screening]) -> None:
    """Enrichment TMDb in place: rating, genere, poster, sinossi, durata."""
    if not screenings:
        return
    tmdb = TmdbClient()
    if tmdb.enabled:
        logger.info("Enrichment TMDb: cerco info per %d film", len(screenings))
        tmdb.enrich_screenings(screenings)
    else:
        logger.info("TMDb disabilitato (nessuna TMDB_API_KEY)")


def _scrape_one_day(target: date, cache: Cache) -> CacheSnapshot:
    """Esegue gli scraper per un singolo giorno e salva in cache."""
    logger.info("--- Scraping %s ---", target.isoformat())

    results: list[ScraperResult] = []
    scrapers = [cls() for cls in ALL_SCRAPERS]

    with ThreadPoolExecutor(max_workers=len(scrapers)) as pool:
        futures = [pool.submit(s.run, target) for s in scrapers]
        for fut in as_completed(futures):
            results.append(fut.result())

    fresh: list[Screening] = []
    failures: dict[str, str] = {}
    for r in results:
        if not r.success:
            failures[r.slug] = f"Circuito non disponibile: {r.name} ({r.error})."
        elif not r.screenings:
            failures[r.slug] = (
                f"Nessuna proiezione trovata per {r.name} (controlla i selettori)."
            )
        else:
            fresh.extend(r.screenings)

    _enrich(fresh)
    return _store_day(cache, target, fresh, failures)


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
    """Scrapa ogni circuito UNA sola volta ed estrae N giorni dalla risposta.

    Evita 429 rate-limit: 4-8 richieste HTTP totali invece di 4*N.
    """
    start = target_date or today()
    cache = Cache()

    # 1) Una chiamata per circuito, tutti i giorni insieme. run_all_dates ha
    #    il suo timeout rigido: questo pool non resta appeso a uno scraper.
    scrapers = [cls() for cls in ALL_SCRAPERS]
    with ThreadPoolExecutor(max_workers=len(scrapers)) as pool:
        results: list[MultiDayResult] = list(
            pool.map(lambda s: s.run_all_dates(start, days), scrapers)
        )

    # 2) Esito per circuito sull'intera finestra: zero proiezioni in N giorni
    #    vuol dire quasi sempre selettori rotti, non un cinema chiuso.
    ok: list[MultiDayResult] = []
    failures: dict[str, str] = {}
    for r in results:
        if not r.success:
            failures[r.slug] = f"Circuito non disponibile: {r.name} ({r.error})."
        elif not any(r.by_date.values()):
            failures[r.slug] = (
                f"Nessuna proiezione trovata per {r.name} nei prossimi "
                f"{days} giorni (controlla i selettori)."
            )
        else:
            ok.append(r)

    _enrich([s for r in ok for screenings in r.by_date.values() for s in screenings])

    # 3) Un snapshot per giorno, con fallback per i circuiti falliti.
    snapshots: list[CacheSnapshot] = []
    for i in range(days):
        d = start + timedelta(days=i)
        fresh = [s for r in ok for s in r.by_date.get(d, [])]
        snapshots.append(_store_day(cache, d, fresh, failures))

    logger.info(
        "Pipeline multi-giorno completata: %d giorni, %d film totali",
        days,
        sum(len(s.screenings) for s in snapshots),
    )
    return snapshots
