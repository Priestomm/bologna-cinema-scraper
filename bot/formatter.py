"""Formattazione messaggi Telegram in HTML."""
from __future__ import annotations

import html
from datetime import date

from database import CacheSnapshot
from scrapers import Screening

_GIORNI = (
    "Lunedi", "Martedi", "Mercoledi", "Giovedi",
    "Venerdi", "Sabato", "Domenica",
)
_MESI = (
    "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
    "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
)

# Limite messaggio Telegram = 4096 caratteri. Tagliamo a 3900 per sicurezza
# e splittiamo su confine di cinema.
_MAX_LEN = 3900


def _format_date(d: date) -> str:
    return f"{_GIORNI[d.weekday()]} {d.day} {_MESI[d.month - 1]} {d.year}"


def _group_by_cinema(screenings: list[Screening]) -> dict[str, list[Screening]]:
    grouped: dict[str, list[Screening]] = {}
    for s in screenings:
        grouped.setdefault(s.cinema, []).append(s)
    for items in grouped.values():
        items.sort(key=lambda s: s.titolo.lower())
    return dict(sorted(grouped.items(), key=lambda kv: kv[0].lower()))


def _format_film(s: Screening) -> str:
    titolo = f"<b>{html.escape(s.titolo)}</b>"
    orari = ""
    if s.orari:
        orari = " " + " ".join(
            f"<code>{html.escape(o)}</code>" for o in s.orari
        )
    note = ""
    if s.note:
        note = f"\n   <i>{html.escape(s.note)}</i>"
    return f"- {titolo}{orari}{note}"


def render_snapshot(snapshot: CacheSnapshot) -> list[str]:
    """Restituisce uno o piu' messaggi (split se troppo lunghi)."""
    header = (
        f"<b>Programmazione cinema Bologna</b>\n"
        f"<i>{html.escape(_format_date(snapshot.target_date))}</i>\n"
        f"<i>Aggiornato: {snapshot.updated_at.strftime('%H:%M')}</i>\n"
    )

    if snapshot.is_empty and not snapshot.warnings:
        return [header + "\nNessuna proiezione disponibile per oggi."]

    grouped = _group_by_cinema(snapshot.screenings)

    sections: list[str] = []
    for cinema, films in grouped.items():
        lines = [f"\n*** {html.escape(cinema)} ***"]
        for f in films:
            lines.append(_format_film(f))
        sections.append("\n".join(lines))

    warnings_block = ""
    if snapshot.warnings:
        warning_lines = "\n".join(
            f"!!! {html.escape(w)}" for w in snapshot.warnings
        )
        warnings_block = f"\n\n<b>Avvisi</b>\n{warning_lines}"

    messages: list[str] = []
    current = header
    for section in sections:
        if len(current) + len(section) + 2 > _MAX_LEN:
            messages.append(current)
            current = section.lstrip("\n")
        else:
            current += "\n" + section
    if warnings_block:
        if len(current) + len(warnings_block) > _MAX_LEN:
            messages.append(current)
            current = warnings_block.lstrip("\n")
        else:
            current += warnings_block
    messages.append(current)
    return messages
