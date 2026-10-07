"""Mini-sito HTML: programmazione cinematografica renderizzata con Jinja2.

- GET /                   mini-sito HTML (programmazione oggi)
- GET /{YYYY-MM-DD}       mini-sito HTML (programmazione per data)
- GET /partials/{date}    frammento HTML per il cambio giorno via JS (uso interno)
- GET /robots.txt         direttive per i crawler
- GET /sitemap.xml        sitemap (oggi + prossimi giorni con programmazione)

Le pagine rispondono anche a HEAD (monitor di uptime, alcuni crawler):
le route FastAPI dichiarate con @router.get rispondono 405 a HEAD.

SEO: title/description per giorno, canonical e URL assoluti da
settings.public_base_url, JSON-LD schema.org (ScreeningEvent per ogni
orario), noindex sui giorni passati o senza programmazione.
"""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import date, datetime, time, timedelta
from typing import Any

import pytz
from fastapi import APIRouter
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from config import settings
from core.pipeline import today
from database.cache import CacheSnapshot
from scrapers import ALL_SCRAPERS
from web import web_utils

templates = Jinja2Templates(directory="web/templates")

router = APIRouter(tags=["site"])

_TZ = pytz.timezone(settings.timezone)
_SITE_NAME = "BOS // Bologna on Screen"
_GET_HEAD = ["GET", "HEAD"]

# Unica fonte di verita' per le etichette giorno/mese in italiano, condivisa
# dal rendering pagina intera e dal frammento /partials/{date}.
_DAY_MAP = {
    "Monday": "Lunedì",
    "Tuesday": "Martedì",
    "Wednesday": "Mercoledì",
    "Thursday": "Giovedì",
    "Friday": "Venerdì",
    "Saturday": "Sabato",
    "Sunday": "Domenica",
}
_MONTH_MAP = {
    "January": "GENNAIO",
    "February": "FEBBRAIO",
    "March": "MARZO",
    "April": "APRILE",
    "May": "MAGGIO",
    "June": "GIUGNO",
    "July": "LUGLIO",
    "August": "AGOSTO",
    "September": "SETTEMBRE",
    "October": "OTTOBRE",
    "November": "NOVEMBRE",
    "December": "DICEMBRE",
}


def _normalize_title(title: str) -> str:
    """Normalizza il titolo per il raggruppamento film duplicati.
    Rimuove prefissi/suffissi OV, sottotitoli e varianti per unificare."""
    t = title.lower()
    # Toglie gli accenti ("è" -> "e"): alcuni siti scrivono "e'" al posto di "è"
    # e altrimenti "Dov'e' la fiesta" e "Dov'è la fiesta" non si unirebbero.
    t = "".join(
        c for c in unicodedata.normalize("NFKD", t) if not unicodedata.combining(c)
    )
    t = re.sub(r"\s*\(.*?\)\s*", " ", t)

    # Prima rimuovi prefissi VO
    for prefix in ("original version - ", "original version: ", "original: ", "v.o.: "):
        t = t.removeprefix(prefix)

    # Detect VO markers (dopo aver rimosso i prefissi)
    has_vo = bool(
        re.search(r"original version|versione originale|v\.?\s*o\.?|sub\s+(ita|eng)", t)
    )

    # Strip after " - " solo se la parte dopo contiene marcatori VO
    if " - " in t:
        before, after = t.rsplit(" - ", 1)
        if has_vo or re.search(
            r"v\.?\s*o\.?|original version|versione originale|sub\s+(ita|eng)", after
        ):
            t = before

    t = re.sub(r"\s*[-–]\s*versione originale\s*$", "", t)
    t = re.sub(r"\s*[-–]\s*original version\s*$", "", t)
    t = re.sub(r"\s*[-–]\s*v\.?\s*o\.?\s*$", "", t)
    t = re.sub(r"\s*[-–]\s*sub\s+(ita|eng)\s*$", "", t)
    # Strip common abbreviations (C.A., S.A., etc.)
    t = re.sub(r"\s+(?:c\.?a\.?|s\.?a\.?|s\.?p\.?a\.?)\s*$", "", t)
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    return " ".join(t.split())


