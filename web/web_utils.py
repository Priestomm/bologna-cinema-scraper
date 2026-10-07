"""Utility condivise tra web/api.py e web/site.py.

Solo le cose che servono davvero a entrambi: l'accesso alla Cache
condivisa (un'unica istanza, letta dagli stessi path indipendentemente da
quale router gestisce la richiesta) e il parsing di una data da URL.
"""

from __future__ import annotations

from datetime import date, timedelta

from starlette.requests import Request

from config import settings
from core.pipeline import today
from database import Cache

_cache: Cache | None = None


def get_cache() -> Cache:
    """Istanza singleton della Cache. api.py e site.py importano il modulo
    (`from web import web_utils`) e chiamano `web_utils.get_cache()`, non la
    funzione direttamente: cosi' un solo `patch("web.web_utils.get_cache", ...)`
    nei test copre le letture di entrambi i router."""
    global _cache
    if _cache is None:
        _cache = Cache()
    return _cache


def parse_date(s: str) -> date:
    parts = s.split("-")
    if len(parts) != 3:
        raise ValueError
    return date(int(parts[0]), int(parts[1]), int(parts[2]))


# Finestra delle date servite dal sito: lo storico in cache e i giorni gia'
# scrapati, piu' un margine. Fuori da qui e' 404, cosi' un crawler non puo'
# generare pagine all'infinito ("/1970-01-01", "/9999-12-31", ...).
DAYS_PAST = 90
DAYS_FUTURE = 14


def in_window(d: date) -> bool:
    t = today()
    return t - timedelta(days=DAYS_PAST) <= d <= t + timedelta(days=DAYS_FUTURE)


def absolute_url(request: Request, path: str) -> str:
    """URL assoluto pubblico per `path` (che inizia con "/").

    Usa settings.public_base_url quando c'e': dietro nginx la richiesta
    arriva come http://127.0.0.1:8080 e request.url darebbe quello.
    """
    base = settings.public_base_url or str(request.base_url).rstrip("/")
    return base + path
