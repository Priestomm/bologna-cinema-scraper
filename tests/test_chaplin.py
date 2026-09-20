from __future__ import annotations

from datetime import date

from scrapers.chaplin import parse_film_links, parse_film_page

HOME = """
<article class="df-post-item category-in-programma">
  <h2 class="df-post-title"><a href="https://cinemachaplin.it/dove-la-fiesta/">Dov&#8217;è la fiesta?</a></h2>
</article>
<article class="df-post-item category-prossimamente">
  <h2 class="df-post-title"><a href="https://cinemachaplin.it/presto/">Presto</a></h2>
</article>
"""

FILM = """
<html><head>
<meta property="og:title" content="Dov&#039;è la fiesta? - Cinema Chaplin" />
<meta property="og:image" content="https://cinemachaplin.it/locandina.jpg" />
</head><body>
<div class="et_pb_toggle_item">
  <h5 class="et_pb_toggle_title">Orari e giorni programmazione</h5>
  <div class="et_pb_toggle_content"><p>Giovedì 17 settembre<br />
  16:30-18:45-21:00 <br /> prezzi interi € 9.00 ridotti € 7.00</p>
  <p>Lunedì 21 settembre<br /> Chiuso per Riposo..!!</p>
  <p>Martedì 22 settembre<br /> 18.45-21:00 <br /> prezzo unico € 3.50</p></div>
</div></body></html>
"""


def test_parse_film_links_only_in_programma():
    assert parse_film_links(HOME) == ["https://cinemachaplin.it/dove-la-fiesta/"]


def test_parse_film_page_orari_senza_prezzi():
    result = parse_film_page(FILM, "https://cinemachaplin.it/x/", date(2026, 9, 20))
    assert result[date(2026, 9, 17)].orari == ["16:30", "18:45", "21:00"]
    assert result[date(2026, 9, 22)].orari == ["18:45", "21:00"]


def test_parse_film_page_ignora_giorni_di_chiusura():
    result = parse_film_page(FILM, "https://cinemachaplin.it/x/", date(2026, 9, 20))
    assert date(2026, 9, 21) not in result


def test_parse_film_page_metadati():
    s = parse_film_page(FILM, "https://cinemachaplin.it/x/", date(2026, 9, 20))[
        date(2026, 9, 17)
    ]
    assert s.titolo == "Dov'è la fiesta?"
    assert s.poster_url == "https://cinemachaplin.it/locandina.jpg"
    assert s.cinema == "Cinema Chaplin"


def test_parse_film_page_senza_blocco_orari():
    assert parse_film_page("<html></html>", "u", date(2026, 9, 20)) == {}
