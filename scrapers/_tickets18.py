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
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

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
    if any(
        h in lower for h in ("v.o.", " vo ", "versione originale", "lingua originale")
    ):
        parts.append("VO")
    if (
        "sub ita" in lower
        or "sottotitoli in italiano" in lower
        or "sottotitoli italiano" in lower
    ):
        parts.append("Sub ITA")
    elif "sub eng" in lower or "sottotitoli in inglese" in lower:
        parts.append("Sub ENG")
    return " / ".join(parts)


def _extract_director(movie_div: Tag) -> str:
    """Estrae il nome del regista da <p class='movie__option'>Regia: ...</p>"""
    for opt in movie_div.find_all("p", class_="movie__option"):
        strong = opt.find("strong")
        if strong and "regia" in strong.get_text(strip=True).lower():
            # Rimuovi il prefisso "Regia:" e pulisci
            full = opt.get_text(" ", strip=True)
            regista = re.sub(r"^Regia\s*:?\s*", "", full, flags=re.I).strip()
            if regista:
                return regista
    return ""


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

    # URL pagina film
    film_url = ""
    href = title_tag.get("href", "")
    if href:
        film_url = href.strip()

    # Poster
    poster_url = ""
    poster_img = movie_div.find("img", class_="img-fluid")
    if poster_img and poster_img.get("src"):
        poster_url = poster_img["src"].strip()

    # Lingua: parsing dei paragrafi movie__option
    lingua_text = ""
    for opt in movie_div.find_all("p", class_="movie__option"):
        strong = opt.find("strong")
        if strong and "lingua" in strong.get_text(strip=True).lower():
            lingua_text = opt.get_text(" ", strip=True)
            break
    lang_note = _extract_lang_note(lingua_text)

    # Regista
    regista = _extract_director(movie_div)

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
        poster_url=poster_url,
        regista=regista,
        url=film_url,
    )


def parse_day(html: str, cinema_name: str, target: date) -> list[Screening]:
    soup = BeautifulSoup(html, "lxml")
    out: list[Screening] = []
    for movie in soup.find_all("div", class_="movie--preview"):
        screening = _extract_movie(movie, cinema_name, target)
        if screening:
            out.append(screening)
    return out


def _extract_movie_all_dates(
    movie_div: Tag,
    cinema_name: str,
    after_date: date,
    max_days: int,
) -> dict[date, Screening]:
    """Estrae un film e raggruppa gli orari per data (invece di filtrarne una)."""
    title_tag = movie_div.find("a", class_="movie__title")
    if not title_tag:
        return {}
    titolo = title_tag.get_text(" ", strip=True)
    if not titolo:
        return {}

    film_url = ""
    href = title_tag.get("href", "")
    if href:
        film_url = href.strip()

    poster_url = ""
    poster_img = movie_div.find("img", class_="img-fluid")
    if poster_img and poster_img.get("src"):
        poster_url = poster_img["src"].strip()

    lingua_text = ""
    for opt in movie_div.find_all("p", class_="movie__option"):
        strong = opt.find("strong")
        if strong and "lingua" in strong.get_text(strip=True).lower():
            lingua_text = opt.get_text(" ", strip=True)
            break
    lang_note = _extract_lang_note(lingua_text)

    regista = _extract_director(movie_div)

    # Raggruppa orari e sale per data
    orari_by_date: dict[date, list[str]] = defaultdict(list)
    sale_by_date: dict[date, list[str]] = defaultdict(list)

    cutoff = after_date + timedelta(days=max_days)

    for show in movie_div.find_all("div", class_="schedule-section-show"):
        show_text = show.get_text(" ", strip=True)
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
            d = _ms_to_local_date(ms)
            if d < after_date or d >= cutoff:
                continue
            ts = datetime.fromtimestamp(ms / 1000, tz=timezone.utc).astimezone(_TZ)
            formatted = ts.strftime("%H:%M")
            if formatted not in orari_by_date[d]:
                orari_by_date[d].append(formatted)
            if sala and sala not in sale_by_date[d]:
                sale_by_date[d].append(sala)

    if not orari_by_date:
        return {}

    result: dict[date, Screening] = {}
    for d, orari in orari_by_date.items():
        note_bits: list[str] = []
        if sale_by_date[d]:
            note_bits.append(" / ".join(sale_by_date[d]))
        if lang_note:
            note_bits.append(lang_note)
        note = " - ".join(note_bits)
        result[d] = Screening(
            cinema=cinema_name,
            titolo=titolo,
            orari=sorted(orari),
            note=note,
            poster_url=poster_url,
            regista=regista,
            url=film_url,
        )
    return result


def parse_all_dates(
    html: str,
    cinema_name: str,
    after_date: date,
    max_days: int = 7,
) -> dict[date, list[Screening]]:
    """Analizza la pagina e raggruppa i film per data.

    Restituisce solo le date in [after_date, after_date + max_days).
    """
    soup = BeautifulSoup(html, "lxml")
    by_date: dict[date, list[Screening]] = defaultdict(list)

    for movie in soup.find_all("div", class_="movie--preview"):
        for d, screening in _extract_movie_all_dates(
            movie, cinema_name, after_date, max_days
        ).items():
            by_date[d].append(screening)

    return dict(by_date)
