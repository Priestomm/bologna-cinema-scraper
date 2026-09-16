"""Scraper Nuovo Cinema Nosadella.

Backend: nosadella.18tickets.it (stesso template di Cineteca/Pop Up).
Il cinema ha due sale interne (Sala Berti, Sala Scalo); per ora le
manteniamo aggregate sotto il singolo cinema, il nome sala finisce
nelle note (estratto dal parser comune via _SALA_RE).
"""

from __future__ import annotations

from ._tickets18_base import SingleTheaterScraper


class NosadellaScraper(SingleTheaterScraper):
    name = "Nuovo Cinema Nosadella"
    slug = "nosadella"
    base_url = "https://nosadella.18tickets.it/"
    label = "Nosadella"
