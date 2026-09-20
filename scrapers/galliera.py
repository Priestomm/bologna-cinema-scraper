"""Scraper Cinema Teatro Galliera (Bologna, via Matteotti).

Il sito e' un WordPress senza ticketing strutturato: la programmazione
cinema e' un unico post "AGENDA SPETTACOLI ..." (categoria `cinema`) in
testo libero, ad esempio:

    ● domenica 20 settembre | promo cinema revolution
    ore 16:00 CALLE MALAGA di Maryam Touzani | prima visione
    ore 21:00 PALESTINA 36  V.O.S. | prima visione esclusiva

L'URL del post cambia a ogni stagione, quindi lo si cerca ogni volta nella
pagina di categoria. Il titolo del film e' scritto in maiuscolo subito dopo
"ore HH:MM"; il resto della riga (regista, tag) viene scartato.
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup, Tag

from ._dates_it import DATE_RE, extract_times, resolve_date
from ._text import titlecase_it
from .base import BaseScraper, Screening

_CATEGORY_URL = "https://www.cinemateatrogalliera.it/category/cinema/"
_CINEMA = "Cinema Teatro Galliera"
_TZ = ZoneInfo("Europe/Rome")

_UPPER = "A-ZÀ-ÖØ-Þ0-9"
_SHOW_RE = re.compile(
    rf"ore\s+(\d{{1,2}}[:.]\d{{2}})\s+((?:[{_UPPER}][{_UPPER}'’:!?,.&\-]*\s*)+)"
)
_VOS_RE = re.compile(r"\s*\bV\.?\s?O\.?\s?S\.?\*?\s*$")
_LABEL_RE = re.compile(r"^(?:ANTEPRIMA|PROIEZIONE SPECIALE)\s+")


def find_agenda_url(category_html: str) -> str | None:
    """URL del post con l'agenda, il primo della categoria che la nomina."""
    soup = BeautifulSoup(category_html, "lxml")
    for a in soup.select("h2.entry-title a[href]"):
        if "agenda" in a.get_text().lower():
            href = a.get("href")
            if isinstance(href, str):
                return href
    return None


def _clean_title(raw: str) -> tuple[str, bool]:
    """Ripulisce il titolo; restituisce (titolo, e' in versione originale)."""
    title = " ".join(raw.split()).strip()
    vos = bool(_VOS_RE.search(title))
    title = _VOS_RE.sub("", title)
    title = _LABEL_RE.sub("", title).strip(" -–*")
    # Il sito scrive i titoli tutti in maiuscolo: li portiamo a "Come Negli Altri".
    return titlecase_it(title), vos


def parse_agenda(html: str, reference: date) -> dict[date, list[Screening]]:
    """Estrae gli spettacoli di ogni giorno dal post dell'agenda."""
    soup = BeautifulSoup(html, "lxml")
    content = soup.select_one(".entry-content")
    if not isinstance(content, Tag):
        return {}

    # Link ai film (pagina scheda), indicizzati per titolo maiuscolo.
    film_urls: dict[str, str] = {}
    for a in content.find_all("a", href=True):
        label = " ".join(a.get_text().split()).upper()
        href = a.get("href")
        if label and isinstance(href, str) and "cinemateatrogalliera.it" in href:
            film_urls[label] = href

    for br in content.find_all("br"):
        br.replace_with("\n")
    text = content.get_text("")
    cut = text.upper().find("PROSSIMAMENTE")
    if cut != -1:
        text = text[:cut]

    matches = list(DATE_RE.finditer(text))
    grouped: dict[tuple[date, str], Screening] = {}
    for i, m in enumerate(matches):
        day = resolve_date(int(m.group(1)), m.group(2), reference)
        if day is None:
            continue
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        for show in _SHOW_RE.finditer(text[m.end() : end]):
            title, vos = _clean_title(show.group(2))
            orari = extract_times(show.group(1))
            if not title or not orari:
                continue
            key = (day, title)
            screening = grouped.get(key)
            if screening is None:
                screening = grouped[key] = Screening(
                    cinema=_CINEMA,
                    titolo=title,
                    note="Galliera",
                    url=film_urls.get(title.upper(), ""),
                )
            screening.orari = sorted({*screening.orari, *orari})
            if vos and "V.O.S." not in screening.note:
                screening.note = "V.O.S. - " + screening.note

    result: dict[date, list[Screening]] = defaultdict(list)
    for (day, _), screening in grouped.items():
        result[day].append(screening)
    return result


class GallieraScraper(BaseScraper):
    name = "Cinema Teatro Galliera"
    slug = "galliera"

    def _collect(self) -> dict[date, list[Screening]]:
        agenda_url = find_agenda_url(self._get(_CATEGORY_URL).text)
        if agenda_url is None:
            raise RuntimeError("post agenda non trovato nella categoria cinema")
        reference = datetime.now(_TZ).date()
        return parse_agenda(self._get(agenda_url).text, reference)

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
