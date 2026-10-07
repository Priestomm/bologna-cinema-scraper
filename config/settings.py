"""Caricamento configurazione da variabili d'ambiente (.env)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


def _env(key: str, default: str | None = None, required: bool = False) -> str:
    value = os.getenv(key, default)
    if required and not value:
        raise RuntimeError(f"Variabile d'ambiente richiesta mancante: {key}")
    return value or ""


def _int(key: str, default: int) -> int:
    raw = os.getenv(key)
    return int(raw) if raw and raw.strip() else default


@dataclass(frozen=True)
class Settings:
    telegram_token: str
    telegram_chat_id: str
    scrape_cron_hour: int
    scrape_cron_minute: int
    broadcast_cron_hour: int
    broadcast_cron_minute: int
    scraper_timeout: int
    http_user_agent: str
    cache_db_path: Path
    log_level: str
    refresh_interval_minutes: int = 15
    health_port: int = 8080
    timezone: str = "Europe/Rome"
    tmdb_api_key: str = ""
    # Timeout complessivo di uno scraping multi-giorno (piu' richieste HTTP,
    # retry su 429 compresi): SCRAPER_TIMEOUT vale per la singola richiesta.
    scraper_total_timeout: int = 90
    # Token richiesto da POST /api/refresh (header X-Refresh-Token).
    # Vuoto = endpoint disabilitato.
    refresh_token: str = ""
    # Chat Telegram (privata, NON quella del broadcast) per gli alert sui
    # circuiti che falliscono. Vuoto = alert solo nei log.
    admin_chat_id: str = ""
    # Fallimenti consecutivi di un circuito prima dell'alert (3 = 45 minuti
    # col refresh di default ogni 15).
    alert_after_failures: int = 3
    # Backup notturno della cache SQLite: cartella e quante copie tenere.
    backup_dir: Path = PROJECT_ROOT / "data" / "backups"
    backup_keep: int = 14
    backup_cron_hour: int = 3


def _load() -> Settings:
    return Settings(
        telegram_token=_env("TELEGRAM_BOT_TOKEN", required=True),
        telegram_chat_id=_env("TELEGRAM_CHAT_ID", required=True),
        scrape_cron_hour=_int("SCRAPE_CRON_HOUR", 7),
        scrape_cron_minute=_int("SCRAPE_CRON_MINUTE", 30),
        broadcast_cron_hour=_int("BROADCAST_CRON_HOUR", 8),
        broadcast_cron_minute=_int("BROADCAST_CRON_MINUTE", 0),
        scraper_timeout=_int("SCRAPER_TIMEOUT", 15),
        http_user_agent=_env(
            "HTTP_USER_AGENT",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        ),
        cache_db_path=PROJECT_ROOT / _env("CACHE_DB_PATH", "data/cache.sqlite3"),
        log_level=_env("LOG_LEVEL", "INFO"),
        refresh_interval_minutes=_int("REFRESH_INTERVAL_MINUTES", 15),
        health_port=_int("HEALTH_PORT", 8080),
        tmdb_api_key=_env("TMDB_API_KEY"),
        scraper_total_timeout=_int("SCRAPER_TOTAL_TIMEOUT", 90),
        refresh_token=_env("REFRESH_TOKEN"),
        admin_chat_id=_env("ADMIN_CHAT_ID"),
        alert_after_failures=_int("ALERT_AFTER_FAILURES", 3),
        backup_dir=PROJECT_ROOT / _env("BACKUP_DIR", "data/backups"),
        backup_keep=_int("BACKUP_KEEP", 14),
        backup_cron_hour=_int("BACKUP_CRON_HOUR", 3),
    )


settings = _load()
