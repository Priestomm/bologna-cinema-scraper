"""Parser per le pagine 18tickets usate da Cineteca, Pop Up e Circuito Cinema.

Struttura osservata (giugno 2026):
- ogni film e' un `<div class="movie movie--preview">`
- titolo: `<a class="movie__title">`
- lingua/regia: `<p class="movie__option"><strong>Lingua:</strong>...`
- proiezioni: `<div class="schedule-section-show">` contenente:
    - testo "Lunedi 08/06/2026" e nome sala
    - `<a data-time="<timestamp_ms>">` con orario testuale dentro un `<li>`

Filtriamo per giorno usando `data-time` (timestamp ms in UTC dal portale,
ma in locale Europe/Rome il bot lavora con la stessa data; usiamo
l'aritmetica ms->date in fuso locale).
"""
from __future__ import annotations

import re
from datetime import date, datetime, timezone

import pytz
from bs4 import BeautifulSoup, Tag

from config import settings
from .base import Screening

_TZ = pytz.timezone(settings.timezone)
_TIME_RE = re.compile(r"\b([01]?\d|2[0-3])[:.]([0-5]\d)\b")


def _ms_to_local_date(ms: int) -> date:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).astimezone(_TZ).date()


def _extract_lang_note(text: str) -> str:
    lower = text.lower()
    parts: list[str] = []
    if any(h in lower for h in ("v.o.", " vo ", "versione originale", "lingua originale")):
        parts.append("VO")
    if "sub ita" in lower or "sottotitoli in italiano" in lower or "sottotitoli italiano" in lower:
        parts.append("Sub ITA")
    elif "sub eng" in lower or "sottotitoli in inglese" in lower:
        parts.append("Sub ENG")
    return " / ".join(parts)


def _extract_movie(
    movie_div: Tag,
    cinema_name: str,
    target: date,
) -> Screening | None:
    title_tag = movie_div.find("a", class_="movie__title")
    if not title_tag:
        return None
    titolo = title_tag.get_text(" ", strip=True)
    if not titolo:
        return None

    # Lingua: parsing dei paragrafi movie__option
    lingua_text = ""
    for opt in movie_div.find_all("p", class_="movie__option"):
        strong = opt.find("strong")
        if strong and "lingua" in strong.get_text(strip=True).lower():
            lingua_text = opt.get_text(" ", strip=True)
            break
    lang_note = _extract_lang_note(lingua_text)

    # Raccoglie tutti i blocchi orario filtrati per data target via data-time
    orari: list[str] = []
    sale: list[str] = []

    for show in movie_div.find_all("div", class_="schedule-section-show"):
        show_text = show.get_text(" ", strip=True)
        # Sala: testo dopo "Cinema " o nome esplicito
        sala_match = re.search(
            r"(Cinema\s+[A-Z][A-Za-z' ]+|Arena\s+[A-Z][A-Za-z' ]+|"
            r"Sala\s+[A-Za-z0-9]+|"
            r"Modernissimo|Lumi[eè]re|Mastroianni|Officinema|Scorsese|Cervi|"
            r"Rialto|Odeon|Europa|Roma|"
            r"Arlecchino|Bristol|Berti|Scalo|"
            r"Puccini|Sotto le Stelle)",
            show_text,
        )
        sala = sala_match.group(1).strip() if sala_match else ""

        for link in show.find_all("a", attrs={"data-time": True}):
            try:
                ms = int(link["data-time"])
            except (TypeError, ValueError):
                continue
            if _ms_to_local_date(ms) != target:
                continue
            ts = datetime.fromtimestamp(ms / 1000, tz=timezone.utc).astimezone(_TZ)
            formatted = ts.strftime("%H:%M")
            if formatted not in orari:
                orari.append(formatted)
            if sala and sala not in sale:
                sale.append(sala)

    if not orari:
        # Fallback: testo "Lunedi 08/06/2026" + orari nel testo, niente data-time
        for show in movie_div.find_all("div", class_="schedule-section-show"):
            show_text = show.get_text(" ", strip=True)
            date_pattern = re.compile(
                rf"\b{target.day:02d}[/-]{target.month:02d}([/-]{target.year})?\b"
            )
            if not date_pattern.search(show_text):
                continue
            for hh, mm in _TIME_RE.findall(show_text):
                f = f"{int(hh):02d}:{mm}"
                if f not in orari:
                    orari.append(f)

    if not orari:
        return None

    note_bits = []
    if sale:
        note_bits.append(" / ".join(sale))
    if lang_note:
        note_bits.append(lang_note)
    note = " - ".join(note_bits)

    return Screening(
        cinema=cinema_name,
        titolo=titolo,
        orari=sorted(orari),
        note=note,
    )


def parse_day(html: str, cinema_name: str, target: date) -> list[Screening]:
    soup = BeautifulSoup(html, "lxml")
    out: list[Screening] = []
    for movie in soup.find_all("div", class_="movie--preview"):
        screening = _extract_movie(movie, cinema_name, target)
        if screening:
            out.append(screening)
    return out
