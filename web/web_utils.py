"""Utility condivise tra web/api.py e web/site.py.

Solo le due cose che servono davvero a entrambi: l'accesso alla Cache
condivisa (un'unica istanza, letta dagli stessi path indipendentemente da
quale router gestisce la richiesta) e il parsing di una data da URL.
"""

from __future__ import annotations

from datetime import date

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
