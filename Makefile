PYTHON ?= python3
NPM ?= npm
SEMGREP ?= $(shell $(PYTHON) -c 'import shutil, sysconfig; print(shutil.which("semgrep") or (sysconfig.get_path("scripts") + "/semgrep"))')
export PYTHONPATH := $(CURDIR)

.PHONY: bootstrap test lint format contracts sast migrate api-dev web-dev compose-up worker-placeholder

bootstrap:
	$(PYTHON) -m pip install -r apps/api/requirements.txt
	$(PYTHON) -m pip install -e ".[dev]"
	$(NPM) install

test:
	$(PYTHON) -m pytest

lint:
	$(PYTHON) -m ruff check .
	$(NPM) --workspace apps/web run lint

sast:
	$(PYTHON) -m bandit -r apps lib workers scripts
	$(SEMGREP) scan --config auto --exclude archive
	$(PYTHON) -m pyright apps lib workers scripts
	$(PYTHON) -m mypy apps/api lib workers scripts

format:
	$(PYTHON) -m ruff format .
	$(PYTHON) -m ruff check . --fix

contracts:
	$(PYTHON) scripts/validate_contracts.py

migrate:
	$(PYTHON) scripts/migrate.py

api-dev:
	uvicorn apps.api.structura_api.main:app --reload --host 0.0.0.0 --port 8000

web-dev:
	$(NPM) --workspace apps/web run dev -- --host 0.0.0.0

compose-up:
	docker compose up postgres api web

worker-placeholder:
	$(PYTHON) -m workers.placeholder --worker worker-local
