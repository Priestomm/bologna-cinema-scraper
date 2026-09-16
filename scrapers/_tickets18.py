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
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

import pytz
from bs4 import BeautifulSoup, Tag

from config import settings

from .base import Screening

_TZ = pytz.timezone(settings.timezone)
_TIME_RE = re.compile(r"\b([01]?\d|2[0-3])[:.]([0-5]\d)\b")
_SALA_RE = re.compile(
    r"(Cinema\s+[A-Z][A-Za-z' ]+|Arena\s+[A-Z][A-Za-z' ]+|"
    r"Sala\s+[A-Za-z0-9]+|"
    r"Modernissimo|Lumi[eè]re|Mastroianni|Officinema|Scorsese|Cervi|"
    r"Rialto|Odeon|Europa|Roma|"
    r"Arlecchino|Bristol|Berti|Scalo|"
    r"Puccini|Sotto le Stelle)"
)


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
            regista = re.sub(r"^Regia\s*:?\s*", "", full, flags=re.IGNORECASE).strip()
            if regista:
                return regista
    return ""


@dataclass
class _MovieMeta:
    """Metadati del film indipendenti dalla data (titolo, poster, lingua...)."""

    titolo: str
    film_url: str
    poster_url: str
    lang_note: str
    regista: str


def _extract_movie_meta(movie_div: Tag) -> _MovieMeta | None:
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

    return _MovieMeta(
        titolo=titolo,
        film_url=film_url,
        poster_url=poster_url,
        lang_note=_extract_lang_note(lingua_text),
        regista=_extract_director(movie_div),
    )


def _extract_movie_all_dates(
    movie_div: Tag,
    cinema_name: str,
    after_date: date,
    max_days: int,
) -> dict[date, Screening]:
    """Estrae un film e raggruppa gli orari per data nell'intervallo richiesto."""
    meta = _extract_movie_meta(movie_div)
    if meta is None:
        return {}

    # Raggruppa orari e sale per data, via data-time (timestamp ms UTC)
    orari_by_date: dict[date, list[str]] = defaultdict(list)
    sale_by_date: dict[date, list[str]] = defaultdict(list)
    times_urls_by_date: dict[date, dict[str, str]] = defaultdict(dict)

    cutoff = after_date + timedelta(days=max_days)
    shows = movie_div.find_all("div", class_="schedule-section-show")

    for show in shows:
        show_text = show.get_text(" ", strip=True)
        sala_match = _SALA_RE.search(show_text)
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
            href = link.get("href", "")
            if href and formatted not in times_urls_by_date[d]:
                clean_url = href.strip().split("#")[0]
                times_urls_by_date[d][formatted] = f"{clean_url}#{d.isoformat()}"

    if not orari_by_date:
        # Fallback: nessun data-time, prova a leggere "gg/mm" + orari dal testo
        # per ciascuna data candidata nell'intervallo richiesto.
        for show in shows:
            show_text = show.get_text(" ", strip=True)
            sala_match = _SALA_RE.search(show_text)
            sala = sala_match.group(1).strip() if sala_match else ""

            for i in range(max_days):
                candidate = after_date + timedelta(days=i)
                date_pattern = re.compile(
                    rf"\b{candidate.day:02d}[/-]{candidate.month:02d}"
                    rf"([/-]{candidate.year})?\b"
                )
                if not date_pattern.search(show_text):
                    continue
                for hh, mm in _TIME_RE.findall(show_text):
                    formatted = f"{int(hh):02d}:{mm}"
                    if formatted not in orari_by_date[candidate]:
                        orari_by_date[candidate].append(formatted)
                if sala and sala not in sale_by_date[candidate]:
                    sale_by_date[candidate].append(sala)

    if not orari_by_date:
        return {}

    result: dict[date, Screening] = {}
    for d, orari in orari_by_date.items():
        note_bits: list[str] = []
        if sale_by_date[d]:
            note_bits.append(" / ".join(sale_by_date[d]))
        if meta.lang_note:
            note_bits.append(meta.lang_note)
        sorted_orari = sorted(orari)
        urls = times_urls_by_date.get(d, {})
        result[d] = Screening(
            cinema=cinema_name,
            titolo=meta.titolo,
            orari=sorted_orari,
            note=" - ".join(note_bits),
            poster_url=meta.poster_url,
            regista=meta.regista,
            url=meta.film_url,
            times_urls={t: urls[t] for t in sorted_orari if t in urls},
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


def parse_day(html: str, cinema_name: str, target: date) -> list[Screening]:
    """Analizza la pagina e restituisce solo le proiezioni del giorno *target*."""
    return parse_all_dates(html, cinema_name, target, max_days=1).get(target, [])
