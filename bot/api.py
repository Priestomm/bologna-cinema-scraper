"""REST API per la programmazione cinematografica.

Endpoints:
  GET /api/screenings          programmazione oggi (o ?date=YYYY-MM-DD)
  GET /api/cinemas             elenco cinema con conteggio film
  GET /api/cinemas/{cinema}    film di un cinema specifico
  GET /api/history             ultimi N giorni (?days=7)
  GET /api/stats               statistiche generali
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pytz
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from database import Cache
from scrapers.base import Screening

_TZ = pytz.timezone(settings.timezone)
_cache = Cache()

app = FastAPI(
    title="Cinema Bologna API",
    description="API REST per la programmazione cinematografica di Bologna",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


def _today() -> date:
    from datetime import datetime

    return datetime.now(_TZ).date()


def _screening_dict(s: Screening) -> dict[str, Any]:
    return {
        "cinema": s.cinema,
        "titolo": s.titolo,
        "orari": s.orari,
        "note": s.note,
    }


@app.get("/api/screenings")
def get_screenings(
    date: str | None = Query(None, description="YYYY-MM-DD, default oggi"),
) -> dict[str, Any]:
    """Restituisce la programmazione per una data."""
    if date:
        try:
            target = _parse_date(date)
        except ValueError:
            raise HTTPException(400, f"Formato data non valido: {date}. Usa YYYY-MM-DD.")
    else:
        target = _today()

    snapshot = _cache.load(target)
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
    """Elenco tutti i cinema disponibili oggi con conteggio film."""
    snapshot = _cache.load(_today())
    if snapshot is None:
        return []

    counts: dict[str, int] = {}
    for s in snapshot.screenings:
        counts[s.cinema] = counts.get(s.cinema, 0) + 1

    return [{"cinema": c, "film_count": n} for c, n in sorted(counts.items())]


@app.get("/api/cinemas/{cinema_name}")
def get_cinema_screenings(cinema_name: str) -> dict[str, Any]:
    """Film disponibili per un cinema specifico oggi."""
    snapshot = _cache.load(_today())
    if snapshot is None:
        raise HTTPException(404, "Nessun dato disponibile")

    films = [_screening_dict(s) for s in snapshot.screenings if cinema_name.lower() in s.cinema.lower()]
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
        snapshot = _cache.load(d)
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
    """Statistiche generali della cache."""
    today = _today()
    total_screenings = 0
    total_cinemas: set[str] = set()
    days_with_data = 0
    last_updated: str | None = None

    for i in range(90):
        d = today - timedelta(days=i)
        snapshot = _cache.load(d)
        if snapshot:
            days_with_data += 1
            total_screenings += len(snapshot.screenings)
            total_cinemas.update(s.cinema for s in snapshot.screenings)
            if last_updated is None or snapshot.updated_at.isoformat() > last_updated:
                last_updated = snapshot.updated_at.isoformat()

    return {
        "days_with_data": days_with_data,
        "total_screenings": total_screenings,
        "unique_cinemas": len(total_cinemas),
        "cinemas": sorted(total_cinemas),
        "last_updated": last_updated,
    }


def _parse_date(s: str) -> date:
    parts = s.split("-")
    if len(parts) != 3:
        raise ValueError
    return date(int(parts[0]), int(parts[1]), int(parts[2]))
