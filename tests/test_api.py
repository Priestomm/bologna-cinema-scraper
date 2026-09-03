from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from database.cache import Cache
from scrapers.base import ScraperResult, Screening


@pytest.fixture(autouse=True)
def _patch_cache(tmp_path: Path) -> Iterator[None]:
    db = tmp_path / "test.sqlite3"
    cache = Cache(db)
    with patch("bot.health._get_cache", return_value=cache):
        yield


@pytest.fixture
def client() -> TestClient:
    from bot.health import app

    return TestClient(app)


@pytest.fixture
def seed_cache() -> None:
    from datetime import datetime

    import pytz

    from bot.health import _get_cache
    from config import settings

    cache = _get_cache()
    d = datetime.now(pytz.timezone(settings.timezone)).date()
    screenings = [
        Screening(
            cinema="Rialto", titolo="Parasite", orari=["18:00", "21:00"], note="VO"
        ),
        Screening(cinema="Rialto", titolo="Oppenheimer", orari=["19:30"], note=""),
        Screening(
            cinema="Lumiere", titolo="La grande bellezza", orari=["15:00"], note="VO"
        ),
    ]
    result = ScraperResult(
        name="Test", slug="test", screenings=screenings, success=True
    )
    cache.store(d, [result])


class TestHealth:
    def test_health_empty(self, client: TestClient) -> None:
        resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "degraded"
        assert body["screenings"] == 0

    def test_health_ok(self, client: TestClient, seed_cache: None) -> None:
        resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["screenings"] == 3
        assert "uptime_seconds" in body


class TestScreenings:
    def test_empty(self, client: TestClient) -> None:
        resp = client.get("/api/screenings")
        assert resp.status_code == 404

    def test_today(self, client: TestClient, seed_cache: None) -> None:
        resp = client.get("/api/screenings")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_screenings"] == 3
        assert "Rialto" in body["cinemas"]
        assert "Lumiere" in body["cinemas"]

    def test_specific_date(self, client: TestClient, seed_cache: None) -> None:
        from datetime import datetime

        import pytz

        from config import settings

        d = datetime.now(pytz.timezone(settings.timezone)).date().isoformat()
        resp = client.get(f"/api/screenings?date={d}")
        assert resp.status_code == 200
        assert resp.json()["total_screenings"] == 3

    def test_invalid_date(self, client: TestClient) -> None:
        resp = client.get("/api/screenings?date=not-a-date")
        assert resp.status_code == 400

    def test_missing_date(self, client: TestClient) -> None:
        resp = client.get("/api/screenings?date=2099-01-01")
        assert resp.status_code == 404


class TestCinemas:
    def test_empty(self, client: TestClient) -> None:
        resp = client.get("/api/cinemas")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list(self, client: TestClient, seed_cache: None) -> None:
        resp = client.get("/api/cinemas")
        assert resp.status_code == 200
        cinemas = resp.json()
        names = [c["cinema"] for c in cinemas]
        assert "Rialto" in names
        assert "Lumiere" in names

    def test_filter_by_name(self, client: TestClient, seed_cache: None) -> None:
        resp = client.get("/api/cinemas/rialto")
        assert resp.status_code == 200
        body = resp.json()
        assert body["film_count"] == 2

    def test_not_found(self, client: TestClient, seed_cache: None) -> None:
        resp = client.get("/api/cinemas/nonexistent")
        assert resp.status_code == 404


class TestHistory:
    def test_empty(self, client: TestClient) -> None:
        resp = client.get("/api/history")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_with_data(self, client: TestClient, seed_cache: None) -> None:
        resp = client.get("/api/history?days=7")
        assert resp.status_code == 200
        history = resp.json()
        assert len(history) >= 1
        assert history[0]["screenings"] == 3

    def test_days_bounds(self, client: TestClient) -> None:
        resp = client.get("/api/history?days=100")
        assert resp.status_code == 422  # validation error: max 90


class TestStats:
    def test_empty(self, client: TestClient) -> None:
        resp = client.get("/api/stats")
        assert resp.status_code == 200
        body = resp.json()
        assert body["days_with_data"] == 0
        assert body["unique_cinemas"] == 0

    def test_with_data(self, client: TestClient, seed_cache: None) -> None:
        resp = client.get("/api/stats")
        assert resp.status_code == 200
        body = resp.json()
        assert body["days_with_data"] == 1
        assert body["unique_cinemas"] == 2
        assert "Rialto" in body["cinemas"]
