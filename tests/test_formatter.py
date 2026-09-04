from __future__ import annotations

from datetime import date, datetime, timezone

from bot.formatter import (
    _clean_title,
    _format_date,
    _format_note,
    _group_by_cinema,
    _group_by_timeslot,
    render_snapshot,
)
from database.cache import CacheSnapshot
from scrapers.base import Screening


class TestFormatDate:
    def test_weekday(self) -> None:
        d = date(2026, 6, 8)
        result = _format_date(d)
        assert "Lunedì" in result
        assert "8" in result
        assert "giugno" in result
        assert "2026" in result

    def test_sunday(self) -> None:
        d = date(2026, 6, 14)
        result = _format_date(d)
        assert "Domenica" in result
        assert "14" in result


class TestCleanTitle:
    def test_all_caps_converted_to_title_case(self) -> None:
        assert _clean_title("SILENT FRIEND") == "Silent Friend"

    def test_strip_original_version_suffixes(self) -> None:
        assert _clean_title("ODISSEA - V. O.") == "Odissea"
        assert _clean_title("L'HANGAR ROSSO - ORIGINAL VERSION") == "L'Hangar Rosso"
        assert _clean_title("CAMP MIASMA - VERSIONE ORIGINALE") == "Camp Miasma"

    def test_strip_original_version_prefix(self) -> None:
        assert (
            _clean_title("ORIGINAL VERSION: TONY - DIARIO DI UN GIOVANE CUOCO")
            == "Tony - Diario Di Un Giovane Cuoco"
        )

    def test_preserves_roman_numerals(self) -> None:
        assert (
            _clean_title("IL SIGNORE DEGLI ANELLI - PARTE II")
            == "Il Signore Degli Anelli - Parte II"
        )


class TestFormatNote:
    def test_removes_redundant_cinema_names(self) -> None:
        assert _format_note("Cinema Lumiere - Cineteca", "Cineteca - Lumiere") == ""
        assert _format_note("Pop Up", "Pop Up - Cinema Medica") == ""

    def test_extracts_vo_and_sub(self) -> None:
        assert (
            _format_note(
                "Cinema Modernissimo - VO / Sub ITA - Cineteca",
                "Cineteca - Modernissimo",
            )
            == "🔤 VO · 🇮🇹 Sub"
        )

    def test_extracts_specific_room(self) -> None:
        assert (
            _format_note("Sala Mastroianni - VO - Cineteca", "Cineteca - Lumiere")
            == "🔤 VO  •  🏛️ Sala Mastroianni"
        )


class TestGroupByCinema:
    def test_groups(self, sample_screenings: list[Screening]) -> None:
        grouped = _group_by_cinema(sample_screenings)
        assert "Cineteca - Lumiere" in grouped
        assert "Cineteca - Modernissimo" in grouped
        assert "Rialto" in grouped
        assert len(grouped["Rialto"]) == 2

    def test_sorts_by_title(self) -> None:
        screenings = [
            Screening(cinema="X", titolo="Zebra", orari=["10:00"]),
            Screening(cinema="X", titolo="Alpha", orari=["10:00"]),
            Screening(cinema="X", titolo="Mamma", orari=["10:00"]),
        ]
        grouped = _group_by_cinema(screenings)
        titles = [s.titolo for s in grouped["X"]]
        assert titles == ["Alpha", "Mamma", "Zebra"]

    def test_sorts_cinemas_alphabetically(self) -> None:
        screenings = [
            Screening(cinema="Zebra", titolo="Film", orari=["10:00"]),
            Screening(cinema="Alpha", titolo="Film", orari=["10:00"]),
        ]
        grouped = _group_by_cinema(screenings)
        assert list(grouped.keys()) == ["Alpha", "Zebra"]


class TestRenderSnapshot:
    def _snapshot(
        self,
        screenings: list[Screening] | None = None,
        warnings: list[str] | None = None,
    ) -> CacheSnapshot:
        return CacheSnapshot(
            target_date=date(2026, 6, 8),
            updated_at=datetime(2026, 6, 8, 8, 0, tzinfo=timezone.utc),
            screenings=screenings or [],
            warnings=warnings or [],
        )

    def test_empty_snapshot(self) -> None:
        snap = self._snapshot()
        msgs = render_snapshot(snap)
        assert len(msgs) == 1
        assert "Nessuna proiezione" in msgs[0]

    def test_single_message_within_limit(self) -> None:
        snap = self._snapshot(
            screenings=[
                Screening(
                    cinema="Rialto", titolo="Parasite", orari=["18:00"], note="VO"
                )
            ]
        )
        msgs = render_snapshot(snap)
        assert len(msgs) == 1
        assert "Parasite" in msgs[0]
        assert "Rialto" in msgs[0]

    def test_warnings_present(self) -> None:
        snap = self._snapshot(warnings=["Circuito non disponibile: Rialto (timeout)"])
        msgs = render_snapshot(snap)
        assert any("Avvisi" in m for m in msgs)
        assert any("Rialto" in m for m in msgs)

    def test_html_escaping(self) -> None:
        snap = self._snapshot(
            screenings=[
                Screening(
                    cinema="Test <script>",
                    titolo="Film <b>bold</b>",
                    orari=["10:00"],
                )
            ]
        )
        msgs = render_snapshot(snap)
        full = "\n".join(msgs)
        assert "<script>" not in full
        assert "&lt;script&gt;" in full

    def test_long_list_splits(self) -> None:
        screenings = [
            Screening(
                cinema=f"Cinema {i:03d}",
                titolo=f"Film {i:03d}",
                orari=["10:00"],
            )
            for i in range(100)
        ]
        snap = self._snapshot(screenings=screenings)
        msgs = render_snapshot(snap)
        assert len(msgs) > 1
        for m in msgs:
            assert len(m) <= 3900


