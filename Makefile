PY := .venv/bin/python
PORT ?= 8000
# Loopback by default: there is no auth, so nothing gets exposed by accident.
# To reach it from your phone over the tailnet:
#   make serve HOST=0.0.0.0
HOST ?= 127.0.0.1

.PHONY: setup venv data web serve dev test clean reset

## one-shot: environment, source data, database, built UI
setup: venv data web
	@echo
	@echo "ready — run 'make serve' and open http://localhost:$(PORT)"

$(PY):
	python3 -m venv .venv
	$(PY) -m pip install --quiet --upgrade pip
	$(PY) -m pip install --quiet -r server/requirements.txt

venv: $(PY)

## download the public-domain sources once, then build the SQLite database
data: $(PY)
	$(PY) etl/fetch_sources.py
	$(PY) etl/build_db.py

web:
	cd web && npm ci && npm run build

## production: one process serving the API and the built UI, on $(HOST):$(PORT)
serve: $(PY)
	$(PY) -m uvicorn server.main:app --host $(HOST) --port $(PORT)

## development: API on 8000, Vite with hot reload on 5173. The trap takes the
## reloader down when Vite exits -- it stops its own worker on SIGTERM -- so
## port 8000 is free for the next run.
dev: $(PY)
	@$(PY) -m uvicorn server.main:app --reload --port 8000 & \
	api=$$!; \
	trap 'kill $$api 2>/dev/null; wait $$api 2>/dev/null' EXIT INT TERM; \
	cd web && npm run dev

test: $(PY)
	$(PY) -m pip install --quiet -r server/requirements-dev.txt
	$(PY) -m unittest discover -s tests -v

## build artifacts only: your notes live in data/concordance.db
clean:
	rm -rf web/dist
	find . -name __pycache__ -type d -prune -exec rm -rf {} +

## destructive: throws the database away, notes and all
reset: clean
	rm -f data/concordance.db data/concordance.db-wal data/concordance.db-shm
