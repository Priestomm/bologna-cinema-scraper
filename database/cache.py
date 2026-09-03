"""Cache SQLite per la programmazione giornaliera.

Schema:
- snapshots(date TEXT PRIMARY KEY, updated_at TEXT, payload JSON)
  Contiene UN record per giornata: tutta la programmazione e gli avvisi
  per i circuiti che hanno fallito sono nel payload JSON.

Il bot legge sempre da qui; mai dalle fonti remote.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, fields
from datetime import date, datetime
from pathlib import Path
from typing import Iterator

import pytz

from config import settings
from scrapers import Screening, ScraperResult

# Campi conosciuti dal dataclass: usati per filtrare snapshot vecchi
# che potrebbero contenere chiavi extra (retro-compatibilita').
_SCREENING_FIELDS = {f.name for f in fields(Screening)}


_TZ = pytz.timezone(settings.timezone)


@dataclass
class CacheSnapshot:
    """Snapshot di una giornata letta dalla cache."""

    target_date: date
    updated_at: datetime
    screenings: list[Screening]
    warnings: list[str]  # avvisi su scraper falliti

    @property
    def is_empty(self) -> bool:
        return not self.screenings


class Cache:
    def __init__(self, db_path: Path | None = None) -> None:
        self.path = Path(db_path or settings.cache_db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    # ---- schema -------------------------------------------------------

    def _init_schema(self) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS snapshots (
                    date TEXT PRIMARY KEY,
                    updated_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # ---- scrittura ----------------------------------------------------

    def store(self, target_date: date, results: list[ScraperResult]) -> CacheSnapshot:
        """Salva l'esito di un ciclo di scraping per una giornata."""
        screenings: list[Screening] = []
        warnings: list[str] = []

        for r in results:
            if r.success:
                screenings.extend(r.screenings)
                if not r.screenings:
                    warnings.append(
                        f"Nessuna proiezione trovata per {r.name} (controlla i selettori)."
                    )
            else:
                warnings.append(
                    f"Circuito non disponibile: {r.name} ({r.error})."
                )

        payload = {
            "screenings": [s.to_dict() for s in screenings],
            "warnings": warnings,
        }
        now = datetime.now(_TZ).isoformat()

        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO snapshots (date, updated_at, payload)
                VALUES (?, ?, ?)
                ON CONFLICT(date) DO UPDATE SET
                    updated_at = excluded.updated_at,
                    payload = excluded.payload
                """,
                (target_date.isoformat(), now, json.dumps(payload, ensure_ascii=False)),
            )

        return CacheSnapshot(
            target_date=target_date,
            updated_at=datetime.fromisoformat(now),
            screenings=screenings,
            warnings=warnings,
        )

    # ---- lettura ------------------------------------------------------

    def load(self, target_date: date) -> CacheSnapshot | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT updated_at, payload FROM snapshots WHERE date = ?",
                (target_date.isoformat(),),
            ).fetchone()

        if not row:
            return None

        updated_at_raw, payload_raw = row
        payload = json.loads(payload_raw)
        screenings = [
            Screening(**{k: v for k, v in item.items() if k in _SCREENING_FIELDS})
            for item in payload.get("screenings", [])
        ]
        warnings = list(payload.get("warnings", []))
        return CacheSnapshot(
            target_date=target_date,
            updated_at=datetime.fromisoformat(updated_at_raw),
            screenings=screenings,
            warnings=warnings,
        )