def _normalize_poster_url(url: str | None) -> str:
    """Normalizza l'URL del poster TMDB togliendo la dimensione.
    /w500/abc.jpg -> /abc.jpg  (stessa immagine = stessa chiave)
    """
    if not url:
        return ""
    return re.sub(r"/(?:w\d+|original|preview)/", "/", url)


def _strip_vo_markers(title: str) -> str:
    """Rimuove marcatori VO/versione originale dal titolo normalizzato.
    Usato come chiave di raggruppamento: 'odissea' e 'odissea - v.o.'
    producono la stessa chiave.
    """
    t = title
    # Rimuovi suffissi VO dopo " - "
    t = re.sub(
        r"\s*[-–]\s*(?:v\.?\s*o\.?|original version|versione originale)\s*$",
        "",
        t,
        flags=re.IGNORECASE,
    )
    # Rimuovi prefissi VO all'inizio
    for prefix in ("original version - ", "original version: ", "original: ", "v.o.: "):
        t = t.removeprefix(prefix)
    t = t.strip(" -:")
    return t


def _is_vo(note: str) -> bool:
    """True se la proiezione e' in versione originale."""
    n = note.lower()
    return "vo" in n or "sub ita" in n or "sub eng" in n


def _build_film_list(
    snapshot: CacheSnapshot,
) -> tuple[list[dict], list[str], list[str]]:
    """Raggruppa gli screening in film unici con info complete.
    Restituisce (film_list, genres_sorted, cinema_names_sorted).
    """
    film_groups: dict[str, dict] = {}
    poster_to_key: dict[str, str] = {}

    for s in snapshot.screenings:
        if not s.titolo:
            continue

        norm_poster = _normalize_poster_url(s.poster_url_tmdb or s.poster_url)
        matched_key = None

        if norm_poster and norm_poster in poster_to_key:
            matched_key = poster_to_key[norm_poster]

        if matched_key is None:
            norm_title = _normalize_title(s.titolo)
            if not norm_title:
                continue
            group_key = _strip_vo_markers(norm_title)
            # Si confronta con il titolo normalizzato di ogni gruppo, non con la
            # sua chiave: i gruppi con poster sono indicizzati per URL del poster.
            for existing_key, existing in film_groups.items():
                existing_title = _strip_vo_markers(existing["normalized"])
                if group_key == existing_title:
                    matched_key = existing_key
                    break
                short, long = (
                    (group_key, existing_title)
                    if len(group_key) <= len(existing_title)
                    else (existing_title, group_key)
                )
                if long.startswith(short + " "):
                    matched_key = existing_key
                    break
                if len(short) >= 15 and short in long:
                    matched_key = existing_key
                    break

        if matched_key is None:
            norm_title = _normalize_title(s.titolo)
            matched_key = norm_poster or _strip_vo_markers(norm_title)
            display_title = s.clean_title_tmdb or s.titolo
            film_groups[matched_key] = {
                "titolo": display_title,
                "normalized": norm_title,
                "poster_url": s.poster_url_tmdb or s.poster_url,
                "rating": s.rating,
                "genre": s.genre,
                "overview": s.overview,
                "runtime": s.runtime,
                "regista": s.regista,
                "cinemas": {},
            }
            if norm_poster:
                poster_to_key[norm_poster] = matched_key

        fg = film_groups[matched_key]

        if s.clean_title_tmdb and not fg["titolo"]:
            fg["titolo"] = s.clean_title_tmdb
        if s.poster_url_tmdb and not fg["poster_url"]:
            fg["poster_url"] = s.poster_url_tmdb
        if s.poster_url and not fg["poster_url"]:
            fg["poster_url"] = s.poster_url
        if s.rating and not fg["rating"]:
            fg["rating"] = s.rating
        if s.genre and not fg["genre"]:
            fg["genre"] = s.genre
        if s.overview and not fg["overview"]:
            fg["overview"] = s.overview
        if s.runtime and not fg["runtime"]:
            fg["runtime"] = s.runtime
        if s.regista and not fg["regista"]:
            fg["regista"] = s.regista

        cinema_key = s.cinema
        vo_flag = _is_vo(s.note)
        if cinema_key not in fg["cinemas"]:
            fg["cinemas"][cinema_key] = {
                "name": s.cinema,
                "times": [],
            }
        for ora in s.orari:
            fg["cinemas"][cinema_key]["times"].append(
                {
                    "ora": ora,
                    "vo": vo_flag,
                    "url": s.times_urls.get(ora, s.url),
                }
            )

    all_cinema_names: set[str] = set()
    for fg in film_groups.values():
        for cinema in fg["cinemas"].values():
            cinema["times"].sort(key=lambda t: t["ora"])
            all_cinema_names.add(cinema["name"])
        cinema_list = list(fg["cinemas"].values())
        cinema_list.sort(key=lambda c: len(c["times"]), reverse=True)
        fg["cinemas"] = cinema_list
        # Orario piu' presto tra tutti i cinema (non solo il primo cinema
        # della lista, che e' ordinata per numero di orari): usato per
        # l'ordinamento "per orario" lato sito.
        all_times = [t["ora"] for c in cinema_list for t in c["times"]]
        fg["earliest_time"] = min(all_times) if all_times else "99:99"

    film_list = sorted(film_groups.values(), key=lambda f: f["titolo"].lower())

    all_genres: set[str] = set()
    for fg in film_list:
        if fg["genre"]:
            for g in fg["genre"].split("/"):
                g = g.strip()
                if g:
                    all_genres.add(g)
    genres_sorted = sorted(all_genres, key=str.lower)
    cinema_names_sorted = sorted(all_cinema_names, key=str.lower)

    return film_list, genres_sorted, cinema_names_sorted


