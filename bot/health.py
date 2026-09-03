"""Server HTTP combinato: health check + REST API.

Avvia un server FastAPI su una porta dedicata (default 8080).
Include:
- GET /health             stato del bot
- GET /api/screenings     programmazione
- GET /api/cinemas        elenco cinema
- GET /api/cinemas/{name} film di un cinema
- GET /api/history        storico ultimi N giorni
- GET /api/stats          statistiche generali
"""
from __future__ import annotations

import threading
import time
from datetime import date, datetime, timedelta
from typing import Any

import pytz
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from database import Cache
from scrapers.base import Screening
from utils import get_logger

logger = get_logger("bot.server")
_TZ = pytz.timezone(settings.timezone)
_start_time = time.time()

_cache: Cache | None = None


def _get_cache() -> Cache:
    global _cache
    if _cache is None:
        _cache = Cache()
    return _cache

app = FastAPI(
    title="Cinema Bologna Bot",
    description="Health check + API REST per la programmazione cinematografica di Bologna",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


def _today() -> date:
    return datetime.now(_TZ).date()


# ---- health check -----------------------------------------------------


@app.get("/health")
def health() -> dict[str, Any]:
    """Stato del bot: uptime, conteggio film, avvisi."""
    try:
        snapshot = _get_cache().load(_today())
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
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "message": str(exc)}


# ---- API endpoints ----------------------------------------------------


@app.get("/api/screenings")
def get_screenings(
    date: str | None = Query(None, description="YYYY-MM-DD, default oggi"),
) -> dict[str, Any]:
    """Programmazione per una data specifica (o oggi)."""
    if date:
        try:
            target = _parse_date(date)
        except ValueError:
            raise HTTPException(
                400, f"Formato data non valido: {date}. Usa YYYY-MM-DD."
            )
    else:
        target = _today()

    snapshot = _get_cache().load(target)
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


@app.get("/api/cinemas")
def get_cinemas() -> list[dict[str, Any]]:
    """Elenco cinema disponibili oggi con conteggio film."""
    snapshot = _get_cache().load(_today())
    if snapshot is None:
        return []

    counts: dict[str, int] = {}
    for s in snapshot.screenings:
        counts[s.cinema] = counts.get(s.cinema, 0) + 1

    return [{"cinema": c, "film_count": n} for c, n in sorted(counts.items())]


@app.get("/api/cinemas/{cinema_name}")
def get_cinema_screenings(cinema_name: str) -> dict[str, Any]:
    """Film disponibili per un cinema specifico oggi."""
    snapshot = _get_cache().load(_today())
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
        "date": _today().isoformat(),
        "film_count": len(films),
        "screenings": films,
    }


@app.get("/api/history")
def get_history(days: int = Query(7, ge=1, le=90)) -> list[dict[str, Any]]:
    """Programmazione degli ultimi N giorni."""
    today = _today()
    result = []
    for i in range(days):
        d = today - timedelta(days=i)
        snapshot = _get_cache().load(d)
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


@app.get("/api/stats")
def get_stats() -> dict[str, Any]:
    """Statistiche generali della cache (ultimi 90 giorni)."""
    today = _today()
    total_screenings = 0
    total_cinemas: set[str] = set()
    days_with_data = 0
    last_updated: str | None = None

    for i in range(90):
        d = today - timedelta(days=i)
        snapshot = _get_cache().load(d)
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


# ---- helpers ----------------------------------------------------------


def _screening_dict(s: Screening) -> dict[str, Any]:
    return {
        "cinema": s.cinema,
        "titolo": s.titolo,
        "orari": s.orari,
        "note": s.note,
    }


def _parse_date(s: str) -> date:
    parts = s.split("-")
    if len(parts) != 3:
        raise ValueError
    return date(int(parts[0]), int(parts[1]), int(parts[2]))


# ---- server launcher --------------------------------------------------


def start_api_server() -> threading.Thread | None:
    """Avvia il server FastAPI in un thread daemon."""
    import uvicorn

    port = settings.health_port
    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=port,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    logger.info("API server in ascolto su http://0.0.0.0:%d", port)
    return thread
