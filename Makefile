PY := .venv/bin/python
PORT ?= 8000
HOST ?= 0.0.0.0

.PHONY: setup venv data web serve dev test clean

## one-shot: environment, source data, database, built UI
setup: venv data web
	@echo
	@echo "ready — run 'make serve' and open http://localhost:$(PORT)"

venv:
	python3 -m venv .venv
	$(PY) -m pip install --quiet --upgrade pip
	$(PY) -m pip install --quiet -r server/requirements.txt

## download the public-domain sources once, then build the SQLite database
data:
	$(PY) etl/fetch_sources.py
	$(PY) etl/build_db.py

web:
	cd web && npm install && npm run build

## production: one process serving the API and the built UI
serve:
	$(PY) -m uvicorn server.main:app --host $(HOST) --port $(PORT)

## development: API on 8000, Vite with hot reload on 5173
dev:
	$(PY) -m uvicorn server.main:app --reload --port 8000 & \
	cd web && npm run dev

test:
	$(PY) -m pip install --quiet -r server/requirements-dev.txt
	$(PY) -m unittest discover -s tests -v

clean:
	rm -rf data/concordance.db data/concordance.db-wal data/concordance.db-shm web/dist