def _day_label(d: date) -> str:
    """ "mercoledi' 7 ottobre": per title, description e h1."""
    weekday = _DAY_MAP[d.strftime("%A")].lower()
    return f"{weekday} {d.day} {_MONTH_MAP[d.strftime('%B')].lower()}"


def _seo_title(target: date) -> str:
    label = _day_label(target)
    if target == today():
        return f"Cinema a Bologna oggi, {label}: film e orari | BOS"
    return f"Cinema a Bologna {label}: film e orari | BOS"


def _seo_description(target: date, film_count: int) -> str:
    when = "oggi" if target == today() else _day_label(target)
    circuits = ", ".join(cls.name for cls in ALL_SCRAPERS[:-1])
    circuits += f" e {ALL_SCRAPERS[-1].name}"
    if film_count:
        return (
            f"{film_count} film in programmazione a Bologna {when}: "
            f"tutti gli orari di {circuits}."
        )
    return f"Programmazione dei cinema di Bologna {when}: {circuits}."


def _page_path(target: date) -> str:
    """Path canonico: oggi e' "/", gli altri giorni "/YYYY-MM-DD"."""
    return "/" if target == today() else f"/{target.isoformat()}"


def _jsonld(request: Request, target: date, films: list[dict]) -> str:
    """JSON-LD schema.org: il sito + un ScreeningEvent per ogni orario.

    L'indirizzo e' solo provincia/paese: le sale non hanno (ancora) un
    indirizzo nei dati, e uno inventato sarebbe peggio di uno parziale.
    """
    graph: list[dict[str, Any]] = [
        {
            "@type": "WebSite",
            "name": _SITE_NAME,
            "url": web_utils.absolute_url(request, "/"),
            "inLanguage": "it-IT",
        }
    ]
    page_url = web_utils.absolute_url(request, _page_path(target))
    theater_ids: dict[str, str] = {}

    def theater_ref(name: str) -> dict[str, str]:
        """Sala descritta una volta sola, poi richiamata per @id."""
        if name not in theater_ids:
            theater_ids[name] = f"{page_url}#sala-{len(theater_ids)}"
            graph.append(
                {
                    "@type": "MovieTheater",
                    "@id": theater_ids[name],
                    "name": name,
                    "address": {
                        "@type": "PostalAddress",
                        "addressRegion": "BO",
                        "addressCountry": "IT",
                    },
                }
            )
        return {"@id": theater_ids[name]}

    for i, film in enumerate(films):
        # Il film e' descritto una volta sola e ogni orario lo richiama per
        # @id: ripeterlo per proiezione triplicava il peso del JSON-LD.
        movie_id = f"{page_url}#film-{i}"
        movie: dict[str, Any] = {
            "@type": "Movie",
            "@id": movie_id,
            "name": film["titolo"],
        }
        if film["poster_url"]:
            movie["image"] = film["poster_url"]
        directors = [d.strip() for d in (film["regista"] or "").split(",")]
        if any(directors):
            movie["director"] = [{"@type": "Person", "name": d} for d in directors if d]
        if film["runtime"]:
            movie["duration"] = f"PT{film['runtime']}M"
        if film["genre"]:
            movie["genre"] = [g.strip() for g in film["genre"].split("/") if g.strip()]
        graph.append(movie)

        for cinema in film["cinemas"]:
            for t in cinema["times"]:
                try:
                    hh, mm = (int(x) for x in t["ora"].split(":"))
                    start = _TZ.localize(datetime.combine(target, time(hh, mm)))
                except ValueError:
                    continue
                event: dict[str, Any] = {
                    "@type": "ScreeningEvent",
                    "name": film["titolo"],
                    "startDate": start.isoformat(),
                    "eventStatus": "https://schema.org/EventScheduled",
                    "eventAttendanceMode": (
                        "https://schema.org/OfflineEventAttendanceMode"
                    ),
                    "location": theater_ref(cinema["name"]),
                    "workPresented": {"@id": movie_id},
                }
                if t["url"]:
                    event["offers"] = {"@type": "Offer", "url": t["url"]}
                graph.append(event)

    payload = {"@context": "https://schema.org", "@graph": graph}
    # "</" spezzato: un titolo con "</script>" non deve chiudere il tag.
    return json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")


