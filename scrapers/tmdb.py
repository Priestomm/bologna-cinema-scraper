"""Client TMDb con cache SQLite per i rating dei film.

Cerca ogni titolo su TMDb API e restituisce il rating medio (0-10).
Usa una cache locale (TTL 7 giorni) per evitare chiamate API ripetute.
Matching fuzzy su titolo + regista per gestire differenze tra titoli
italiani e originali.
"""

from __future__ import annotations

import difflib
import re
import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager

import requests

from config import settings
from scrapers.base import Screening
from utils import get_logger

logger = get_logger("scrapers.tmdb")

_TMDB_SEARCH_URL = "https://api.themoviedb.org/3/search/movie"
_CACHE_TTL_DAYS = 7

_TMDB_GENRES: dict[int, str] = {
    28: "Azione",
    12: "Avventura",
    16: "Animazione",
    35: "Commedia",
    80: "Crime",
    99: "Documentario",
    18: "Dramma",
    10751: "Famiglia",
    14: "Fantasy",
    36: "Storia",
    27: "Horror",
    10402: "Musica",
    9648: "Mistero",
    10749: "Romance",
    878: "Fantascienza",
    53: "Thriller",
    10752: "Guerra",
    37: "Western",
}


def _normalize(text: str) -> str:
    """Lowercase, senza punteggiatura, trim."""
    t = text.lower()
    t = re.sub(r"\s*\(.*?\)\s*", " ", t)
    # Rimuovi prefissi comuni 18tickets
    for prefix in ("original version - ", "original version: ", "original: ", "v.o.: "):
        t = t.removeprefix(prefix)
    t = re.sub(r"\s*-\s*v\.?\s*o\.?\s*$", "", t)
    t = re.sub(r"\s*-\s*versione originale\s*$", "", t)
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    return " ".join(t.split())


def _clean_title_for_search(title: str) -> str:
    """Pulisce il titolo per la ricerca TMDb: rimuove prefissi/suffissi 18tickets."""
    t = title.lower()
    for prefix in ("original version - ", "original version: ", "original: ", "v.o.: "):
        t = t.removeprefix(prefix)
    t = re.sub(r"\s*-\s*v\.?\s*o\.?\s*$", "", t)
    t = re.sub(r"\s*-\s*versione originale\s*$", "", t)
    t = re.sub(r"[()]", " ", t)
    return " ".join(t.split()).strip()