class TestGroupByTimeslot:
    def test_film_appears_in_correct_slot(self) -> None:
        screenings = [
            Screening(cinema="Rialto", titolo="Film Mattina", orari=["10:00"], note=""),
            Screening(cinema="Rialto", titolo="Film Sera", orari=["19:30"], note=""),
        ]
        grouped = _group_by_timeslot(screenings)
        assert "🌅 Mattina" in grouped
        assert "🌆 Sera" in grouped
        assert "Film Mattina" in [s.titolo for s in grouped["🌅 Mattina"]["Rialto"]]
        assert "Film Sera" in [s.titolo for s in grouped["🌆 Sera"]["Rialto"]]

    def test_film_with_multiple_times_in_multiple_slots(self) -> None:
        screenings = [
            Screening(
                cinema="Rialto",
                titolo="Film Completo",
                orari=["10:00", "15:00", "19:00", "22:00"],
                note="",
            ),
        ]
        grouped = _group_by_timeslot(screenings)
        slots_with_film = [
            slot
            for slot, cinemas in grouped.items()
            if any(
                s.titolo == "Film Completo" for films in cinemas.values() for s in films
            )
        ]
        assert len(slots_with_film) == 4

    def test_empty_slots_excluded(self) -> None:
        screenings = [
            Screening(cinema="Rialto", titolo="Film Sera", orari=["19:00"], note=""),
        ]
        grouped = _group_by_timeslot(screenings)
        assert "🌅 Mattina" not in grouped
        assert "☀️ Pomeriggio" not in grouped
        assert "🌙 Notte" not in grouped

    def test_sorts_by_cinema_then_title(self) -> None:
        screenings = [
            Screening(cinema="B", titolo="Z Film", orari=["10:00"]),
            Screening(cinema="A", titolo="A Film", orari=["10:00"]),
            Screening(cinema="A", titolo="M Film", orari=["10:00"]),
        ]
        grouped = _group_by_timeslot(screenings)
        assert list(grouped["🌅 Mattina"].keys()) == ["A", "B"]
        titles = [s.titolo for s in grouped["🌅 Mattina"]["A"]]
        assert titles == ["A Film", "M Film"]


class TestRenderTimeslot:
    def _snapshot(
        self,
        screenings: list[Screening] | None = None,
        warnings: list[str] | None = None,
    ) -> CacheSnapshot:
        return CacheSnapshot(
            target_date=date(2026, 6, 8),
            updated_at=datetime(2026, 6, 8, 8, 0, tzinfo=timezone.utc),
            screenings=screenings or [],
            warnings=warnings or [],
        )

    def test_timeslot_mode_header(self) -> None:
        snap = self._snapshot(
            screenings=[
                Screening(cinema="Rialto", titolo="Film", orari=["19:00"], note="")
            ]
        )
        msgs = render_snapshot(snap, mode="timeslot")
        assert len(msgs) == 1
        assert "🌆 Sera" in msgs[0]

    def test_timeslot_empty_snapshot(self) -> None:
        snap = self._snapshot()
        msgs = render_snapshot(snap, mode="timeslot")
        assert len(msgs) == 1
        assert "Nessuna proiezione" in msgs[0]

    def test_timeslot_cinema_label_inline(self) -> None:
        snap = self._snapshot(
            screenings=[
                Screening(
                    cinema="Rialto", titolo="Parasite", orari=["18:00"], note="VO"
                )
            ]
        )
        msgs = render_snapshot(snap, mode="timeslot")
        full = msgs[0]
        assert "Rialto" in full
        assert "Parasite" in full

    def test_timeslot_long_list_splits(self) -> None:
        screenings = [
            Screening(
                cinema=f"Cinema {i:03d}",
                titolo=f"Film {i:03d}",
                orari=["19:00"],
            )
            for i in range(100)
        ]
        snap = self._snapshot(screenings=screenings)
        msgs = render_snapshot(snap, mode="timeslot")
        assert len(msgs) > 1
        for m in msgs:
            assert len(m) <= 3900
