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

from ._tickets18_base import SingleTheaterScraper
from .base import Screening

# "Cinema XXX" o "Arena XXX" all'inizio del campo note (eventualmente
# seguito da " - ..." con annotazioni linguistiche).
_SALA_RE = re.compile(r"^((?:Cinema|Arena)\s+[A-Za-z][A-Za-z' ]*?)(?:\s+-\s+|$)")


class PopUpCinemaScraper(SingleTheaterScraper):
    name = "Pop Up Cinema"
    slug = "popup"
    base_url = "https://popupcinema.18tickets.it/"
    label = "Pop Up"

    def _post_process(self, screenings: list[Screening]) -> None:
        for s in screenings:
            match = _SALA_RE.match(s.note)
            if match:
                sala = match.group(1).strip()
                # Promuovi la sala a cinema; rimuovi il duplicato dalla nota.
                s.cinema = f"Pop Up - {sala}"
                s.note = s.note[match.end() :].strip()
