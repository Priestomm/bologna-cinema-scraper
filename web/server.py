"""Assembla l'app FastAPI (health check + API REST + mini-sito) e la avvia
su una porta dedicata (default 8080). Vedi web/api.py e web/site.py per le
singole route.

L'ordine di `include_router` conta: /health e /api/* devono essere
registrate PRIMA del router del mini-sito, perche' "/{date_param}"
(la catch-all a singolo segmento di web/site.py) altrimenti intercetterebbe
"/health" trattandolo come una data non valida.
"""

from __future__ import annotations

import threading

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from config import settings
from utils import get_logger
from web import api, site

logger = get_logger("web.server")

app = FastAPI(
    title="Cinema Bologna Bot",
    description="Health check + API REST + mini-sito per la programmazione cinematografica di Bologna",
    version="1.0.0",
)

# API in sola lettura aperta a qualunque origine; l'unico POST
# (/api/refresh) e' un comando amministrativo da chiamare server-to-server,
# non da un browser su un altro dominio.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
)

app.mount("/static", StaticFiles(directory="web/static"), name="static")

app.include_router(api.router)
app.include_router(site.router)


def _uvicorn_server() -> uvicorn.Server:
    config = uvicorn.Config(
        app,
        host=settings.web_host,
        port=settings.health_port,
        log_level="warning",
        access_log=False,
    )
    return uvicorn.Server(config)


def start_api_server() -> threading.Thread:
    """Avvia il server in un thread daemon dentro il processo del bot
    (modalita' tutto-in-uno: `python main.py` senza flag, usata da Docker)."""
    server = _uvicorn_server()
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    logger.info(
        "API server in ascolto su http://%s:%d", settings.web_host, settings.health_port
    )
    return thread


def run_api_server() -> None:
    """Avvia il server in primo piano, come processo a se' (`main.py --web`):
    se muore, PM2 lo vede e lo riavvia senza toccare il bot."""
    logger.info(
        "API server in ascolto su http://%s:%d", settings.web_host, settings.health_port
    )
    _uvicorn_server().run()