def _build_day_context(target: date) -> dict[str, Any]:
    """Contesto Jinja per un giorno: usato sia dalla pagina piena
    (_schedule_page) sia dal frammento servito da /partials/{date_param},
    cosi' entrambi leggono la programmazione con la stessa logica.
    """
    snapshot = web_utils.get_cache().load(target)
    context: dict[str, Any] = {
        "date": target.isoformat(),
        "date_obj": target,
        "today": today(),
        "day_map": _DAY_MAP,
        "month_map": _MONTH_MAP,
        "day_label": _day_label(target),
        "seo_title": _seo_title(target),
    }
    if snapshot is None:
        context.update(
            {
                "updated_at": "",
                "films": [],
                "genres": [],
                "cinema_names": [],
                "warnings": ["Nessun dato disponibile per questa data."],
            }
        )
        return context

    film_list, genres_sorted, cinema_names_sorted = _build_film_list(snapshot)
    context.update(
        {
            "updated_at": snapshot.updated_at.strftime("%H:%M"),
            "films": film_list,
            "genres": genres_sorted,
            "cinema_names": cinema_names_sorted,
            "warnings": snapshot.warnings,
        }
    )
    return context


def _date_params(target: date) -> dict[str, str]:
    prev = (target - timedelta(days=1)).isoformat()
    nxt = (target + timedelta(days=1)).isoformat()
    label = "Oggi" if target == today() else target.isoformat()
    return {"prev": prev, "next": nxt, "label": label}


def _seo_context(request: Request, target: date, films: list[dict]) -> dict[str, Any]:
    # I giorni passati restano navigabili ma non indicizzati: orari scaduti,
    # e pagine che crescerebbero all'infinito. Idem i giorni senza dati.
    indexable = target >= today() and bool(films)
    return {
        "title": _seo_title(target),
        "description": _seo_description(target, len(films)),
        "canonical": web_utils.absolute_url(request, _page_path(target)),
        "image": web_utils.absolute_url(request, "/static/og-image.jpg"),
        "robots": "" if indexable else "noindex, follow",
        "jsonld": _jsonld(request, target, films) if indexable else "",
    }


