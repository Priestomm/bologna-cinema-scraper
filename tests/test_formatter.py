from __future__ import annotations

from datetime import date, datetime

from database.cache import CacheSnapshot
from scrapers.base import Screening
from bot.formatter import render_snapshot, _format_date, _group_by_cinema


class TestFormatDate:
    def test_weekday(self) -> None:
        d = date(2026, 6, 8)
        result = _format_date(d)
        assert "Lunedi" in result
        assert "8" in result
        assert "giugno" in result
        assert "2026" in result

    def test_sunday(self) -> None:
        d = date(2026, 6, 14)
        result = _format_date(d)
        assert "Domenica" in result
        assert "14" in result


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
            updated_at=datetime(2026, 6, 8, 8, 0),
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
                Screening(cinema="Rialto", titolo="Parasite", orari=["18:00"], note="VO")
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
