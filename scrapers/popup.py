"""Scraper Pop Up Cinema.

Il sito popupcinema.it e' un redirect JavaScript verso il portale
18tickets dedicato (popupcinema.18tickets.it). Andiamo diretti sull'API
HTML del portale.

A differenza di Cineteca e Circuito Cinema, Pop Up serve tutte le sue
sale (Cinema Medica, Cinema Jolly, eventuali arene...) dalla stessa
pagina, senza sottodomini. Il parser estrae il nome sala nel campo note;
qui lo promuoviamo a `cinema` cosi' il formatter raggruppa per sala come
fa per gli altri circuiti.
"""
from __future__ import annotations

import re
from datetime import date

from .base import BaseScraper, Screening
from ._tickets18 import parse_day

# "Cinema XXX" o "Arena XXX" all'inizio del campo note (eventualmente
# seguito da " - ..." con annotazioni linguistiche).
_SALA_RE = re.compile(r"^((?:Cinema|Arena)\s+[A-Za-z][A-Za-z' ]*?)(?:\s+-\s+|$)")


class PopUpCinemaScraper(BaseScraper):
    name = "Pop Up Cinema"
    slug = "popup"
    base_url = "https://popupcinema.18tickets.it/"

    def _fetch(self, target_date: date) -> list[Screening]:
        html = self._get(self.base_url).text
        day = parse_day(html, self.name, target_date)
        for s in day:
            match = _SALA_RE.match(s.note)
            if match:
                sala = match.group(1).strip()
                # Promuovi la sala a cinema; rimuovi il duplicato dalla nota.
                s.cinema = f"Pop Up - {sala}"
                s.note = s.note[match.end():].strip()
            s.note = (s.note + " - " if s.note else "") + "Pop Up"
        return day
