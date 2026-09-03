"""Scheduler interno: 07:30 scraping, 08:00 broadcast.

Tutto orario locale Europe/Rome. Gli scheduler non si sovrappongono:
il broadcast legge dalla cache popolata dal job di scraping.
"""

from __future__ import annotations

from typing import Awaitable, Callable

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from config import settings
from utils import get_logger

logger = get_logger("bot.scheduler")


class CinemaScheduler:
    def __init__(
        self,
        on_scrape: Callable[[], Awaitable[None]],
        on_broadcast: Callable[[], Awaitable[None]],
    ) -> None:
        self._on_scrape = on_scrape
        self._on_broadcast = on_broadcast
        self._scheduler = AsyncIOScheduler(timezone=settings.timezone)

    def start(self) -> None:
        self._scheduler.add_job(
            self._on_scrape,
            CronTrigger(
                hour=settings.scrape_cron_hour,
                minute=settings.scrape_cron_minute,
                timezone=settings.timezone,
            ),
            id="daily_scrape",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        self._scheduler.add_job(
            self._on_broadcast,
            CronTrigger(
                hour=settings.broadcast_cron_hour,
                minute=settings.broadcast_cron_minute,
                timezone=settings.timezone,
            ),
            id="daily_broadcast",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        self._scheduler.start()
        logger.info(
            "Scheduler avviato: scrape %02d:%02d, broadcast %02d:%02d (%s)",
            settings.scrape_cron_hour,
            settings.scrape_cron_minute,
            settings.broadcast_cron_hour,
            settings.broadcast_cron_minute,
            settings.timezone,
        )

    def shutdown(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
