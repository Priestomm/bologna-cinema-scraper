"""Scraper UCI Cinemas Meridiana (Bologna).

Backend JSON API di UCI Cinemas. A differenza degli altri circuiti
che usano HTML 18tickets, UCI espone un'API REST pulita che ritorna
programmazione, generi, lingue e sottotitoli in JSON strutturato.

API: GET /theatres/{slug}/programming/{YYYY-MM-DD}
Base: https://myuci---uci-backend-production-nfluwp7wga-oc.a.run.app/api
"""

from __future__ import annotations

import re
from datetime import date, timedelta

from .base import BaseScraper, Screening

_UCI_API_BASE = "https://myuci---uci-backend-production-nfluwp7wga-oc.a.run.app/api"
_UCI_THEATRE_SLUG = "uci-cinemas-meridiana-bologna"
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

        screenings: list[Screening] = []
        for movie in data:
            title = movie.get("title", "").strip()
            if not title:
                continue

            poster = movie.get("poster", "")
            genres = [g.get("name", "") for g in movie.get("genres", [])]
            genre = " / ".join(g for g in genres if g)

            for screen_group in movie.get("screens", []):
                for format_name, versions in screen_group.items():
                    for version in versions:
                        sala = version.get("screen", {}).get("name", format_name)
                        lang = version.get("language", {}).get("name", "")
                        subs = version.get("subtitles")
                        sub_name = subs.get("name", "") if subs else ""

                        note = sala
                        if lang:
                            note += f" - {lang}"
                        if sub_name:
                            note += f" / Sub {sub_name}"

                        orari: list[str] = []
                        for perf in version.get("performances", []):
                            raw = perf.get("starts_at", "")
                            m = _TIME_RE.search(raw)
                            if m:
                                t = f"{m.group(1)}:{m.group(2)}"
                                if t not in orari:
                                    orari.append(t)

                        if not orari:
                            continue

                        slug = movie.get("slug", "")
                        url_film = f"https://ucicinemas.it/film/{slug}" if slug else ""

                        screenings.append(
                            Screening(
                                cinema="UCI Cinemas",
                                titolo=title,
                                orari=sorted(orari),
                                note=note,
                                poster_url=poster,
                                genre=genre,
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
