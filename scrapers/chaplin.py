"""Scraper Cinema Chaplin (Bologna, Porta Saragozza).

Il sito e' un WordPress: la home elenca i film in programmazione
(articoli della categoria `in-programma`) e ogni scheda film ha un blocco
"Orari e giorni programmazione" in testo libero, ad esempio:

    Giovedi 17 settembre
    16:30-18:45-21:00
    prezzi interi 9.00 ridotti 7.00
    Lunedi 21 settembre
    Chiuso per Riposo..!!

Il testo e' scritto a mano, quindi il parser e' volutamente tollerante:
i prezzi vengono scartati e i giorni senza orari (chiusure) ignorati.
"""

from __future__ import annotations

import re
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from ._dates_it import DATE_RE, extract_times, resolve_date
from .base import BaseScraper, Screening

_HOME_URL = "https://cinemachaplin.it/"
_TICKETS_URL = "https://www.webtic.it/app/shopping/loadLocal/BO/5373"
_CINEMA = "Cinema Chaplin"
_TZ = ZoneInfo("Europe/Rome")
_PRICE_RE = re.compile(r"\bprezz\w*", re.IGNORECASE)
_TITLE_SUFFIX_RE = re.compile(r"\s+[-–|]\s+Cinema Chaplin\s*$", re.IGNORECASE)


def parse_film_links(home_html: str) -> list[str]:
    """URL delle schede dei film in programmazione (esclude 'prossimamente')."""
    soup = BeautifulSoup(home_html, "lxml")
    links: list[str] = []
    for article in soup.select("article.category-in-programma"):
        a = article.select_one("h2.df-post-title a[href]")
        href = a.get("href") if a else None
        if isinstance(href, str) and href not in links:
            links.append(href)
    return links


def parse_film_page(html: str, film_url: str, reference: date) -> dict[date, Screening]:
    """Estrae gli orari di un film, un `Screening` per ciascun giorno."""
    soup = BeautifulSoup(html, "lxml")

    og_title = soup.find("meta", property="og:title")
    raw_title = og_title.get("content", "") if og_title else ""
    titolo = _TITLE_SUFFIX_RE.sub("", str(raw_title)).strip()
    og_image = soup.find("meta", property="og:image")
    poster = str(og_image.get("content", "")) if og_image else ""

    titolo_toggle = next(
        (
            h
            for h in soup.select(".et_pb_toggle_title")
            if "orari" in h.get_text(strip=True).lower()
        ),
        None,
    )
    content = (
        titolo_toggle.find_next_sibling(class_="et_pb_toggle_content")
        if titolo_toggle
        else None
    )
    if not titolo or content is None:
        return {}

    text = content.get_text("\n")
    matches = list(DATE_RE.finditer(text))
    result: dict[date, Screening] = {}
    for i, m in enumerate(matches):
        day = resolve_date(int(m.group(1)), m.group(2), reference)
        if day is None:
            continue
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        segment = text[m.end() : end]
        price = _PRICE_RE.search(segment)
        if price:
            segment = segment[: price.start()]
        orari = extract_times(segment)
        if not orari:
            continue
        result[day] = Screening(
            cinema=_CINEMA,
            titolo=titolo,
            orari=orari,
            note="Chaplin",
            poster_url=poster,
            url=film_url,
            times_urls={t: _TICKETS_URL for t in orari},
        )
    return result


class ChaplinScraper(BaseScraper):
    name = "Cinema Chaplin"
    slug = "chaplin"

    def _fetch_pages(self) -> list[tuple[str, str]]:
        film_links = parse_film_links(self._get(_HOME_URL).text)
        with ThreadPoolExecutor(max_workers=4) as pool:
            htmls = list(pool.map(lambda u: self._get(u).text, film_links))
        return list(zip(film_links, htmls, strict=True))

    def _collect(self) -> dict[date, list[Screening]]:
        reference = datetime.now(_TZ).date()
        by_date: dict[date, list[Screening]] = defaultdict(list)
        for url, html in self._fetch_pages():
            for day, screening in parse_film_page(html, url, reference).items():
                by_date[day].append(screening)
        return by_date

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
