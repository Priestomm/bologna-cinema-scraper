"""Layer scrapers: ognuno restituisce list[Screening] per la giornata richiesta."""

from .base import BaseScraper, MultiDayResult, ScraperResult, Screening
from .chaplin import ChaplinScraper
from .cineteca import CinetecaScraper
from .circuito import CircuitoCinemaScraper
from .galliera import GallieraScraper
from .nosadella import NosadellaScraper
from .popup import PopUpCinemaScraper
from .thespace import TheSpaceScraper
from .uci import UCIScraper

ALL_SCRAPERS: list[type[BaseScraper]] = [
    CinetecaScraper,
    PopUpCinemaScraper,
    CircuitoCinemaScraper,
    NosadellaScraper,
    UCIScraper,
    ChaplinScraper,
    GallieraScraper,
    TheSpaceScraper,
]

__all__ = [
    "ALL_SCRAPERS",
    "BaseScraper",
    "ChaplinScraper",
    "CinetecaScraper",
    "CircuitoCinemaScraper",
    "GallieraScraper",
    "MultiDayResult",
    "NosadellaScraper",
    "PopUpCinemaScraper",
    "ScraperResult",
    "Screening",
    "TheSpaceScraper",
    "UCIScraper",
]
