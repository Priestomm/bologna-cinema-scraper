from __future__ import annotations

import os
from datetime import date

import pytest

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "fake-token-for-tests")
os.environ.setdefault("TELEGRAM_CHAT_ID", "-123456")
os.environ.setdefault("CACHE_DB_PATH", "")

from scrapers.base import Screening


@pytest.fixture
def target_date() -> date:
    return date(2026, 6, 8)


@pytest.fixture
def sample_screening() -> Screening:
    return Screening(
        cinema="Cineteca - Lumiere",
        titolo="La grande bellezza",
        orari=["15:00", "20:30"],
        note="VO - Cineteca",
    )


@pytest.fixture
def sample_screenings() -> list[Screening]:
    return [
        Screening(
            cinema="Cineteca - Lumiere",
            titolo="La grande bellezza",
            orari=["15:00", "20:30"],
            note="VO - Cineteca",
        ),
        Screening(
            cinema="Cineteca - Modernissimo",
            titolo="La grande bellezza",
            orari=["18:00"],
            note="Sub ITA - Cineteca",
        ),
        Screening(
            cinema="Rialto",
            titolo="Parasite",
            orari=["17:00", "21:00"],
            note="Circuito Cinema",
        ),
        Screening(
            cinema="Rialto",
            titolo="Oppenheimer",
            orari=["19:30"],
            note="Circuito Cinema",
        ),
    ]


MOCK_HTML_ONE_MOVIE = """
<html><body>
<div class="movie movie--preview">
  <a class="movie__title">La grande bellezza</a>
  <p class="movie__option"><strong>Lingua:</strong> Italiano versione originale sottotitoli in inglese</p>
  <div class="schedule-section-show">
    Cinema Lumiere - Proiezioni
    <ul>
      <li><a data-time="1780923600000">15:00</a></li>
      <li><a data-time="1780943400000">20:30</a></li>
    </ul>
  </div>
</div>
</body></html>
"""

MOCK_HTML_MULTI_MOVIE = """
<html><body>
<div class="movie movie--preview">
  <a class="movie__title">La grande bellezza</a>
  <p class="movie__option"><strong>Lingua:</strong> Versione originale</p>
  <div class="schedule-section-show">
    Cinema Lumiere
    <ul>
      <li><a data-time="1780923600000">15:00</a></li>
    </ul>
  </div>
</div>
<div class="movie movie--preview">
  <a class="movie__title">Oppenheimer</a>
  <p class="movie__option"><strong>Lingua:</strong> Italiano</p>
  <div class="schedule-section-show">
    Modernissimo
    <ul>
      <li><a data-time="1780943400000">20:30</a></li>
    </ul>
  </div>
</div>
</body></html>
"""

MOCK_HTML_NO_SHOWTIMES = """
<html><body>
<div class="movie movie--preview">
  <a class="movie__title">Film senza orari</a>
  <div class="schedule-section-show">
    Nessuna proiezione oggi
  </div>
</div>
</body></html>
"""

MOCK_HTML_FALLBACK_DATE = """
<html><body>
<div class="movie movie--preview">
  <a class="movie__title">Film fallback</a>
  <div class="schedule-section-show">
    Sala A - Proiezioni Lunedi 08/06/2026
    Orari: 16:00, 19:00
  </div>
</div>
</body></html>
"""

MOCK_HTML_VARIANTS = """
<html><body>
<div class="movie movie--preview">
  <a class="movie__title">Spirited Away</a>
  <p class="movie__option"><strong>Lingua:</strong> Giapponese sub ita</p>
  <div class="schedule-section-show">
    Arena试
    <ul>
      <li><a data-time="1780923600000">15:00</a></li>
    </ul>
  </div>
</div>
<div class="movie movie--preview">
  <a class="movie__title">Il ladro di calamari</a>
  <p class="movie__option"><strong>Lingua:</strong> Italiano sub eng</p>
  <div class="schedule-section-show">
    Sala Berti
    <ul>
      <li><a data-time="1780943400000">20:30</a></li>
    </ul>
  </div>
</div>
</body></html>
"""
