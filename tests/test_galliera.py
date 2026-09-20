from __future__ import annotations

from datetime import date

from scrapers.galliera import find_agenda_url, parse_agenda

CATEGORY = """
<h2 class="entry-title"><a href="https://x.it/altro/">Altro post</a></h2>
<h2 class="entry-title"><a href="https://x.it/agenda-spettacoli-2026/">AGENDA SPETTACOLI 2026</a></h2>
"""

AGENDA = """
<div class="entry-content">
<p><strong>● domenica 20 settembre</strong> | promo<br />
<strong>ore 16:00 <a href="https://www.cinemateatrogalliera.it/calle-malaga/">CALLE MALAGA</a></strong> di Maryam Touzani | prima visione<br />
<strong>ore 21:00 <a href="https://www.cinemateatrogalliera.it/palestina-36/">PALESTINA 36</a> V.O.S.</strong> | prima visione</p>
<p>● lunedì 21 settembre<br />
ore 21:00 <span>ANTEPRIMA</span> <a href="https://www.cinemateatrogalliera.it/with-hasan-in-gaza/">WITH HASAN IN GAZA</a> V.O.S. di Kamal Aljafari</p>
<p>● martedì 22 settembre<br />ore 18:30 CALLE MALAGA di M. T.<br />ore 21:00 CALLE MALAGA</p>
<p>PROSSIMAMENTE &amp; IN ARRIVO</p>
<p>● da venerdì 25 settembre | PRIMA VISIONE<br />SANTIAGO UN CAMMINO</p>
</div>
"""

REF = date(2026, 9, 20)


def test_find_agenda_url():
    assert find_agenda_url(CATEGORY) == "https://x.it/agenda-spettacoli-2026/"


def test_find_agenda_url_assente():
    assert find_agenda_url("<html></html>") is None


def test_parse_agenda_giorni_e_titoli():
    result = parse_agenda(AGENDA, REF)
    assert {s.titolo for s in result[date(2026, 9, 20)]} == {
        "Calle Malaga",
        "Palestina 36",
    }
    assert date(2026, 9, 25) not in result  # sezione "prossimamente"


def test_parse_agenda_vos_e_label_anteprima():
    (s,) = parse_agenda(AGENDA, REF)[date(2026, 9, 21)]
    assert s.titolo == "With Hasan In Gaza"
    assert "V.O.S." in s.note
    assert s.url.endswith("/with-hasan-in-gaza/")


def test_parse_agenda_unisce_stesso_film_nello_stesso_giorno():
    (s,) = parse_agenda(AGENDA, REF)[date(2026, 9, 22)]
    assert s.orari == ["18:30", "21:00"]


def test_parse_agenda_senza_contenuto():
    assert parse_agenda("<html></html>", REF) == {}
