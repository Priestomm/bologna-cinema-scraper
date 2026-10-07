from __future__ import annotations

import json
import re
from collections.abc import Iterator
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from config import settings
from core.pipeline import today
from database.cache import Cache
from scrapers.base import ScraperResult, Screening

BASE = "https://bolognaonscreen.it"


@pytest.fixture
def cache(tmp_path: Path) -> Iterator[Cache]:
    cache = Cache(tmp_path / "test.sqlite3")
    with (
        patch("web.web_utils.get_cache", return_value=cache),
        patch("web.web_utils.settings", replace(settings, public_base_url=BASE)),
    ):
        yield cache


@pytest.fixture
def client(cache: Cache) -> TestClient:
    from web.server import app

    return TestClient(app)


def _seed(cache: Cache, days: int) -> None:
    screening = Screening(
        cinema="Rialto",
        titolo="Parasite </script>",
        orari=["18:00", "21:00"],
        regista="Bong Joon-ho",
        runtime=132,
        genre="Dramma/Thriller",
        times_urls={"21:00": "https://biglietti.example/21"},
    )
    result = ScraperResult("Rialto", "rialto", [screening], success=True)
    cache.store(today() + timedelta(days=days), [result])


def _jsonld(html: str) -> dict:
    m = re.search(
        r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL
    )
    assert m, "JSON-LD mancante"
    return json.loads(m.group(1))


class TestHead:
    def test_oggi(self, client: TestClient, cache: Cache) -> None:
        _seed(cache, 0)
        html = client.get("/").text

        assert "<title>Cinema a Bologna oggi, " in html
        assert f'<link rel="canonical" href="{BASE}/">' in html
        assert f'content="{BASE}/static/og-image.jpg"' in html
        assert 'name="robots"' not in html
        assert "1 film in programmazione a Bologna oggi" in html

    def test_pagina_di_oggi_con_data_ha_canonical_su_root(
        self, client: TestClient, cache: Cache
    ) -> None:
        _seed(cache, 0)
        html = client.get(f"/{today().isoformat()}").text
        assert f'<link rel="canonical" href="{BASE}/">' in html

    def test_domani(self, client: TestClient, cache: Cache) -> None:
        _seed(cache, 1)
        d = today() + timedelta(days=1)
        html = client.get(f"/{d.isoformat()}").text
        assert f'<link rel="canonical" href="{BASE}/{d.isoformat()}">' in html
        assert "<title>Cinema a Bologna " in html
        assert "oggi" not in html.split("<title>")[1].split("</title>")[0]

    def test_giorno_passato_noindex(self, client: TestClient, cache: Cache) -> None:
        _seed(cache, -1)
        d = today() - timedelta(days=1)
        html = client.get(f"/{d.isoformat()}").text
        assert '<meta name="robots" content="noindex, follow">' in html
        assert "ld+json" not in html

    def test_giorno_senza_dati_noindex(self, client: TestClient) -> None:
        html = client.get("/").text
        assert '<meta name="robots" content="noindex, follow">' in html

    def test_h1_e_titoli_film_h2(self, client: TestClient, cache: Cache) -> None:
        _seed(cache, 0)
        html = client.get("/").text
        assert html.count("<h1>") == 1
        assert '<h2 class="title-tape">' in html


class TestJsonLd:
    def test_eventi_per_orario(self, client: TestClient, cache: Cache) -> None:
        _seed(cache, 0)
        graph = _jsonld(client.get("/").text)["@graph"]

        by_id = {x["@id"]: x for x in graph if "@id" in x}
        events = [x for x in graph if x["@type"] == "ScreeningEvent"]
        assert len(events) == 2
        assert {e["startDate"][11:16] for e in events} == {"18:00", "21:00"}

        movie = by_id[events[0]["workPresented"]["@id"]]
        assert movie["director"] == [{"@type": "Person", "name": "Bong Joon-ho"}]
        assert movie["duration"] == "PT132M"
        assert movie["genre"] == ["Dramma", "Thriller"]
        assert by_id[events[0]["location"]["@id"]]["name"] == "Rialto"

        late = next(e for e in events if e["startDate"][11:16] == "21:00")
        assert late["offers"]["url"] == "https://biglietti.example/21"

    def test_titolo_non_chiude_lo_script(
        self, client: TestClient, cache: Cache
    ) -> None:
        _seed(cache, 0)
        html = client.get("/").text
        jsonld = html.split('application/ld+json">')[1].split("</script>")[0]
        assert "</" not in jsonld


class TestRobotsSitemap:
    def test_robots(self, client: TestClient) -> None:
        body = client.get("/robots.txt").text
        assert "Disallow: /partials/" in body
        assert "Disallow: /api/" in body
        assert f"Sitemap: {BASE}/sitemap.xml" in body

    def test_sitemap_solo_giorni_con_dati(
        self, client: TestClient, cache: Cache
    ) -> None:
        _seed(cache, 0)
        _seed(cache, 2)
        xml = client.get("/sitemap.xml").text
        d2 = (today() + timedelta(days=2)).isoformat()
        locs = re.findall(r"<loc>(.*?)</loc>", xml)
        assert locs == [f"{BASE}/", f"{BASE}/{d2}"]
        assert xml.count("<lastmod>") == 2


@pytest.mark.parametrize("path", ["/", "/health", "/robots.txt", "/sitemap.xml"])
def test_head(client: TestClient, path: str) -> None:
    assert client.head(path).status_code == 200


def test_partial_porta_title_e_giorno(client: TestClient, cache: Cache) -> None:
    d = today() + timedelta(days=1)
    html = client.get(f"/partials/{d.isoformat()}").text
    assert 'data-slot="title">Cinema a Bologna ' in html
    assert 'data-slot="day-label">' in html
