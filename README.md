# Cinema Bologna Bot

![CI](https://github.com/Priestomm/bologna-cinema-scraper/actions/workflows/ci.yml/badge.svg)

Bot Telegram che ogni mattina pubblica la programmazione cinematografica giornaliera di Bologna per quattro circuiti:

- **Cineteca di Bologna** (Lumiere, Modernissimo)
- **Pop Up Cinema**
- **Circuito Cinema Bologna** (Rialto, Odeon, Europa, Roma D'Azeglio)
- **Nuovo Cinema Nosadella** (Sala Berti, Sala Scalo)

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
|   `-- popup.py             # Pop Up Cinema (18tickets)
|-- database/
|   `-- cache.py             # cache SQLite degli snapshot giornalieri
|-- bot/
|   |-- pipeline.py          # orchestratore scraper -> cache
|   |-- scheduler.py         # APScheduler (07:30 scrape, 08:00 broadcast)
|   |-- formatter.py         # rendering messaggi Telegram (HTML)
|   |-- health.py            # health check HTTP server (/health)
|   `-- telegram_bot.py      # handler /cinema + lifecycle
|-- tests/                   # test unitari (pytest)
|   |-- conftest.py          # fixture + mock HTML
|   |-- test_formatter.py
|   |-- test_cache.py
|   `-- test_tickets18.py
|-- utils/
|   `-- logger.py            # logger con file rotante
|-- .github/workflows/ci.yml # CI: ruff + mypy + pytest
|-- requirements.txt
|-- .env.example
|-- ecosystem.config.js      # PM2
`-- deploy/cinema-bot.service # systemd
```

### Flusso operativo

1. **07:30** APScheduler avvia la pipeline: tutti gli scraper girano in parallelo, ognuno con timeout di 15s e isolamento errori.
2. Il risultato (incluse le note di errore per i circuiti caduti) viene scritto in `data/cache.sqlite3`.
3. **08:00** APScheduler legge la cache, rende il messaggio HTML e lo invia in chat.
4. In qualunque momento `/cinema` legge dalla cache (zero latenza, zero rischio di ban IP).

### Fault tolerance

- Ogni scraper gira in un thread isolato con `concurrent.futures` e timeout rigido configurabile.
- Le eccezioni sono catturate dentro `BaseScraper.run()`: il pipeline produce comunque un `ScraperResult` con `success=False` ed `error=...`.
- Il formatter aggiunge automaticamente in coda una sezione "Avvisi" con la lista dei circuiti non disponibili, senza interrompere il broadcast degli altri.

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
# modifica TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID
```

### Opzione Docker (consigliata per rapidita')

```bash
# build e avvia con Docker Compose
cp .env.example .env   # configura le credenziali
make docker-up

# oppure manualmente
docker compose up -d

# log
make docker-logs

# ferma
make docker-down
```

### Ottenere TELEGRAM_BOT_TOKEN e CHAT_ID

1. Scrivi a [@BotFather](https://t.me/BotFather), `/newbot`, copia il token.
2. Scrivi al tuo bot un messaggio qualunque (o aggiungilo a un gruppo).
3. `curl "https://api.telegram.org/bot<TOKEN>/getUpdates"` e copia `chat.id`.

## Uso

```bash
# Tutti i comandi rapidi disponibili
make help

# Avvia il bot in foreground
make run

# Solo scraping
make scrape

# Test invio reale
make broadcast
```

### Health Check & API REST

Il bot espone un server HTTP FastAPI sulla porta 8080 (configurabile via `HEALTH_PORT` in `.env`).

```bash
# Health check
curl http://localhost:8080/health

# Programmazione di oggi
curl http://localhost:8080/api/screenings

# Programmazione di una data specifica
curl "http://localhost:8080/api/screenings?date=2026-06-08"

# Elenco cinema disponibili
curl http://localhost:8080/api/cinemas

# Film di un cinema specifico
curl http://localhost:8080/api/cinemas/rialto

# Storico ultimi 7 giorni
curl http://localhost:8080/api/history

# Statistiche generali
curl http://localhost:8080/api/stats

# Documentazione interattiva (Swagger UI)
open http://localhost:8080/docs
```

#### Endpoints disponibili

| Endpoint | Descrizione |
|---|---|
| `GET /health` | Stato del bot (uptime, conteggio film, avvisi) |
| `GET /api/screenings?date=YYYY-MM-DD` | Programmazione per data |
| `GET /api/cinemas` | Elenco cinema con conteggio film |
| `GET /api/cinemas/{name}` | Film di un cinema specifico |
| `GET /api/history?days=N` | Programmazione ultimi N giorni (max 90) |
| `GET /api/stats` | Statistiche generali della cache |

### Deploy in background

### Opzione A - PM2 (consigliato per VPS)

```bash
# installa PM2 (richiede Node.js)
npm install -g pm2

# avvia
pm2 start ecosystem.config.js
pm2 save
pm2 startup     # genera lo snippet da eseguire come root (auto-start al boot)

# controllo
pm2 status
pm2 logs cinema-bologna-bot
pm2 restart cinema-bologna-bot
```

### Opzione B - systemd (Linux nativo)

```bash
sudo cp deploy/cinema-bot.service /etc/systemd/system/
# modifica User/WorkingDirectory dentro il file se necessario
sudo systemctl daemon-reload
sudo systemctl enable --now cinema-bot
sudo systemctl status cinema-bot
journalctl -u cinema-bot -f
```

### Opzione C - macOS launchd

Crea `~/Library/LaunchAgents/com.cinema.bot.plist` con il comando `python main.py` come `ProgramArguments`. `launchctl load -w ...`.

## Personalizzazione

- **Orari** scraping/broadcast: modifica `SCRAPE_CRON_*` / `BROADCAST_CRON_*` in `.env`.
- **Timeout** scraper: `SCRAPER_TIMEOUT` (default 15s).
- **Health check**: `HEALTH_PORT` (default 8080). Imposta a 0 per disabilitare.
- **Aggiungere un cinema**: crea `scrapers/nuovo.py` ereditando da `BaseScraper`, esponi la classe in `scrapers/__init__.py`, aggiungila ad `ALL_SCRAPERS`. Nient'altro.
- **Selettori HTML**: i siti cambiano. I parser sono volutamente difensivi ma se un circuito smette di restituire dati, l'unica cosa da modificare e' lo scraper relativo o il parser comune `_tickets18.py` (usato da Cineteca, Circuito Cinema, Pop Up e Nosadella).

## Note sui dati

I parser sfruttano pagine pubbliche server-rendered (tutti i cinema attualmente integrati usano la piattaforma 18tickets). Non viene fatto alcun login ne' bypass di paywall. Rispetta i `robots.txt` se imposti orari di refresh piu' aggressivi.

## Troubleshooting

| Sintomo | Causa probabile | Fix |
|---|---|---|
| `/cinema` risponde "Cache vuota" | Bot avviato la prima volta prima delle 07:30 | Esegui `python main.py --scrape` una volta, poi riavvia |
| Un circuito appare sempre in "Avvisi" | Selettori HTML cambiati o sito offline | Apri il sito, ispeziona la struttura, aggiorna lo scraper relativo |
| `Conflict: terminated by other getUpdates` | Due istanze del bot attive | `pm2 list` / `systemctl status`, killa la duplicata |
| Timeout frequenti | Rete lenta o sito sotto carico | Aumenta `SCRAPER_TIMEOUT` (max consigliato 30s) |
