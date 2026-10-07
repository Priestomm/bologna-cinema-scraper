"""Alert sui circuiti che falliscono di fila.

Col fallback della pipeline un circuito rotto non sparisce piu' dal sito
(restano gli orari dell'ultimo aggiornamento riuscito): proprio per questo
serve qualcuno che se ne accorga. CircuitHealth conta i fallimenti
consecutivi per circuito e produce un Alert una volta sola quando si
supera la soglia, e uno quando il circuito torna a funzionare.

La pipeline registra gli esiti, chi ha accesso a Telegram (il bot) svuota
la coda con drain() e manda i messaggi: core/ non dipende da bot/.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from html import escape
from typing import Literal

from config import settings


@dataclass(frozen=True)
class Alert:
    kind: Literal["down", "recovered"]
    name: str
    failures: int
    error: str = ""

    def to_html(self) -> str:
        if self.kind == "down":
            return (
                f"⚠️ <b>{escape(self.name)}</b>: {self.failures} scraping "
                f"falliti di fila.\nUltimo errore: {escape(self.error)}"
            )
        return (
            f"✅ <b>{escape(self.name)}</b> di nuovo raggiungibile "
            f"(dopo {self.failures} fallimenti)."
        )


class CircuitHealth:
    def __init__(self, threshold: int) -> None:
        self.threshold = max(1, threshold)
        self._failures: dict[str, int] = {}
        self._pending: list[Alert] = []
        # La pipeline gira sia nello scheduler sia da /api/refresh.
        self._lock = threading.Lock()

    def record(self, slug: str, name: str, error: str | None) -> None:
        """Registra l'esito di un circuito: error=None vuol dire successo."""
        with self._lock:
            count = self._failures.get(slug, 0)
            if error is None:
                if count >= self.threshold:
                    self._pending.append(Alert("recovered", name, count))
                self._failures[slug] = 0
                return
            count += 1
            self._failures[slug] = count
            # Una volta sola, quando si raggiunge la soglia: non a ogni giro.
            if count == self.threshold:
                self._pending.append(Alert("down", name, count, error))

    def drain(self) -> list[Alert]:
        with self._lock:
            alerts, self._pending = self._pending, []
            return alerts


circuit_health = CircuitHealth(settings.alert_after_failures)
