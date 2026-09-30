from __future__ import annotations

from datetime import date

from scrapers.thespace import parse_films


def _session(sid: str, start: str, lang: str, *special: str) -> dict:
    attrs = [{"attributeType": "Language", "name": lang}]
    attrs += [{"attributeType": "Session_Special", "name": s} for s in special]
    return {
        "sessionId": sid,
        "bookingUrl": f"/prenotare-il-biglietto/summary/1003/HO1/{sid}",
        "startTime": start,
        "attributes": attrs,
    }


FILMS = [
    {
        "filmTitle": "DUNE: PARTE TRE",
        "director": "Denis Villeneuve",
        "runningTime": 140,
        "genres": ["Fantascienza"],
        "filmUrl": "https://www.thespacecinema.it/film/dune",
        "posterImageSrc": "https://img/dune.jpg",
        "showingGroups": [
            {
                "sessions": [
                    _session("1", "2026-09-24T20:30:00", "ITALIANO"),
                    _session("2", "2026-09-24T17:10:00", "ITALIANO"),
                    _session("3", "2026-09-24T19:00:00", "LINGUA ORIGINALE"),
                    _session("4", "2026-09-25T21:00:00", "ITALIANO", "INFINITY VISION"),
                ]
            }
        ],
    },
    {"filmTitle": "", "showingGroups": []},
]


def test_parse_films_raggruppa_per_giorno_e_lingua():
    result = parse_films(FILMS)
    day = result[date(2026, 9, 24)]
    by_note = {s.note: s for s in day}
    assert by_note["ITA - The Space"].orari == ["17:10", "20:30"]
    assert by_note["V.O. - The Space"].orari == ["19:00"]


def test_parse_films_metadati_e_link_acquisto():
    s = parse_films(FILMS)[date(2026, 9, 24)][0]
    assert s.titolo == "Dune: Parte Tre"
    assert s.regista == "Denis Villeneuve"
    assert s.runtime == 140
    assert s.times_urls["20:30"].endswith("/summary/1003/HO1/1")


def test_parse_films_formato_speciale_nella_nota():
    (s,) = parse_films(FILMS)[date(2026, 9, 25)]
    assert s.note == "ITA - Infinity Vision - The Space"


def test_parse_films_ignora_film_senza_titolo():
    assert parse_films([{"filmTitle": " "}]) == {}
