"""Scraper Nuovo Cinema Nosadella.

Backend: nosadella.18tickets.it (stesso template di Cineteca/Pop Up).
Il cinema ha due sale interne (Sala Berti, Sala Scalo); per ora le
manteniamo aggregate sotto il singolo cinema, il nome sala finisce
nelle note (estratto dal parser comune via _SALA_RE).
"""

from __future__ import annotations

from datetime import date

from .base import BaseScraper, Screening
from ._tickets18 import parse_day


class NosadellaScraper(BaseScraper):
    name = "Nuovo Cinema Nosadella"
    slug = "nosadella"
    base_url = "https://nosadella.18tickets.it/"

    def _fetch(self, target_date: date) -> list[Screening]:
        html = self._get(self.base_url).text
        day = parse_day(html, self.name, target_date)
        for s in day:
            s.note = (s.note + " - " if s.note else "") + "Nosadella"
        return day