class TmdbClient:
    """Cerca rating film su TMDb con cache SQLite."""

    def __init__(self) -> None:
        self._api_key = settings.tmdb_api_key
        self._session = requests.Session()
        self._cache_path = settings.cache_db_path.parent / "tmdb_ratings.sqlite3"
        self._init_schema()

    @property
    def enabled(self) -> bool:
        return bool(self._api_key)

    # ---- cache -------------------------------------------------------

    def _init_schema(self) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS ratings (
                    cache_key TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    rating REAL,
                    tmdb_title TEXT,
                    genres TEXT NOT NULL DEFAULT '',
                    fetched_at REAL NOT NULL
                )
                """
            )
            # Migrazione: aggiungi colonna genres se manca
            cols = {row[1] for row in conn.execute("PRAGMA table_info(ratings)")}
            if "genres" not in cols:
                conn.execute(
                    "ALTER TABLE ratings ADD COLUMN genres TEXT NOT NULL DEFAULT ''"
                )

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self._cache_path)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _cache_get(self, cache_key: str) -> tuple[float | None, str, str] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT rating, tmdb_title, genres, fetched_at FROM ratings WHERE cache_key = ?",
                (cache_key,),
            ).fetchone()
        if not row:
            return None
        rating, tmdb_title, genres, fetched_at = row
        age_days = (time.time() - fetched_at) / 86400
        if age_days > _CACHE_TTL_DAYS:
            return None
        return rating, tmdb_title or "", genres or ""

    def _cache_put(
        self,
        cache_key: str,
        title: str,
        rating: float | None,
        tmdb_title: str,
        genres: str = "",
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO ratings (cache_key, title, rating, tmdb_title, genres, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    rating = excluded.rating,
                    tmdb_title = excluded.tmdb_title,
                    genres = excluded.genres,
                    fetched_at = excluded.fetched_at
                """,
                (cache_key, title, rating, tmdb_title, genres, time.time()),
            )

    # ---- TMDb API ---------------------------------------------------

    def _search(self, query: str) -> list[dict]:
        """Cerca film su TMDb, restituisce tutti i risultati."""
        if not self.enabled:
            return []
        try:
            resp = self._session.get(
                _TMDB_SEARCH_URL,
                params={
                    "api_key": self._api_key,
                    "query": query,
                    "language": "it-IT",
                    "include_adult": "false",
                },
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning("TMDb search fallito per '%s': %s", query, exc)
            return []
        return data.get("results", [])

    def _find_best_match(
        self, title: str, regista: str, results: list[dict]
    ) -> dict | None:
        """Trova il risultato TMDb che matcha meglio titolo + regista.

        Usa SequenceMatcher sul titolo e bonus per match del regista.
        """
        if not results:
            return None

        norm_title = _normalize(_clean_title_for_search(title))

        best_score = -1.0
        best: dict | None = None

        for r in results:
            # Score titolo (0-1)
            candidates = [r.get("title", ""), r.get("original_title", "")]
            title_score = 0.0
            for c in candidates:
                if not c:
                    continue
                s = difflib.SequenceMatcher(None, norm_title, _normalize(c)).ratio()
                title_score = max(title_score, s)

            # Bonus regista (TMDb non ha il regista in search, ma lo ignoriamo)
            # Invece: se il titolo esatto matcha, bonus +0.2
            if norm_title == _normalize(_clean_title_for_search(r.get("title", ""))):
                title_score = min(1.0, title_score + 0.2)
            if norm_title == _normalize(
                _clean_title_for_search(r.get("original_title", ""))
            ):
                title_score = min(1.0, title_score + 0.2)

            if title_score > best_score:
                best_score = title_score
                best = r

        if best_score >= 0.45:
            return best
        return None

    def _get_movie_info(self, title: str, regista: str) -> tuple[str, str]:
        """Cerca rating + genere per un film dato titolo e regista."""
        if not self.enabled:
            return "", ""

        cache_key = (
            f"{_normalize(_clean_title_for_search(title))}|{_normalize(regista)}"
        )
        if not cache_key.strip("|"):
            return "", ""

        # Check cache
        cached = self._cache_get(cache_key)
        if cached is not None:
            rating, _tmdb_title, genres = cached
            rating_str = f"{rating:.1f}" if rating is not None else ""
            return rating_str, genres

        # Search TMDb
        search_query = _clean_title_for_search(title)
        results = self._search(search_query)

        # Se nessun risultato, prova solo con le prime 3 parole
        if not results:
            words = search_query.split()[:3]
            if len(words) >= 2:
                results = self._search(" ".join(words))

        if not results:
            self._cache_put(cache_key, title, None, "")
            return "", ""

        # Find best match
        match = self._find_best_match(title, regista, results)
        if not match:
            match = results[0]  # fallback: primo risultato

        rating = match.get("vote_average")
        tmdb_title = match.get("title", "")
        genre_ids = match.get("genre_ids", [])
        genres = " / ".join(
            _TMDB_GENRES[gid] for gid in genre_ids if gid in _TMDB_GENRES
        )

        self._cache_put(cache_key, title, rating, tmdb_title, genres)

        rating_str = ""
        if rating is not None and rating > 0:
            rating_str = f"{rating:.1f}"
        return rating_str, genres

    def enrich_screenings(self, screenings: list[Screening]) -> list[Screening]:
        """Aggiunge rating e genere a ogni Screening (muta in-place e restituisce)."""
        if not self.enabled:
            logger.info("TMDb disabilitato (nessuna API key)")
            return screenings

        # Deduplica per (titolo, regista) per evitare ricerche multiple
        unique: dict[tuple[str, str], tuple[str, str]] = {}
        for s in screenings:
            key = (s.titolo, s.regista)
            if key not in unique:
                unique[key] = ("", "")

        logger.info("Cerco rating + genere per %d film unici su TMDb", len(unique))

        for i, (titolo, regista) in enumerate(unique):
            rating, genre = self._get_movie_info(titolo, regista)
            unique[(titolo, regista)] = (rating, genre)
            if rating or genre:
                logger.debug("  %s (%s) → %s | %s", titolo, regista, rating, genre)
            if (i + 1) % 5 == 0:
                logger.info("  %d/%d film cercati", i + 1, len(unique))

        for s in screenings:
            rating, genre = unique.get((s.titolo, s.regista), ("", ""))
            s.rating = rating
            s.genre = genre

        return screenings
