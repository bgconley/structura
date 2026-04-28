PYTHON ?= python3
NPM ?= npm
SEMGREP ?= $(shell $(PYTHON) -c 'import shutil, sysconfig; print(shutil.which("semgrep") or (sysconfig.get_path("scripts") + "/semgrep"))')
PYRIGHT_PYTHON ?= $(shell command -v $(PYTHON) 2>/dev/null || printf '%s' '$(PYTHON)')
export PYTHONPATH := $(CURDIR)

.PHONY: bootstrap test integration-test lint format contracts sast migrate golden-corpus backup-restore-rehearsal release-readiness api-dev web-dev compose-up worker-placeholder

bootstrap:
	$(PYTHON) -m pip install -r requirements-dev.lock
	$(PYTHON) -m pip install -e . --no-deps
	$(NPM) install

test:
	$(PYTHON) -m pytest

integration-test:
	$(PYTHON) scripts/run_integration_tests.py

lint:
	$(PYTHON) -m ruff check .
	$(NPM) --workspace apps/web run lint

sast:
	$(PYTHON) -m bandit -r apps lib workers scripts
	$(SEMGREP) scan --config auto --exclude archive
	$(PYTHON) -m pyright --pythonpath $(PYRIGHT_PYTHON) apps lib workers scripts
	$(PYTHON) -m mypy apps/api lib workers scripts

format:
	$(PYTHON) -m ruff format .
	$(PYTHON) -m ruff check . --fix

contracts:
	$(PYTHON) scripts/validate_contracts.py

golden-corpus:
	$(PYTHON) scripts/run_golden_corpus.py

backup-restore-rehearsal:
	$(PYTHON) scripts/rehearse_backup_restore.py

release-readiness: contracts golden-corpus backup-restore-rehearsal

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
