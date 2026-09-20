"""Helper testuali condivisi dagli scraper."""

from __future__ import annotations


def titlecase_it(title: str) -> str:
    """Porta un titolo scritto TUTTO MAIUSCOLO a "Come Negli Altri".

    Non usa `str.title()` perche' rovinerebbe gli apostrofi ("Dov'E'").
    """
    return " ".join(w[:1].upper() + w[1:].lower() for w in title.split())
