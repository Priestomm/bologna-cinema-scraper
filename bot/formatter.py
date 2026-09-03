"""Formattazione messaggi Telegram in HTML."""

from __future__ import annotations

import html
from datetime import date

from database import CacheSnapshot
from scrapers import Screening

_GIORNI = (
    "Lunedì",
    "Martedì",
    "Mercoledì",
    "Giovedì",
    "Venerdì",
    "Sabato",
    "Domenica",
)
_MESI = (
    "gennaio",
    "febbraio",
    "marzo",
    "aprile",
    "maggio",
    "giugno",
    "luglio",
    "agosto",
    "settembre",
    "ottobre",
    "novembre",
    "dicembre",
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


def _format_orari(orari: list[str]) -> str:
    if not orari:
        return ""
    return "  ".join(f"<code>{html.escape(o)}</code>" for o in orari)


def _format_note(note: str) -> str:
    if not note:
        return ""
    tags: list[str] = []
    lower = note.lower()
    if "vo" in lower:
        tags.append("🔤 VO")
    if "sub ita" in lower:
        tags.append("🇮🇹 Sub")
    elif "sub eng" in lower:
        tags.append("🇬🇧 Sub")
    # Sala / cinema info (ultima parte della nota)
    parts = [p.strip() for p in note.split(" - ") if p.strip()]
    sala = (
        parts[-1]
        if parts and not any(kw in parts[-1].lower() for kw in ("vo", "sub"))
        else ""
    )
    if tags:
        return " · ".join(tags) + (f"  •  <i>{html.escape(sala)}</i>" if sala else "")
    return f"<i>{html.escape(note)}</i>" if note else ""


def _format_film(s: Screening) -> str:
    titolo = f"<b>{html.escape(s.titolo)}</b>"
    orari = _format_orari(s.orari)
    note = _format_note(s.note)

    line1 = f"  ▸ {titolo}"
    if orari:
        line1 += f"  {orari}"
    if note:
        line1 += f"\n     {note}"
    return line1


def render_snapshot(snapshot: CacheSnapshot) -> list[str]:
    """Restituisce uno o piu' messaggi (split se troppo lunghi)."""
    header = (
        f"🎬 <b>Programmazione Cinema Bologna</b>\n"
        f"📅 {_format_date(snapshot.target_date)}\n"
        f"🔄 Aggiornato alle {snapshot.updated_at.strftime('%H:%M')}"
    )

    if snapshot.is_empty and not snapshot.warnings:
        return [header + "\n\n_Nessuna proiezione disponibile per oggi._"]

    grouped = _group_by_cinema(screenings=snapshot.screenings)
    cinema_count = len(grouped)
    film_count = len(snapshot.screenings)

    header += f"\n📊 {film_count} film  •  {cinema_count} sale"

    sections: list[str] = []
    for cinema, films in grouped.items():
        film_count_cinema = len(films)
        lines = [
            f"\n<b>📍 {html.escape(cinema)}</b>  <i>({film_count_cinema})</i>",
            "",
        ]
        for f in films:
            lines.append(_format_film(f))
        sections.append("\n".join(lines))

    warnings_block = ""
    if snapshot.warnings:
        warning_lines = "\n".join(f"  ⚠️ {html.escape(w)}" for w in snapshot.warnings)
        warnings_block = f"\n\n<b>⚠️ Avvisi</b>\n{warning_lines}"

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
