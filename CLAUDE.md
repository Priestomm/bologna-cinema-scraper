# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

A Telegram bot + mini-website that scrapes and publishes the daily cinema listings for five Bologna theater circuits (Cineteca, Pop Up Cinema, Circuito Cinema, Nosadella, UCI Meridiana). Runs 24/7 on Oracle Cloud via PM2. Comments/docstrings in the codebase are in Italian; match that style when editing existing files.

## Commands

```bash
make install      # pip install -r requirements.txt
make test         # python -m pytest tests/ -v
make lint         # ruff check .
make format       # ruff format . && ruff check . --fix
make typecheck    # mypy --ignore-missing-imports .
make run          # python main.py (bot + scheduler, foreground)
make scrape       # python main.py --scrape (single-day scrape, no send)
make broadcast    # python main.py --broadcast (scrape + real Telegram send)
```

Single test: `python -m pytest tests/test_formatter.py::test_name -v`

Multi-day scrape (used to backfill/warm cache for a week): `python main.py --scrape --days 7`.

CI (`.github/workflows/ci.yml`) runs three independent jobs on every push/PR to `main`/`master`: `ruff check` + `ruff format --check`, `mypy --ignore-missing-imports .`, and `pytest tests/ -v`. There is no repo-level ruff/mypy config file — both run with default settings plus CLI flags.

`.env` (from `.env.example`) is required — `config/settings.py` raises `RuntimeError` at import time if `TELEGRAM_BOT_TOKEN` or `TELEGRAM_CHAT_ID` is missing. Tests avoid this via `tests/conftest.py`, which sets fake env vars with `os.environ.setdefault` before any app import.

## Architecture

Data flows one way: **scrapers → pipeline (+ TMDb enrichment) → SQLite cache → bot/API read from cache only.** Nothing downstream ever hits a scraper source directly; `database/cache.py`'s module docstring states this explicitly.

- `scrapers/base.py` — `Screening` dataclass (the standardized model every scraper must emit) and `BaseScraper`. `BaseScraper.run()` executes `_fetch()` in a single-thread `ThreadPoolExecutor` with a hard timeout (`settings.scraper_timeout`) and catches all exceptions, always returning a `ScraperResult(success=False, error=...)` instead of raising — one broken cinema site can never crash the pipeline. Concrete scrapers only implement `_fetch(target_date) -> list[Screening]`; multi-day scraping optionally overrides `fetch_all_dates()` to do one HTTP request instead of N (avoids 429s).
- `scrapers/_tickets18.py` — shared HTML parser for the "18tickets" ticketing platform, reused by Cineteca, Pop Up, Circuito Cinema, and Nosadella. `parse_all_dates()` is the single extraction path, grouping every showing by date; `parse_day()` is just `parse_all_dates(..., max_days=1)` filtered to one date. Showtimes are matched via `data-time` (ms epoch UTC) converted to `Europe/Rome`; there's a regex-based text fallback for pages without `data-time`.
- `scrapers/_tickets18_base.py` — two `BaseScraper` subclasses built on top of `_tickets18.py` so concrete scrapers stay declarative: `SingleTheaterScraper` (one 18tickets page lists every room — Nosadella, Pop Up) and `MultiTheaterScraper` (one 18tickets page per room, fetched in parallel and merged — Cineteca, Circuito Cinema). Subclasses just set `base_url`/`theaters` + `label` (the string appended to each `Screening.note`); `MultiTheaterScraper._fetch_html()` and `SingleTheaterScraper._post_process()` are the two override points (used by Circuito Cinema for HTTP retry-on-429, and Pop Up for promoting the room name into `Screening.cinema`).
- `scrapers/uci.py` — talks to UCI's own API directly instead of scraping HTML.
- `scrapers/tmdb.py` — `TmdbClient`, optional (`tmdb.enabled` is false without `TMDB_API_KEY`); enriches `Screening` objects in place with rating, genre, high-res poster, overview, runtime, using a local SQLite cache (`data/tmdb_ratings.sqlite3`) with a 7-day TTL to avoid hitting the TMDb API repeatedly for the same title.
- `scrapers/__init__.py` — `ALL_SCRAPERS` is the registry list; adding a new cinema circuit means creating a new `BaseScraper` subclass and appending its class here.
- `bot/pipeline.py` — orchestrates one scrape cycle: runs every scraper in `ALL_SCRAPERS` concurrently (`ThreadPoolExecutor`), collects `Screening`s, enriches via `TmdbClient` if enabled, then writes to `Cache`. Two entry points: `run_scrape_pipeline` (single day, or a loop of single-day scrapes) and `run_multi_day_pipeline` (scrapes each circuit exactly once and extracts N days of showtimes from that one response — the "avoid 429" optimization mentioned above). Scraper failures become warning strings surfaced through the cache/API/messages rather than raised exceptions.
- `database/cache.py` — `Cache` wraps a SQLite `snapshots` table keyed by ISO date, storing screenings + warnings as a JSON payload, plus broadcast-dedup bookkeeping (`is_broadcast_done_today` / `mark_broadcast_done`) so the daily broadcast job doesn't double-send on restart. `_SCREENING_FIELDS` filters stored JSON keys against the current `Screening` dataclass fields on load, for backward compatibility with older cached payloads.
- `bot/scheduler.py` — `CinemaScheduler` wraps `AsyncIOScheduler` (APScheduler) with three jobs, all `Europe/Rome`, `max_instances=1`, `coalesce=True`: daily scrape (`SCRAPE_CRON_HOUR/MINUTE`), daily broadcast (`BROADCAST_CRON_HOUR/MINUTE`), and a periodic refresh every `REFRESH_INTERVAL_MINUTES` that re-runs the scrape job. Broadcast always reads from the cache the scrape job just populated — they never race on scraping the same data.
- `bot/telegram_bot.py` — `CinemaBot`, the `python-telegram-bot` app: wires up the scheduler's callbacks, the `/cinema` command handler, and lifecycle (`run()` is the blocking entry point used by `main.py` with no flags).
- `bot/formatter.py` — renders `CacheSnapshot` into Telegram HTML messages, chunked to fit message-size limits (`render_snapshot` returns an iterable of message chunks); automatically appends an "Avvisi" (warnings) section listing circuits that failed to scrape.
- `bot/health.py` — FastAPI app: serves the mini-site (Jinja2 templates in `bot/templates/`) at `/` and `/{YYYY-MM-DD}`, plus the JSON API (`/api/screenings`, `/api/cinemas`, `/api/history`, `/api/stats`, `/api/refresh`, `/health`). Swagger UI at `/docs`. Static assets (including seasonal decorative stickers) live in `bot/static/`.
- `config/settings.py` — single frozen `Settings` dataclass loaded once at import time from `.env` (via `python-dotenv`); everything else imports the module-level `settings` singleton rather than reading env vars directly.
- `main.py` — CLI entry point with three modes: no flags (`CinemaBot().run()`, the real long-running process), `--scrape [--days N]` (pipeline only, prints counts, no Telegram), `--broadcast` (scrape + actually send to the configured chat — used for testing message formatting).

## Testing conventions

`tests/conftest.py` defines shared fixtures (`sample_screening`, `sample_screenings`, `target_date`) and several `MOCK_HTML_*` fixtures with hand-written 18tickets-style HTML for exercising `scrapers/_tickets18.py` without network access. When adding a scraper test, prefer extending these mocks over hitting real sites.
