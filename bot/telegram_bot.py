"""Bot Telegram: comando /cinema + broadcast automatico.

Il bot non scrape mai inline: legge sempre dalla cache. Se la cache del
giorno non esiste (raro, es. primo avvio), forza una pipeline al volo.
"""

from __future__ import annotations

import asyncio
import threading

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

from config import settings
from database import Cache
from utils import get_logger

from .formatter import render_snapshot
from .health import start_api_server
from .pipeline import run_scrape_pipeline, today
from .scheduler import CinemaScheduler

logger = get_logger("bot.telegram")


class CinemaBot:
    def __init__(self) -> None:
        self._cache = Cache()
        self._app: Application = (
            ApplicationBuilder().token(settings.telegram_token).build()
        )
        self._scheduler = CinemaScheduler(
            on_scrape=self._job_scrape,
            on_broadcast=self._job_broadcast,
        )
        self._health_server: threading.Thread | None = None
        self._register_handlers()

    # ---- handlers -----------------------------------------------------

    def _register_handlers(self) -> None:
        self._app.add_handler(CommandHandler("start", self._cmd_start))
        self._app.add_handler(CommandHandler("help", self._cmd_start))
        self._app.add_handler(CommandHandler("cinema", self._cmd_cinema))

    async def _cmd_start(
        self, update: Update, _context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if not update.message:
            return
        await update.message.reply_text(
            "Ciao! Comandi disponibili:\n"
            "/cinema - programmazione di oggi (Cineteca, Pop Up, Circuito Cinema, Nosadella)\n"
            "Il bot invia automaticamente il riepilogo ogni mattina alle "
            f"{settings.broadcast_cron_hour:02d}:{settings.broadcast_cron_minute:02d}."
        )

    async def _cmd_cinema(
        self, update: Update, _context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if not update.message:
            return
        target = today()
        snapshot = self._cache.load(target)
        if snapshot is None:
            await update.message.reply_text(
                "Cache vuota, recupero ora la programmazione (puo' richiedere fino a "
                f"{settings.scraper_timeout * 2}s)..."
            )
            snapshot = await asyncio.to_thread(run_scrape_pipeline, target)

        for chunk in render_snapshot(snapshot):
            await update.message.reply_text(
                chunk, parse_mode=ParseMode.HTML, disable_web_page_preview=True
            )

    # ---- jobs schedulati ---------------------------------------------

    async def _job_scrape(self) -> None:
        logger.info("Job scrape avviato")
        try:
            await asyncio.to_thread(run_scrape_pipeline)
        except Exception:  # noqa: BLE001
            logger.exception("Job scrape fallito (l'errore e' isolato dal bot)")

    async def _job_broadcast(self) -> None:
        logger.info("Job broadcast avviato verso chat %s", settings.telegram_chat_id)
        target = today()
        snapshot = self._cache.load(target)
        if snapshot is None:
            logger.warning("Cache vuota al broadcast: eseguo scraping di emergenza")
            snapshot = await asyncio.to_thread(run_scrape_pipeline, target)
        for chunk in render_snapshot(snapshot):
            try:
                await self._app.bot.send_message(
                    chat_id=settings.telegram_chat_id,
                    text=chunk,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True,
                )
            except Exception:  # noqa: BLE001
                logger.exception("Invio broadcast fallito")

    # ---- ciclo di vita -----------------------------------------------

    async def _post_init(self, _app: Application) -> None:
        self._scheduler.start()
        self._health_server = start_api_server()

    async def _post_shutdown(self, _app: Application) -> None:
        self._scheduler.shutdown()

    def run(self) -> None:
        self._app.post_init = self._post_init
        self._app.post_shutdown = self._post_shutdown
        logger.info("Bot in avvio (polling Telegram)...")
        self._app.run_polling(allowed_updates=Update.ALL_TYPES)
