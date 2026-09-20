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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="web/static"), name="static")

app.include_router(api.router)
app.include_router(site.router)


def start_api_server() -> threading.Thread | None:
    """Avvia il server FastAPI in un thread daemon."""
    import uvicorn

    port = settings.health_port
    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=port,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    logger.info("API server in ascolto su http://0.0.0.0:%d", port)
    return thread
