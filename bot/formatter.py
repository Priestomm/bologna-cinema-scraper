"""Formattazione messaggi Telegram in HTML per Fascia Oraria."""

from __future__ import annotations

import html
from datetime import date
from typing import NamedTuple

from database import CacheSnapshot
from scrapers import Screening

_GIORNI = ("Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica")
_MESI = ("gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre")

_MAX_LEN = 3900

class TimeSlotItem(NamedTuple):
    orario: str
    titolo: str
    cinema: str
    note: str

def _format_date(d: date) -> str:
    return f"{_GIORNI[d.weekday()]} {d.day} {_MESI[d.month - 1]} {d.year}"

def _get_slot_name(orario_str: str) -> str:
    """Assegna la fascia oraria corretta in base all'orario dello screening."""
    try:
        # Prende solo le ore (es. "18:30" -> 18)
        ora = int(orario_str.split(":")[0])
    except (ValueError, IndexError):
        return "🌙 SECONDA SERATA (dalle 21:30)"  # Fallback di sicurezza
        
    if ora < 18:
        return "🌅 POMERIGGIO (fino alle 18:00)"
    if 18 <= ora < 21:
        return "🍹 APERITIVO & PRIMA SERATA (18:00 - 21:30)"
    return "🌙 SECONDA SERATA (dalle 21:30)"

def _group_by_timeslot(screenings: list[Screening]) -> dict[str, list[TimeSlotItem]]:
    """Esplode le proiezioni per singolo orario e le raggruppa per fascia oraria cronologica."""
    # Definiamo l'ordine fisso delle fasce orarie
    slots = {
        "🌅 POMERIGGIO (fino alle 18:00)": [],
        "🍹 APERITIVO & PRIMA SERATA (18:00 - 21:30)": [],
        "🌙 SECONDA SERATA (dalle 21:30)": []
    }
    
    for s in screenings:
        for orario in s.orari:
            slot_name = _get_slot_name(orario)
            slots[slot_name].append(
                TimeSlotItem(orario=orario, titolo=s.titolo, cinema=s.cinema, note=s.note)
            )
            
    # Ordina i film all'interno di ogni fascia per orario e poi per titolo
    for slot_name in slots:
        slots[slot_name].sort(key=lambda x: (x.orario, x.titolo.lower()))
        
    # Ritorna solo le fasce che hanno effettivamente dei film dentro
    return {name: items for name, items in slots.items() if items}

def _format_note_compatta(note: str) -> str:
    if not note:
        return ""
    tags: list[str] = []
    lower = note.lower()
    
    if "vo" in lower:
        tags.append("🗣️ VO")
    if "sub ita" in lower:
        tags.append("🇬🇧 sott. 🇮🇹")
    elif "sub eng" in lower:
        tags.append("🇮🇹 sott. 🇬🇧")
        
    parts = [p.strip() for p in note.split(" - ") if p.strip()]
    sala = parts[-1] if parts and not any(kw in parts[-1].lower() for kw in ("vo", "sub")) else ""
    
    result = " · ".join(tags)
    if sala:
        result += f" ({html.escape(sala)})" if result else html.escape(sala)
    return f" <i>[{result}]</i>" if result else ""

def render_snapshot(snapshot: CacheSnapshot) -> list[str]:
    """Restituisce messaggi strutturati in modo intelligente per orario d'inizio."""
    header = (
        f"🎬 <b>OGGI AL CINEMA A BOLOGNA</b>\n"
        f"📅 <i>{_format_date(snapshot.target_date)}</i>\n"
        f"🕒 <code>Aggiornato alle {snapshot.updated_at.strftime('%H:%M')}</code>"
    )

    if snapshot.is_empty and not snapshot.warnings:
        return [header + "\n\n✨ <i>Nessuna proiezione disponibile per oggi.</i>"]

    grouped_slots = _group_by_timeslot(snapshot.screenings)
    
    # Calcolo statistiche veloci
    cinema_count = len({s.cinema for s in snapshot.screenings})
    film_count = len(snapshot.screenings)
    header += f"\n📊 <b>{film_count}</b> film in programmazione  •  <b>{cinema_count}</b> sale"

    sections: list[str] = []
    for slot_name, items in grouped_slots.items():
        lines = [f"\n<b>{slot_name}</b>", "───────────────────"]
        for item in items:
            note = _format_note_compatta(item.note)
            # Layout super denso: Orario | Titolo | Cinema e Note alla fine
            lines.append(
                f"⏱️ <code>{item.orario}</code> 🔹 <b>{html.escape(item.titolo).upper()}</b>\n"
                f"      📍 <i>{html.escape(item.cinema)}</i>{note}"
            )
        sections.append("\n".join(lines))

    warnings_block = ""
    if snapshot.warnings:
        warning_lines = "\n".join(f"⚠️ {html.escape(w)}" for w in snapshot.warnings)
        warnings_block = f"\n\n⚠️ <b>AVVISI</b>\n{warning_lines}"

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
