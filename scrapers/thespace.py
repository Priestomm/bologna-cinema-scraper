"""Scraper The Space Cinema Bologna (multisala Vue Cinemas).

Il sito e' una SPA Next.js che carica la programmazione da
`/api/microservice/showings/cinemas/{id}/films`. L'API risponde 401 senza
il token anonimo che il sito assegna via cookie alla prima visita della
pagina del cinema: la sessione `requests` lo conserva, quindi basta
visitare prima la pagina e poi chiamare l'API.

Una sola chiamata restituisce tutti i film con le sessioni dei prossimi
giorni, raggruppate per data (`showingGroups`).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any

from ._text import titlecase_it
from .base import BaseScraper, Screening

_BASE = "https://www.thespacecinema.it"
_CINEMA_PAGE = f"{_BASE}/cinema/bologna/al-cinema"
_CINEMA_ID = 1003
_API_URL = f"{_BASE}/api/microservice/showings/cinemas/{_CINEMA_ID}/films"
_CINEMA = "The Space Cinema"

# Attributi di sessione che vale la pena mostrare nella nota.
_NOTE_SPECIAL = {"INFINITY VISION", "ANTEPRIMA"}


def _session_note(attributes: list[dict[str, Any]]) -> str:
    """Nota di una sessione: lingua ed eventuali formati speciali."""
    bits: list[str] = []
    for a in attributes:
        kind, name = a.get("attributeType"), str(a.get("name", "")).strip()
        if kind == "Language" and name:
            bits.append("V.O." if name.upper() == "LINGUA ORIGINALE" else "ITA")
        elif kind == "Session_Special" and name.upper() in _NOTE_SPECIAL:
            bits.append(titlecase_it(name))
    bits.append("The Space")
    return " - ".join(bits)


def parse_films(films: list[dict[str, Any]]) -> dict[date, list[Screening]]:
    """Converte la risposta dell'API in Screening raggruppati per data."""
    grouped: dict[tuple[date, str, str], Screening] = {}
    for film in films:
        titolo = titlecase_it(str(film.get("filmTitle", "")).strip())
        if not titolo:
            continue
        genres = film.get("genres") or []
        genre = " / ".join(str(g) for g in genres if g)
        for group in film.get("showingGroups", []):
            for session in group.get("sessions", []):
                try:
                    start = datetime.fromisoformat(session["startTime"])
                except (KeyError, ValueError):
                    continue
                note = _session_note(session.get("attributes", []))
                key = (start.date(), titolo, note)
                screening = grouped.get(key)
                if screening is None:
                    screening = grouped[key] = Screening(
                        cinema=_CINEMA,
                        titolo=titolo,
                        note=note,
                        poster_url=str(film.get("posterImageSrc") or ""),
                        regista=str(film.get("director") or ""),
                        url=str(film.get("filmUrl") or ""),
                        genre=genre,
                        runtime=int(film.get("runningTime") or 0),
                    )
                hhmm = start.strftime("%H:%M")
                if hhmm not in screening.orari:
                    screening.orari.append(hhmm)
                booking = session.get("bookingUrl")
                if booking:
                    screening.times_urls[hhmm] = f"{_BASE}{booking}"

    result: dict[date, list[Screening]] = defaultdict(list)
    for (day, _, _), screening in grouped.items():
        screening.orari.sort()
        result[day].append(screening)
    return result


class TheSpaceScraper(BaseScraper):
    name = "The Space Cinema"
    slug = "thespace"

    def _collect(self) -> dict[date, list[Screening]]:
        self._get(_CINEMA_PAGE)  # assegna il token anonimo (cookie)
        films = self._get(_API_URL, headers={"Accept": "application/json"}).json()
        return parse_films(films.get("result", []))

    def _fetch(self, target_date: date) -> list[Screening]:
        return self._collect().get(target_date, [])

    def fetch_all_dates(
        self, after_date: date, max_days: int = 7
    ) -> dict[date, list[Screening]]:
        by_date = self._collect()
        return {
            after_date + timedelta(days=i): by_date.get(
                after_date + timedelta(days=i), []
            )
            for i in range(max_days)
        }
