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


def render_snapshot(snapshot: CacheSnapshot) -> list[str]:
    """Restituisce uno o piu' messaggi Telegram formattati in HTML."""
    header = (
        f"🎬 <b>Programmazione Cinema Bologna</b>\n"
        f"📅 <i>{_format_date(snapshot.target_date)}</i>\n"
        f"🔄 <i>Aggiornato alle {snapshot.updated_at.strftime('%H:%M')}</i>"
    )

    if snapshot.is_empty and not snapshot.warnings:
        return [header + "\n\n<i>Nessuna proiezione disponibile per oggi.</i>"]

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

    warnings_block = ""
    if snapshot.warnings:
        warning_lines = "\n".join(f"⚠️ {html.escape(w)}" for w in snapshot.warnings)
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
