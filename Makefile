.PHONY: help install test lint format typecheck run scrape broadcast docker-build docker-up docker-down docker-logs

help: ## Mostra tutti i comandi disponibili
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-18s\033[0m %s\n", $$1, $$2}'

install: ## Installa le dipendenze (dev incluse)
	pip install -r requirements.txt

test: ## Esegui tutti i test
	python -m pytest tests/ -v

lint: ## Rileva errori di stile (ruff)
	ruff check .

format: ## Formatta il codice
	ruff format .
	ruff check . --fix

typecheck: ## Controllo tipi con mypy
	mypy --ignore-missing-imports .

run: ## Avvia il bot in foreground
	python main.py

scrape: ## Esegui solo uno scrape
	python main.py --scrape

broadcast: ## Esegui scrape + invio messaggio
	python main.py --broadcast

docker-build: ## Build dell'immagine Docker
	docker build -t cinema-bologna-bot .

docker-up: ## Avvia con Docker Compose
	docker compose up -d

docker-down: ## Ferma Docker Compose
	docker compose down

docker-logs: ## Mostra log di Docker Compose
	docker compose logs -f

health: ## Test dell'health check endpoint
	curl -s http://localhost:8080/health | python -m json.tool

api: ## Mostra la documentazione API (Swagger UI)
	@echo "Apri http://localhost:8080/docs nel browser"

screenings: ## Mostra la programmazione di oggi via API
	curl -s http://localhost:8080/api/screenings | python -m json.tool
