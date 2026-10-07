"""Backup notturno della cache SQLite, con rotazione.

Una copia al giorno in settings.backup_dir (cache-YYYY-MM-DD.sqlite3),
tenendo le ultime settings.backup_keep. Stanno sullo stesso disco del
database: proteggono da corruzione e migrazioni sbagliate, non dalla
perdita della macchina. Per quello vanno copiate altrove (vedi README).
"""

from __future__ import annotations

from pathlib import Path

from config import settings
from core.pipeline import today
from database import Cache
from utils import get_logger

logger = get_logger("core.backup")

_PREFIX = "cache-"
_SUFFIX = ".sqlite3"


def backup_cache(
    cache: Cache | None = None,
    dest_dir: Path | None = None,
    keep: int | None = None,
) -> Path:
    """Esegue il backup di oggi e cancella quelli oltre i `keep` piu' recenti."""
    cache = cache or Cache()
    dest_dir = dest_dir or settings.backup_dir
    keep = settings.backup_keep if keep is None else keep

    dest = dest_dir / f"{_PREFIX}{today().isoformat()}{_SUFFIX}"
    cache.backup(dest)
    logger.info("Backup cache salvato in %s", dest)

    # Il nome contiene la data ISO: l'ordine alfabetico e' quello cronologico.
    backups = sorted(dest_dir.glob(f"{_PREFIX}*{_SUFFIX}"))
    for old in backups[: max(0, len(backups) - keep)]:
        old.unlink()
        logger.info("Backup vecchio rimosso: %s", old.name)
    return dest
