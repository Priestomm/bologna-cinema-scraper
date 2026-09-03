"""Entry point dell'applicazione.

Uso:
    python main.py            # avvia il bot + scheduler (modalita' normale)
    python main.py --scrape   # esegue solo un ciclo di scraping e termina
    python main.py --broadcast# esegue uno scraping e invia il messaggio (dry-run)
"""
from __future__ import annotations

import argparse
import asyncio
import sys

from bot import CinemaBot, run_scrape_pipeline
from bot.formatter import render_snapshot
from utils import get_logger

logger = get_logger("main")


def _run_scrape_only() -> int:
    snapshot = run_scrape_pipeline()
    logger.info(
        "Risultato: %d film, %d avvisi",
        len(snapshot.screenings),
        len(snapshot.warnings),
    )
    for chunk in render_snapshot(snapshot):
        print(chunk)
        print("-" * 60)
    return 0


def _run_broadcast_test() -> int:
    """Esegue uno scrape e invia in chat (utile per testare la formattazione)."""
    from config import settings
    from telegram import Bot
    from telegram.constants import ParseMode

    snapshot = run_scrape_pipeline()

    async def _send() -> None:
        bot = Bot(token=settings.telegram_token)
        for chunk in render_snapshot(snapshot):
            await bot.send_message(
                chat_id=settings.telegram_chat_id,
                text=chunk,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )

    asyncio.run(_send())
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Bot Telegram cinema Bologna")
    parser.add_argument(
        "--scrape",
        action="store_true",
        help="Esegue solo uno scraping e stampa il risultato",
    )
    parser.add_argument(
        "--broadcast",
        action="store_true",
        help="Scrape + invio messaggio nella chat configurata (test)",
    )
    args = parser.parse_args()

    if args.scrape:
        return _run_scrape_only()
    if args.broadcast:
        return _run_broadcast_test()

    bot = CinemaBot()
    bot.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