def _schedule_page(request: Request, target: date) -> HTMLResponse:
    context = _build_day_context(target)
    context.update(_date_params(target))
    context["refresh_interval_minutes"] = settings.refresh_interval_minutes
    context["seo"] = _seo_context(request, target, context["films"])
    return templates.TemplateResponse(
        request=request, name="schedule.html", context=context
    )


@router.api_route("/", methods=_GET_HEAD, response_class=HTMLResponse)
def schedule_today(request: Request) -> HTMLResponse:
    return _schedule_page(request, today())


@router.get(
    "/partials/{date_param}", response_class=HTMLResponse, include_in_schema=False
)
def schedule_partial(request: Request, date_param: str) -> HTMLResponse:
    """Frammento HTML per il cambio giorno via JS (vedi schedule.html).
    Non e' una route a singolo segmento come "/{date_param}" quindi non
    collide con la catch-all qui sotto, ma resta comunque vicino alle altre
    route del mini-sito per chiarezza."""
    try:
        target = web_utils.parse_date(date_param)
    except ValueError:
        return HTMLResponse("Data non valida", status_code=400)
    if not web_utils.in_window(target):
        return HTMLResponse("Data fuori programmazione", status_code=404)
    context = _build_day_context(target)
    return templates.TemplateResponse(
        request=request, name="_day_fragment.html", context=context
    )


# Route statiche registrate PRIMA della catch-all "/{date_param}" qui sotto:
# essendo un singolo segmento di path, "/{date_param}" matcherebbe anche
# "/robots.txt" o "/sitemap.xml" (Starlette valuta le route nell'ordine in
# cui sono registrate), trattandoli come una data non valida.


@router.api_route(
    "/robots.txt",
    methods=_GET_HEAD,
    response_class=PlainTextResponse,
    include_in_schema=False,
)
def robots_txt(request: Request) -> PlainTextResponse:
    # /partials/ duplica le pagine dei giorni; API e Swagger non sono pagine.
    body = (
        "User-agent: *\n"
        "Disallow: /partials/\n"
        "Disallow: /api/\n"
        "Disallow: /docs\n"
        "Disallow: /redoc\n"
        "Disallow: /openapi.json\n"
        f"Sitemap: {web_utils.absolute_url(request, '/sitemap.xml')}\n"
    )
    return PlainTextResponse(body)


@router.api_route(
    "/sitemap.xml",
    methods=_GET_HEAD,
    response_class=Response,
    include_in_schema=False,
)
def sitemap_xml(request: Request) -> Response:
    """Solo le pagine indicizzabili: oggi ("/") e i prossimi giorni con
    programmazione, con lastmod = ultimo aggiornamento della cache."""
    today_ = today()
    entries = []
    for i in range(7):
        d = today_ + timedelta(days=i)
        snapshot = web_utils.get_cache().load(d)
        if snapshot is None or snapshot.is_empty:
            continue
        loc = web_utils.absolute_url(request, _page_path(d))
        lastmod = snapshot.updated_at.isoformat(timespec="seconds")
        entries.append(f"<url><loc>{loc}</loc><lastmod>{lastmod}</lastmod></url>")
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"{''.join(entries)}</urlset>"
    )
    return Response(content=xml, media_type="application/xml")


@router.api_route(
    "/{date_param}",
    methods=_GET_HEAD,
    response_class=HTMLResponse,
    name="schedule_date",
)
def schedule_date(request: Request, date_param: str) -> HTMLResponse:
    try:
        target = web_utils.parse_date(date_param)
    except ValueError:
        return HTMLResponse("Data non valida", status_code=400)
    if not web_utils.in_window(target):
        return HTMLResponse("Data fuori programmazione", status_code=404)
    return _schedule_page(request, target)
