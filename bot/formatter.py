"""Formattazione messaggi Telegram in HTML."""

from __future__ import annotations

import html
import re
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


def _title_case_word(match: re.Match[str]) -> str:
    word = match.group(0)
    # Numeri romani o risoluzioni come 4K, 3D
    if re.match(r"^(?:I{2,3}|IV|VI{0,3}|IX|X{1,3}|\d+[a-zA-Z]*)$", word):
        return word.upper()
    return word.capitalize()


def _clean_title(titolo: str) -> str:
    """Pulisce il titolo rimuovendo suffissi/prefissi ridondanti e normalizza il casing."""
    cleaned = titolo.strip()

    # Rimuove prefissi e suffissi tipici della versione originale / lingua
    cleaned = re.sub(
        r"^(?:original version|versione originale)\s*:\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"\s*-\s*(?:v\.?\s*o\.?|original version|versione originale|sub\s*ita|sub\s*eng)$",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = cleaned.strip(" -:")

    # Se tutto maiuscolo, applica Title Case intelligente preservando apostrofi e simboli
    if cleaned.isupper():
        cleaned = re.sub(r"[a-zA-ZÀ-ÖØ-öø-ÿ]+", _title_case_word, cleaned)

    return cleaned


_TIMESLOTS = [
    ("🌅 Mattina", "06:00", "12:00"),
    ("☀️ Pomeriggio", "12:00", "17:00"),
    ("🌆 Sera", "17:00", "21:00"),
    ("🌙 Notte", "21:00", "27:00"),
]


def _parse_time(t: str) -> int:
    """Restituisce i minuti dall'inizio del giorno (es. '14:30' -> 870)."""
    h, m = t.split(":")
    return int(h) * 60 + int(m)


def _timeslot_label() -> str:
    return " · ".join(f"{name}" for name, _, _ in _TIMESLOTS)


def _assign_slot(orari: list[str]) -> int:
    """Restituisce l'indice della prima fascia oraria trovata, o 0 se vuoto."""
    for o in orari:
        minutes = _parse_time(o)
        for i, (_, start, end) in enumerate(_TIMESLOTS):
            if _parse_time(start) <= minutes < _parse_time(end):
                return i
    return 0


def _group_by_timeslot(
    screenings: list[Screening],
) -> dict[str, dict[str, list[Screening]]]:
    """Raggruppa per fascia oraria, poi per cinema. Ogni film appare in ogni
    fascia che contiene almeno uno dei suoi orari."""
    result: dict[str, dict[str, list[Screening]]] = {
        name: {} for name, _, _ in _TIMESLOTS
    }
    for s in screenings:
        assigned: set[int] = set()
        for o in s.orari:
            minutes = _parse_time(o)
            for i, (_, start, end) in enumerate(_TIMESLOTS):
                if i in assigned:
                    continue
                if _parse_time(start) <= minutes < _parse_time(end):
                    result[_TIMESLOTS[i][0]].setdefault(s.cinema, []).append(s)
                    assigned.add(i)
    # Ordina film per titolo dentro ogni cinema, e cinema per nome
    for slot_data in result.values():
        for cinema in slot_data:
            slot_data[cinema].sort(key=lambda s: _clean_title(s.titolo).lower())
    return {
        k: dict(sorted(v.items(), key=lambda kv: kv[0].lower()))
        for k, v in result.items()
        if v
    }


def _group_by_cinema(screenings: list[Screening]) -> dict[str, list[Screening]]:
    grouped: dict[str, list[Screening]] = {}
    for s in screenings:
        grouped.setdefault(s.cinema, []).append(s)
    for items in grouped.values():
        items.sort(key=lambda s: _clean_title(s.titolo).lower())
    return dict(sorted(grouped.items(), key=lambda kv: kv[0].lower()))


def _format_orari(orari: list[str]) -> str:
    if not orari:
        return ""
    return " · ".join(f"<code>{html.escape(o)}</code>" for o in orari)


def _format_note(note: str, cinema_name: str = "") -> str:
    if not note:
        return ""

    lower = note.lower()
    tags: list[str] = []

    if any(
        k in lower for k in ("vo", "v.o.", "versione originale", "original version")
    ):
        tags.append("🔤 VO")
    if "sub ita" in lower or "sottotitoli in italiano" in lower:
        tags.append("🇮🇹 Sub")
    elif "sub eng" in lower or "sottotitoli in inglese" in lower:
        tags.append("🇬🇧 Sub")

    # Filtra nomi generici e ridondanti del circuito/cinema
    ignore_tokens = {
        "cineteca",
        "circuito cinema",
        "circuito",
        "pop up",
        "nosadella",
        "cinema lumiere",
        "cinema modernissimo",
        "modernissimo",
        "lumiere",
        "rialto",
        "odeon",
        "europa",
        "roma",
        "roma d'azeglio",
        "cinema jolly",
        "cinema medica",
        "cinema arlecchino",
        "cinema nosadella",
    }
    if cinema_name:
        ignore_tokens.add(cinema_name.lower())
        for part in re.split(r"[\s\-]+", cinema_name.lower()):
            if len(part) > 2:
                ignore_tokens.add(part)

    parts = [p.strip() for p in re.split(r"\s*[-/]\s*", note) if p.strip()]
    specific_room = ""
    for p in parts:
        p_lower = p.lower()
        if any(kw in p_lower for kw in ("vo", "sub", "versione", "lingua", "original")):
            continue
        if p_lower in ignore_tokens:
            continue
        if re.search(r"\b(sala|arena)\b", p_lower):
            specific_room = p
            break

    elements: list[str] = []
    if tags:
        elements.append(" · ".join(tags))
    if specific_room:
        elements.append(f"🏛️ {specific_room}")

    return "  •  ".join(elements)


def _format_film(s: Screening) -> str:
    titolo_clean = _clean_title(s.titolo)
    titolo_html = f"<b>{html.escape(titolo_clean)}</b>"
    orari_html = _format_orari(s.orari)
    note_txt = _format_note(s.note, cinema_name=s.cinema)
    note_html = html.escape(note_txt) if note_txt else ""

    lines = [f"• {titolo_html}"]
    if orari_html and note_html:
        lines.append(f"  {orari_html}  —  {note_html}")
    elif orari_html:
        lines.append(f"  {orari_html}")
    elif note_html:
        lines.append(f"  {note_html}")

    return "\n".join(lines)


def render_snapshot(snapshot: CacheSnapshot, *, mode: str = "cinema") -> list[str]:
    """Restituisce uno o piu' messaggi Telegram formattati in HTML.

    mode="cinema"  -> raggruppamento per cinema (default)
    mode="timeslot" -> raggruppamento per fascia oraria
    """
    header = (
        f"🎬 <b>Programmazione Cinema Bologna</b>\n"
        f"📅 <i>{_format_date(snapshot.target_date)}</i>\n"
        f"🔄 <i>Aggiornato alle {snapshot.updated_at.strftime('%H:%M')}</i>"
    )

    if snapshot.is_empty and not snapshot.warnings:
        return [header + "\n\n<i>Nessuna proiezione disponibile per oggi.</i>"]

    if mode == "timeslot":
        return _render_timeslot(snapshot, header)
    return _render_cinema(snapshot, header)


def _render_cinema(snapshot: CacheSnapshot, header: str) -> list[str]:
    grouped = _group_by_cinema(snapshot.screenings)
    cinema_count = len(grouped)
    film_count = len(snapshot.screenings)

    header += f"\n📊 <b>{film_count}</b> film  •  <b>{cinema_count}</b> cinema\n"

    sections: list[str] = []
    for cinema, films in grouped.items():
        film_count_cinema = len(films)
        cinema_header = f"📍 <b>{html.escape(cinema)}</b> <i>({film_count_cinema})</i>"
        film_lines = [_format_film(f) for f in films]
        blockquote_body = "\n\n".join(film_lines)
        section = f"{cinema_header}\n<blockquote>{blockquote_body}</blockquote>"
        sections.append(section)

    return _assemble(header, sections, snapshot.warnings)


def _render_timeslot(snapshot: CacheSnapshot, header: str) -> list[str]:
    grouped = _group_by_timeslot(snapshot.screenings)
    cinema_count = len({c for slot_data in grouped.values() for c in slot_data})
    film_count = len(snapshot.screenings)

    header += (
        f"\n📊 <b>{film_count}</b> film  •  <b>{cinema_count}</b> cinema\n"
        f"<i>{_timeslot_label()}</i>\n"
    )

    parts: list[str] = []
    for slot_name, cinemas in grouped.items():
        slot_film_count = sum(len(fs) for fs in cinemas.values())
        slot_header = f"{slot_name}  <i>({slot_film_count})</i>"
        film_lines: list[str] = []
        for cinema, films in cinemas.items():
            cinema_label = f"<u>{html.escape(cinema)}</u>"
            for f in films:
                titolo_clean = _clean_title(f.titolo)
                orari_in_slot = _filter_orari_for_slot(f.orari, slot_name)
                orari_html = _format_orari(orari_in_slot)
                note_txt = _format_note(f.note, cinema_name=f.cinema)
                note_html = html.escape(note_txt) if note_txt else ""
                entry = [f"• {cinema_label} — <b>{html.escape(titolo_clean)}</b>"]
                if orari_html and note_html:
                    entry.append(f"  {orari_html}  —  {note_html}")
                elif orari_html:
                    entry.append(f"  {orari_html}")
                elif note_html:
                    entry.append(f"  {note_html}")
                film_lines.append("\n".join(entry))

        # Split film lines into blockquote chunks that fit within _MAX_LEN
        chunk_header = slot_header
        chunk_lines: list[str] = []
        for line in film_lines:
            test_body = "\n\n".join(chunk_lines + [line])
            test_section = f"{chunk_header}\n<blockquote>{test_body}</blockquote>"
            if chunk_lines and len(test_section) > _MAX_LEN:
                parts.append(
                    f"{chunk_header}\n<blockquote>"
                    + "\n\n".join(chunk_lines)
                    + "</blockquote>"
                )
                chunk_lines = [line]
            else:
                chunk_lines.append(line)
        if chunk_lines:
            parts.append(
                f"{chunk_header}\n<blockquote>"
                + "\n\n".join(chunk_lines)
                + "</blockquote>"
            )

    return _assemble(header, parts, snapshot.warnings)


def _filter_orari_for_slot(orari: list[str], slot_name: str) -> list[str]:
    """Filtra gli orari che appartengono alla fascia indicata."""
    for name, start, end in _TIMESLOTS:
        if name == slot_name:
            s_min = _parse_time(start)
            e_min = _parse_time(end)
            return [o for o in orari if s_min <= _parse_time(o) < e_min]
    return orari


def _assemble(header: str, sections: list[str], warnings: list[str]) -> list[str]:
    warnings_block = ""
    if warnings:
        warning_lines = "\n".join(f"⚠️ {html.escape(w)}" for w in warnings)
        warnings_block = f"\n\n<b>⚠️ Avvisi</b>\n{warning_lines}"

    messages: list[str] = []
    current = header
    for section in sections:
        if len(current) + len(section) + 2 > _MAX_LEN:
            messages.append(current.strip())
            current = section
        else:
            current += "\n" + section

    if warnings_block:
        if len(current) + len(warnings_block) > _MAX_LEN:
            messages.append(current.strip())
            current = warnings_block.lstrip("\n")
        else:
            current += warnings_block

    if current.strip():
        messages.append(current.strip())

    return messages
