from __future__ import annotations

from datetime import date

from scrapers._tickets18 import _extract_lang_note, parse_day
from tests.conftest import (
    MOCK_HTML_FALLBACK_DATE,
    MOCK_HTML_MULTI_MOVIE,
    MOCK_HTML_NO_SHOWTIMES,
    MOCK_HTML_ONE_MOVIE,
)


class TestExtractLangNote:
    def test_vo(self) -> None:
        assert "VO" in _extract_lang_note("Lingua: Italiano versione originale")

    def test_sub_ita(self) -> None:
        assert "Sub ITA" in _extract_lang_note("Lingua: Italiano sub ita")

    def test_sub_eng(self) -> None:
        assert "Sub ENG" in _extract_lang_note("Lingua: Giapponese sub eng")

    def test_both(self) -> None:
        result = _extract_lang_note("Versione originale sub ita")
        assert "VO" in result
        assert "Sub ITA" in result

    def test_none(self) -> None:
        assert _extract_lang_note("Lingua: Italiano") == ""


class TestParseDay:
    def test_single_movie(self, target_date: date) -> None:
        screenings = parse_day(MOCK_HTML_ONE_MOVIE, "Lumiere", target_date)
        assert len(screenings) == 1
        s = screenings[0]
        assert s.cinema == "Lumiere"
        assert s.titolo == "La grande bellezza"
        assert "15:00" in s.orari
        assert "20:30" in s.orari

    def test_multi_movie(self, target_date: date) -> None:
        screenings = parse_day(MOCK_HTML_MULTI_MOVIE, "Cineteca", target_date)
        assert len(screenings) == 2
        titoli = {s.titolo for s in screenings}
        assert "La grande bellezza" in titoli
        assert "Oppenheimer" in titoli

    def test_no_showtimes_returns_empty(self, target_date: date) -> None:
        screenings = parse_day(MOCK_HTML_NO_SHOWTIMES, "Test", target_date)
        assert screenings == []

    def test_fallback_date_parsing(self, target_date: date) -> None:
        screenings = parse_day(MOCK_HTML_FALLBACK_DATE, "Test", target_date)
        assert len(screenings) == 1
        assert screenings[0].titolo == "Film fallback"
        assert "16:00" in screenings[0].orari
        assert "19:00" in screenings[0].orari

    def test_orari_are_sorted(self, target_date: date) -> None:
        screenings = parse_day(MOCK_HTML_ONE_MOVIE, "Lumiere", target_date)
        assert screenings[0].orari == sorted(screenings[0].orari)

    def test_vo_detected(self, target_date: date) -> None:
        screenings = parse_day(MOCK_HTML_ONE_MOVIE, "Lumiere", target_date)
        assert "VO" in screenings[0].note

    def test_empty_html(self, target_date: date) -> None:
        assert parse_day("", "Test", target_date) == []

    def test_invalid_html(self, target_date: date) -> None:
        assert (
            parse_day("<html><body>nothing here</body></html>", "Test", target_date)
            == []
        )
