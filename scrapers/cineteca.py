"""Scraper Cineteca di Bologna.

Backend: cinetecabologna.18tickets.it. La programmazione del giorno e'
distribuita sui sottodomini delle due sale (Lumiere e Modernissimo);
il root mostra solo "in arrivo" e link generici, quindi scrapiamo i
sottodomini in parallelo.
"""

from __future__ import annotations

from typing import ClassVar

from ._tickets18_base import MultiTheaterScraper


class CinetecaScraper(MultiTheaterScraper):
    name = "Cineteca di Bologna"
    slug = "cineteca"
    label = "Cineteca"
    theaters: ClassVar[dict[str, str]] = {
        "Cineteca - Lumiere": "https://lumiere.cinetecabologna.18tickets.it/",
        "Cineteca - Modernissimo": "https://modernissimo.cinetecabologna.18tickets.it/",
    }
