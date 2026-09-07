"""Scraper UCI Cinemas Meridiana (Bologna).

Backend JSON API di UCI Cinemas. A differenza degli altri circuiti
che usano HTML 18tickets, UCI espone un'API REST pulita che ritorna
programmazione, generi, lingue e sottotitoli in JSON strutturato.

API: GET /theatres/{slug}/programming/{YYYY-MM-DD}
Base: https://myuci---uci-backend-production-nfluwp7wga-oc.a.run.app/api
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, timedelta

from .base import BaseScraper, Screening

_UCI_API_BASE = "https://myuci---uci-backend-production-nfluwp7wga-oc.a.run.app/api"
_UCI_THEATRE_SLUG = "uci-cinemas-meridiana-bologna"
_UCI_CINEMA_PAGE = "https://ucicinemas.it/cinema/uci-cinemas-meridiana-bologna"
_TIME_RE = re.compile(r"(\d{2}):(\d{2})")


class UCIScraper(BaseScraper):
    name = "UCI Cinemas"
    slug = "uci"

    def _fetch(self, target_date: date) -> list[Screening]:
        screenings = self._fetch_day(target_date)
        for s in screenings:
            s.note = (s.note + " - " if s.note else "") + "UCI"
        return screenings

    def _fetch_day(self, target_date: date) -> list[Screening]:
        url = (
            f"{_UCI_API_BASE}/theatres/{_UCI_THEATRE_SLUG}"
            f"/programming/{target_date.isoformat()}"
        )
        resp = self._get(url, headers={"Accept": "application/json"})
        data = resp.json().get("data", [])

        # Raggruppa per film: tutti gli orari e formati insieme
        films: dict[str, dict] = {}
        for movie in data:
            title = movie.get("title", "").strip()
            if not title:
                continue

            if title not in films:
                poster = movie.get("poster", "")
                genres = [g.get("name", "") for g in movie.get("genres", [])]
                genre = " / ".join(g for g in genres if g)
                slug = movie.get("slug", "")
                films[title] = {
                    "poster": poster,
                    "genre": genre,
                    "slug": slug,
                    "formats": defaultdict(list),
                    "orari": [],
                }

            film = films[title]

            for screen_group in movie.get("screens", []):
                for format_name, versions in screen_group.items():
                    for version in versions:
                        sala = version.get("screen", {}).get("name", format_name)
                        lang = version.get("language", {}).get("name", "")
                        subs = version.get("subtitles")
                        sub_name = subs.get("name", "") if subs else ""

                        fmt_key = sala
                        if lang:
                            fmt_key += f" - {lang}"
                        if sub_name:
                            fmt_key += f" / Sub {sub_name}"

                        orari_raw: list[str] = []
                        for perf in version.get("performances", []):
                            raw = perf.get("starts_at", "")
                            m = _TIME_RE.search(raw)
                            if m:
                                t = f"{m.group(1)}:{m.group(2)}"
                                if t not in orari_raw:
                                    orari_raw.append(t)

                        film["formats"][fmt_key].extend(orari_raw)
                        film["orari"].extend(orari_raw)

        # Costruisci Screening unificati
        screenings: list[Screening] = []
        for title, info in films.items():
            if not info["orari"]:
                continue

            # Unisci formati nella nota (es. "XL - ITA / 2D - ITA")
            note_parts = list(info["formats"].keys())
            note = " / ".join(note_parts) if note_parts else ""

            url_film = (
                f"{_UCI_CINEMA_PAGE}?film={info['slug']}"
                if info["slug"]
                else _UCI_CINEMA_PAGE
            )

            screenings.append(
                Screening(
                    cinema="UCI Cinemas",
                    titolo=title,
                    orari=sorted(set(info["orari"])),
                    note=note,
                    poster_url=info["poster"],
                    genre=info["genre"],
                    url=url_film,
                )
            )

        return screenings

    def fetch_all_dates(
        self, after_date: date, max_days: int = 7
    ) -> dict[date, list[Screening]]:
        result: dict[date, list[Screening]] = {}
        for i in range(max_days):
            d = after_date + timedelta(days=i)
            screenings = self._fetch_day(d)
            for s in screenings:
                s.note = (s.note + " - " if s.note else "") + "UCI"
            result[d] = screenings
        return result
