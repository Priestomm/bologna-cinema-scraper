"""Fasce orarie condivise da bot/formatter.py (digest Telegram) e
web/site.py (vista "Per orario" del mini-sito), cosi' i due prodotti
mostrano sempre la stessa suddivisione della giornata.
"""

from __future__ import annotations

TIMESLOTS = [
    ("🌅 Mattina", "06:00", "12:00"),
    ("☀️ Pomeriggio", "12:00", "17:00"),
    ("🌆 Sera", "17:00", "21:00"),
    ("🌙 Notte", "21:00", "27:00"),
]


def parse_time(t: str) -> int:
    """Restituisce i minuti dall'inizio del giorno (es. '14:30' -> 870)."""
    h, m = t.split(":")
    return int(h) * 60 + int(m)
