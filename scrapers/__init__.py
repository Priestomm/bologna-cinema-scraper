"""Layer scrapers: ognuno restituisce list[Screening] per la giornata richiesta."""
from .base import BaseScraper, ScraperResult, Screening
from .cineteca import CinetecaScraper
from .circuito import CircuitoCinemaScraper
from .nosadella import NosadellaScraper
from .popup import PopUpCinemaScraper

ALL_SCRAPERS: list[type[BaseScraper]] = [
    CinetecaScraper,
    PopUpCinemaScraper,
    CircuitoCinemaScraper,
    NosadellaScraper,
]

__all__ = [
    "BaseScraper",
    "ScraperResult",
    "Screening",
    "CinetecaScraper",
    "CircuitoCinemaScraper",
    "NosadellaScraper",
    "PopUpCinemaScraper",
    "ALL_SCRAPERS",
]
