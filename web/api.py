"""API REST JSON: health check + programmazione cinematografica.

- GET /health             stato del bot
- GET /api/screenings     programmazione
- GET /api/cinemas        elenco cinema
- GET /api/cinemas/{name} film di un cinema
- GET /api/history        storico ultimi N giorni
- GET /api/stats          statistiche generali
- POST /api/refresh       forza uno scraping manuale (header X-Refresh-Token)
- GET /api/refresh/status stato del refresh manuale
"""

from __future__ import annotations

import secrets
import threading
import time
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query

from config import settings
from core.pipeline import today
from scrapers.base import Screening
from utils import get_logger
from web import web_utils

logger = get_logger("web.api")
_start_time = time.time()

router = APIRouter(tags=["api"])


# ---- health check -----------------------------------------------------


@router.api_route("/health", methods=["GET", "HEAD"])
def health() -> dict[str, Any]:
    """Stato del bot: uptime, conteggio film, avvisi."""
    try:
        snapshot = web_utils.get_cache().load(today())
        if snapshot is None:
            return {
                "status": "degraded",
                "message": "cache vuota",
                "screenings": 0,
                "warnings": 0,
                "uptime_seconds": int(time.time() - _start_time),
            }
        return {
            "status": "ok" if not snapshot.is_empty else "degraded",
            "last_updated": snapshot.updated_at.isoformat(),
            "screenings": len(snapshot.screenings),
            "warnings": len(snapshot.warnings),
            "uptime_seconds": int(time.time() - _start_time),
        }
    except Exception:
        # Il dettaglio va nei log, non a chiunque interroghi /health:
        # un'eccezione puo' contenere path, query o configurazione.
        logger.exception("Health check fallito")
        return {"status": "error"}


# ---- API endpoints ----------------------------------------------------


@router.get("/api/screenings")
def get_screenings(
    date: str | None = Query(None, description="YYYY-MM-DD, default oggi"),
) -> dict[str, Any]:
    """Programmazione per una data specifica (o oggi)."""
    if date:
        try:
            target = web_utils.parse_date(date)
        except ValueError:
            raise HTTPException(
                400, f"Formato data non valido: {date}. Usa YYYY-MM-DD."
            )
    else:
        target = today()

    snapshot = web_utils.get_cache().load(target)
    if snapshot is None:
        raise HTTPException(404, f"Nessun dato per {target.isoformat()}")

    cinemas: dict[str, list[dict]] = {}
    for s in snapshot.screenings:
        cinemas.setdefault(s.cinema, []).append(_screening_dict(s))

    return {
        "date": target.isoformat(),
        "updated_at": snapshot.updated_at.isoformat(),
        "total_screenings": len(snapshot.screenings),
        "cinemas": cinemas,
        "warnings": snapshot.warnings,
    }


@router.get("/api/cinemas")
def get_cinemas() -> list[dict[str, Any]]:
    """Elenco cinema disponibili oggi con conteggio film."""
    snapshot = web_utils.get_cache().load(today())
    if snapshot is None:
        return []

    counts: dict[str, int] = {}
    for s in snapshot.screenings:
        counts[s.cinema] = counts.get(s.cinema, 0) + 1

    return [{"cinema": c, "film_count": n} for c, n in sorted(counts.items())]


@router.get("/api/cinemas/{cinema_name}")
def get_cinema_screenings(cinema_name: str) -> dict[str, Any]:
    """Film disponibili per un cinema specifico oggi."""
    snapshot = web_utils.get_cache().load(today())
    if snapshot is None:
        raise HTTPException(404, "Nessun dato disponibile")

    films = [
        _screening_dict(s)
        for s in snapshot.screenings
        if cinema_name.lower() in s.cinema.lower()
    ]
    if not films:
        raise HTTPException(404, f"Nessun film trovato per '{cinema_name}'")

    return {
        "cinema": cinema_name,
        "date": today().isoformat(),
        "film_count": len(films),
        "screenings": films,
    }


@router.get("/api/history")
def get_history(days: int = Query(7, ge=1, le=90)) -> list[dict[str, Any]]:
    """Programmazione degli ultimi N giorni."""
    today_ = today()
    result = []
    for i in range(days):
        d = today_ - timedelta(days=i)
        snapshot = web_utils.get_cache().load(d)
        if snapshot:
            result.append(
                {
                    "date": d.isoformat(),
                    "screenings": len(snapshot.screenings),
                    "cinemas": len({s.cinema for s in snapshot.screenings}),
                    "warnings": len(snapshot.warnings),
                }
            )
    return result


@router.get("/api/stats")
def get_stats() -> dict[str, Any]:
    """Statistiche generali della cache (ultimi 90 giorni)."""
    today_ = today()
    total_screenings = 0
    total_cinemas: set[str] = set()
    days_with_data = 0
    last_updated: str | None = None

    for i in range(90):
        d = today_ - timedelta(days=i)
        snapshot = web_utils.get_cache().load(d)
        if snapshot:
            days_with_data += 1
            total_screenings += len(snapshot.screenings)
            total_cinemas.update(s.cinema for s in snapshot.screenings)
            ts = snapshot.updated_at.isoformat()
            if last_updated is None or ts > last_updated:
                last_updated = ts

    return {
        "days_with_data": days_with_data,
        "total_screenings": total_screenings,
        "unique_cinemas": len(total_cinemas),
        "cinemas": sorted(total_cinemas),
        "last_updated": last_updated,
    }


# ---- refresh -----------------------------------------------------------


# Tenuto per tutta la durata dello scraping: e' anche lo stato esposto da
# /api/refresh/status, cosi' non serve un flag separato da tenere allineato.
_refresh_lock = threading.Lock()


@router.post("/api/refresh")
def trigger_refresh(
    x_refresh_token: str | None = Header(None),
) -> dict[str, Any]:
    """Avvia uno scraping multi-giorno in background.

    Ogni chiamata colpisce i siti di tutti i circuiti: senza token chiunque
    potrebbe farci bannare per 429. Se REFRESH_TOKEN non e' configurato
    l'endpoint e' disabilitato.
    """
    if not settings.refresh_token:
        raise HTTPException(404, "Refresh manuale disabilitato")
    if not x_refresh_token or not secrets.compare_digest(
        x_refresh_token, settings.refresh_token
    ):
        raise HTTPException(401, "Token mancante o non valido")

    # acquire non bloccante: due richieste ravvicinate non possono partire
    # entrambe (il controllo e l'acquisizione sono un'unica operazione).
    if not _refresh_lock.acquire(blocking=False):
        return {"status": "already_running", "message": "Scraping già in corso"}

    def _run() -> None:
        try:
            from core.pipeline import run_multi_day_pipeline

            run_multi_day_pipeline(days=7)
            logger.info("Refresh completato")
        except Exception:
            logger.exception("Refresh fallito")
        finally:
            _refresh_lock.release()

    threading.Thread(target=_run, daemon=True).start()
    return {"status": "started", "message": "Scraping avviato"}


@router.get("/api/refresh/status")
def refresh_status() -> dict[str, Any]:
    """Stato del refresh in corso."""
    return {"in_progress": _refresh_lock.locked()}


# ---- helpers ------------------------------------------------------------


def _screening_dict(s: Screening) -> dict[str, Any]:
    return {
        "cinema": s.cinema,
        "titolo": s.titolo,
        "orari": s.orari,
        "note": s.note,
        "poster_url": s.poster_url,
        "rating": s.rating,
        "regista": s.regista,
        "url": s.url,
        "genre": s.genre,
    }
