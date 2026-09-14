# Cinema Bologna Bot

![CI](https://github.com/Priestomm/bologna-cinema-scraper/actions/workflows/ci.yml/badge.svg)
![Status](https://img.shields.io/badge/status-%20active-success?logo=oracle)

Bot Telegram + mini-sito web con la programmazione cinematografica giornaliera di Bologna per cinque circuiti, attivo 24/7 su Oracle Cloud:

- **Cineteca di Bologna** (Lumiere, Modernissimo)
- **Pop Up Cinema** (Jolly, Arlecchino, Medica)
- **Circuito Cinema Bologna** (Rialto, Odeon, Europa, Roma D'Azeglio)
- **Nuovo Cinema Nosadella** (Sala Berti, Sala Scalo)
- **UCI Cinemas Meridiana** (Bologna)

## Funzionalita'

### Mini-sito web
Pagina web interattiva con:
- **Card film** con locandina, rating, generi e orari per cinema
- **Modale poster**: cliccando su una locandina si apre una vista ingrandita con sinossi (TMDb), regista, durata e generi
- **Filtri** per cinema e genere
- **Ordinamento** per ora, titolo o cinema
- **Date navigation**: barra per navigare tra i prossimi 7 giorni
- **Aggiornamento automatico** ogni 15 minuti

### Enrichment TMDb
Ogni film viene cercato su TMDb per ottenere:
- Rating medio (0-10)
- Genere
- Locandina ad alta risoluzione
- Titolo pulito (dalla versione TMDb)
- Sinossi / overview
- Durata in minuti

I dati vengono cachati localmente (TTL 7 giorni) per evitare chiamate API ripetute.

### Link di acquisto
- **18tickets** (Cineteca, Pop Up, Circuito, Nosadella): ogni orario linka direttamente alla pagina di acquisto con UUID della proiezione e hash della data (`#YYYY-MM-DD`)
- **UCI Cinemas**: link diretto al carrello (`cart_link` dall'API UCI) con fallback a `?film={slug}&date=YYYY-MM-DD`

### Bot Telegram
- Broadcast giornaliero della programmazione in chat
- Comando `/cinema` per consultare la cache istantaneamente
- Lettura sempre dalla cache (zero latenza, zero rischio ban IP)

## Architettura

```
.
|-- main.py                  # entry point (bot | --scrape | --broadcast)
|-- Makefile                 # comandi rapidi (test, lint, docker...)
|-- Dockerfile               # containerizzazione
|-- docker-compose.yml       # avvio con Docker Compose
|-- config/
|   `-- settings.py          # carica .env, costanti di sistema
|-- scrapers/
|   |-- base.py              # BaseScraper + modello Screening
|   |-- _tickets18.py        # parser condiviso piattaforma 18tickets
|   |-- cineteca.py          # Cineteca (18tickets)
|   |-- circuito.py          # Circuito Cinema (18tickets, multi-sala)
|   |-- nosadella.py         # Nuovo Cinema Nosadella (18tickets)
|   |-- popup.py             # Pop Up Cinema (18tickets)
|   |-- uci.py               # UCI Cinemas (API JSON)
|   `-- tmdb.py              # client TMDb con cache SQLite
|-- database/
|   `-- cache.py             # cache SQLite degli snapshot giornalieri
|-- bot/
|   |-- pipeline.py          # orchestratore scraper -> enrichment -> cache
|   |-- scheduler.py         # APScheduler (scrape + broadcast)
|   |-- formatter.py         # rendering messaggi Telegram (HTML)
|   |-- health.py            # FastAPI: mini-sito + API REST + health check
|   |-- telegram_bot.py      # handler /cinema + lifecycle
|   `-- templates/
|       `-- schedule.html    # template Jinja2 per il mini-sito
|-- tests/                   # test unitari (pytest)
|-- utils/
|   `-- logger.py            # logger con file rotante
|-- .github/workflows/ci.yml # CI: ruff + mypy + pytest
|-- requirements.txt
|-- .env.example
`-- ecosystem.config.js      # PM2
```

### Flusso operativo

1. **Scraping**: tutti gli scraper girano in parallelo, ognuno con timeout configurabile e isolamento errori.
2. **Enrichment TMDb**: rating, generi, poster, sinossi e durata vengono aggiunti a ogni film.
3. **Cache**: il risultato (incluse le note di errore per i circuiti caduti) viene scritto in `data/cache.sqlite3`.
4. **Broadcast**: il bot legge dalla cache, rende il messaggio HTML e lo invia in chat.
5. **Mini-sito**: il server FastAPI legge dalla cache per servire la pagina web e le API REST.

### Fault tolerance

- Ogni scraper gira in un thread isolato con `concurrent.futures` e timeout rigido configurabile.
- Le eccezioni sono catturate dentro `BaseScraper.run()`: il pipeline produce comunque un `ScraperResult` con `success=False` ed `error=...`.
- Il formatter aggiunge automaticamente in coda una sezione "Avvisi" con la lista dei circuiti non disponibili.

## Installazione

```bash
# 1. clona/copia il progetto, poi
cd scraper-cinema-bologna
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# oppure con Make
make install

# 2. configura le credenziali
cp .env.example .env
# modifica TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID e TMDB_API_KEY
```

### Variabili d'ambiente

| Variabile | Default | Descrizione |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | *(richiesto)* | Token da @BotFather |
| `TELEGRAM_CHAT_ID` | *(richiesto)* | Chat ID di destinazione |
| `TMDB_API_KEY` | *(opzionale)* | Chiave API TMDb per rating/sinossi |
| `SCRAPE_CRON_HOUR` / `MINUTE` | 7:30 | Orario scraping giornaliero |
| `BROADCAST_CRON_HOUR` / `MINUTE` | 8:00 | Orario broadcast Telegram |
| `SCRAPER_TIMEOUT` | 15 | Timeout per singolo scraper (secondi) |
| `HEALTH_PORT` | 8080 | Porta del server web (0 = disabilitato) |
| `REFRESH_INTERVAL_MINUTES` | 15 | Intervallo auto-refresh mini-sito |
| `CACHE_DB_PATH` | data/cache.sqlite3 | Path della cache SQLite |
| `LOG_LEVEL` | INFO | Livello di logging |

### Docker

```bash
cp .env.example .env   # configura le credenziali
make docker-up         # build + avvia

make docker-logs       # log
make docker-down       # ferma
```

### Ottenere TELEGRAM_BOT_TOKEN e CHAT_ID

1. Scrivi a [@BotFather](https://t.me/BotFather), `/newbot`, copia il token.
2. Scrivi al tuo bot un messaggio qualunque (o aggiungilo a un gruppo).
3. `curl "https://api.telegram.org/bot<TOKEN>/getUpdates"` e copia `chat.id`.

### Ottenere TMDB_API_KEY

1. Crea un account su [themoviedb.org](https://www.themoviedb.org/)
2. Vai su Settings > API e richiedi una chiave gratuita

## Uso

```bash
# Tutti i comandi rapidi disponibili
make help

# Avvia il bot in foreground
make run

# Solo scraping (singolo giorno)
make scrape

# Scraping multi-giorno (7 giorni, consigliato)
python main.py --scrape --days 7

# Test invio reale
make broadcast
```

### Health Check, Mini-sito & API REST

Il bot espone un server HTTP FastAPI sulla porta 8080:

```bash
# Mini-sito (pagina HTML navigabile)
open http://localhost:8080/

# Data specifica
open http://localhost:8080/2026-09-15

# Health check
curl http://localhost:8080/health

# Programmazione di oggi
curl http://localhost:8080/api/screenings

# Programmazione di una data specifica
curl "http://localhost:8080/api/screenings?date=2026-09-15"

# Elenco cinema disponibili
curl http://localhost:8080/api/cinemas

# Film di un cinema specifico
curl http://localhost:8080/api/cinemas/rialto

# Storico ultimi 7 giorni
curl http://localhost:8080/api/history

# Statistiche generali
curl http://localhost:8080/api/stats

# Forza refresh dati
curl -X POST http://localhost:8080/api/refresh

# Stato del refresh
curl http://localhost:8080/api/refresh/status

# Documentazione interattiva (Swagger UI)
open http://localhost:8080/docs
```

#### Endpoints disponibili

| Endpoint | Descrizione |
|---|---|
| `GET /` | Mini-sito HTML — programmazione di oggi |
| `GET /{YYYY-MM-DD}` | Mini-sito HTML — programmazione di una data |
| `GET /health` | Stato del bot (uptime, conteggio film, avvisi) |
| `GET /api/screenings?date=YYYY-MM-DD` | Programmazione per data |
| `GET /api/cinemas` | Elenco cinema con conteggio film |
| `GET /api/cinemas/{name}` | Film di un cinema specifico |
| `GET /api/history?days=N` | Programmazione ultimi N giorni (max 90) |
| `GET /api/stats` | Statistiche generali della cache |
| `POST /api/refresh` | Forza refresh dati dagli scraper |
| `GET /api/refresh/status` | Stato del refresh in corso |

### Deploy

#### PM2 (consigliato per VPS)

```bash
npm install -g pm2
pm2 start ecosystem.config.js
pm2 save
pm2 startup     # auto-start al boot
pm2 status
pm2 logs cinema-bologna-bot
```

#### Docker Compose

```bash
docker compose up -d
docker compose logs -f
docker compose down
```

#### Oracle Cloud (VM sempre attiva)

Il bot e' attualmente ospitato su una VM Oracle Cloud (always-free tier) con PM2.

```bash
git clone https://github.com/Priestomm/bologna-cinema-scraper.git
cd bologna-cinema-scraper
make install
cp .env.example .env
# configura le credenziali
pm2 start ecosystem.config.js
pm2 save
pm2 startup
```

## Personalizzazione

- **Orari** scraping/broadcast: modifica `SCRAPE_CRON_*` / `BROADCAST_CRON_*` in `.env`.
- **Timeout** scraper: `SCRAPER_TIMEOUT` (default 15s).
- **Health check**: `HEALTH_PORT` (default 8080). Imposta a 0 per disabilitare.
- **Aggiungere un cinema**: crea `scrapers/nuovo.py` ereditando da `BaseScraper`, esponi la classe in `scrapers/__init__.py`, aggiungila ad `ALL_SCRAPERS`.
- **Selettori HTML**: i siti cambiano. I parser sono volutamente difensivi ma se un circuito smette di restituire dati, modifica lo scraper relativo o il parser comune `_tickets18.py`.

## Note sui dati

- I parser per Cineteca, Pop Up, Circuito Cinema e Nosadella sfruttano pagine pubbliche server-rendered della piattaforma 18tickets.
- UCI Cinemas espone un'API REST JSON pubblica.
- TMDb viene usato solo per arricchire i dati (rating, generi, poster, sinossi, durata). Nessun dato utente viene inviato.
- Non viene fatto alcun login ne' bypass di paywall.

## Troubleshooting

| Sintomo | Causa probabile | Fix |
|---|---|---|
| `/cinema` risponde "Cache vuota" | Bot avviato prima dello scraping | `python main.py --scrape --days 7` |
| Un circuito appare in "Avvisi" | Selettori HTML cambiati o sito offline | Aggiorna lo scraper relativo |
| Film senza rating/sinossi | TMDB_API_KEY mancante o scaduta | Verifica la chiave in `.env` |
| Link di acquisto sbagliati (18tickets) | Il sito ha cambiato struttura URL | Controlla il parser `_tickets18.py` |
| `Conflict: terminated by other getUpdates` | Due istanze del bot attive | `pm2 list` / `systemctl status`, killa la duplicata |
| Timeout frequenti | Rete lenta o sito sotto carico | Aumenta `SCRAPER_TIMEOUT` |
