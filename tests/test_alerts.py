from __future__ import annotations

from core.alerts import CircuitHealth


def test_alert_una_volta_sola_alla_soglia() -> None:
    health = CircuitHealth(threshold=3)
    for _ in range(2):
        health.record("chaplin", "Cinema Chaplin", "HTTP 503")
    assert health.drain() == []

    health.record("chaplin", "Cinema Chaplin", "HTTP 503")
    alerts = health.drain()
    assert [(a.kind, a.failures, a.error) for a in alerts] == [("down", 3, "HTTP 503")]

    # Oltre la soglia non ripete l'alert a ogni refresh.
    health.record("chaplin", "Cinema Chaplin", "HTTP 503")
    assert health.drain() == []


def test_ripresa_dopo_alert() -> None:
    health = CircuitHealth(threshold=2)
    health.record("uci", "UCI", "timeout")
    health.record("uci", "UCI", "timeout")
    health.drain()

    health.record("uci", "UCI", None)
    alerts = health.drain()
    assert [(a.kind, a.failures) for a in alerts] == [("recovered", 2)]


def test_successo_azzera_il_contatore_senza_alert() -> None:
    health = CircuitHealth(threshold=3)
    health.record("uci", "UCI", "timeout")
    health.record("uci", "UCI", "timeout")
    health.record("uci", "UCI", None)
    health.record("uci", "UCI", "timeout")
    health.record("uci", "UCI", "timeout")
    assert health.drain() == []


def test_circuiti_contati_separatamente() -> None:
    health = CircuitHealth(threshold=2)
    health.record("a", "A", "x")
    health.record("b", "B", "x")
    assert health.drain() == []


def test_messaggio_html_escapato() -> None:
    health = CircuitHealth(threshold=1)
    health.record("x", "Cinema <X>", "errore <html> & co")
    text = health.drain()[0].to_html()
    assert "&lt;X&gt;" in text
    assert "&lt;html&gt; &amp; co" in text
