"""Helper condivisi per leggere date e orari scritti a mano in italiano.

Usati dagli scraper dei cinema che non hanno un sistema di ticketing
strutturato ma pubblicano la programmazione come testo libero
(es. "Giovedi 17 settembre" seguito da "16:30-18:45-21:00").
"""

from __future__ import annotations

import re
from datetime import date

MESI = {
    "gennaio": 1,
    "febbraio": 2,
    "marzo": 3,
    "aprile": 4,
    "maggio": 5,
    "giugno": 6,
    "luglio": 7,
    "agosto": 8,
    "settembre": 9,
    "ottobre": 10,
    "novembre": 11,
    "dicembre": 12,
}

_GIORNI = r"(?:lun|mar|mer|gio|ven|sab|dom)\w*"
_MESI_RE = "|".join(MESI)

# "Giovedi 17 settembre", "● domenica 20 settembre", "sab 12 ottobre"
DATE_RE = re.compile(
    rf"\b{_GIORNI}\.?\s+(\d{{1,2}})\s+({_MESI_RE})\b",
    re.IGNORECASE,
)

# Orario isolato: 16:30, 9.15, 21.00
TIME_RE = re.compile(r"(?<![\d.,€])([01]?\d|2[0-3])[:.]([0-5]\d)(?![\d])")


def resolve_date(day: int, month_name: str, reference: date) -> date | None:
    """Costruisce la data completa deducendo l'anno dal giorno di riferimento.

    I siti omettono l'anno: si usa quello di `reference`, passando all'anno
    successivo se la data risulterebbe piu' di sei mesi nel passato
    (es. riferimento a dicembre, programmazione di gennaio).
    """
    month = MESI.get(month_name.lower())
    if month is None:
        return None
    try:
        d = date(reference.year, month, day)
    except ValueError:
        return None
    if (reference - d).days > 180:
        d = d.replace(year=d.year + 1)
    return d


def extract_times(text: str) -> list[str]:
    """Estrae gli orari HH:MM (normalizzati, senza duplicati, ordinati)."""
    found = {f"{int(h):02d}:{m}" for h, m in TIME_RE.findall(text)}
    return sorted(found)
