from __future__ import annotations

from web.site import _normalize_title


def test_normalize_title_accento_e_apostrofo_coincidono():
    assert _normalize_title("Dov'e' La Fiesta?") == _normalize_title("Dov’è la fiesta?")


def test_film_con_poster_diversi_ma_stesso_titolo_si_unisce():
    from datetime import UTC, date, datetime

    from database.cache import CacheSnapshot
    from scrapers.base import Screening
    from web.site import _build_film_list

    def scr(cinema: str, titolo: str, poster: str) -> Screening:
        return Screening(
            cinema=cinema, titolo=titolo, orari=["20:00"], poster_url_tmdb=poster
        )

    snapshot = CacheSnapshot(
        target_date=date(2026, 9, 20),
        updated_at=datetime(2026, 9, 20, 12, 0, tzinfo=UTC),
        screenings=[
            scr("Chaplin", "Dov'è la fiesta?", "https://i/w500/aaa.jpg"),
            scr("The Space", "Dov'e' La Fiesta?", "https://i/w500/bbb.jpg"),
        ],
        warnings=[],
    )
    films, _, _ = _build_film_list(snapshot)
    assert len(films) == 1
    assert {c["name"] for c in films[0]["cinemas"]} == {"Chaplin", "The Space"}
