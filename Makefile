PYTHON ?= python3
NPM ?= npm
SEMGREP ?= $(shell $(PYTHON) -c 'import shutil, sysconfig; print(shutil.which("semgrep") or (sysconfig.get_path("scripts") + "/semgrep"))')
PYRIGHT_PYTHON ?= $(shell command -v $(PYTHON) 2>/dev/null || printf '%s' '$(PYTHON)')
MODEL_CORPUS_SHAPE_MANIFEST ?= tests/fixtures/model_corpus/phase8_5_model_manifest.example.json
MODEL_CORPUS_RELEASE_MANIFEST ?= tests/fixtures/model_corpus/phase8_5_model_manifest.json
MODEL_CORPUS_RUN_ID ?= phase8_5_model_corpus
MODEL_CORPUS_MODEL_MODE ?= live
MODEL_CORPUS_QWEN_EVIDENCE ?=
MODEL_CORPUS_GRANITE_EVIDENCE ?=
MODEL_CORPUS_TEXT_EMBEDDING_EVIDENCE ?=
MODEL_CORPUS_VISUAL_EMBEDDING_EVIDENCE ?=
MODEL_CORPUS_THRESHOLDS_JSON ?=
MODEL_CORPUS_GOLD_METRICS_JSON ?=
MODEL_CORPUS_GOLD_THRESHOLDS_JSON ?=
export PYTHONPATH := $(CURDIR)

.PHONY: bootstrap test integration-test lint format contracts sast migrate golden-corpus model-corpus build-model-corpus-manifest model-corpus-release backup-restore-rehearsal release-readiness api-dev web-dev compose-up worker-placeholder

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

model-corpus:
	$(PYTHON) scripts/run_model_corpus.py --manifest $(MODEL_CORPUS_SHAPE_MANIFEST)

build-model-corpus-manifest:
	$(PYTHON) scripts/build_model_corpus_manifest.py \
		--output $(MODEL_CORPUS_RELEASE_MANIFEST) \
		--run-id $(MODEL_CORPUS_RUN_ID) \
		--model-mode $(MODEL_CORPUS_MODEL_MODE) \
		--qwen-evidence $(MODEL_CORPUS_QWEN_EVIDENCE) \
		--granite-evidence $(MODEL_CORPUS_GRANITE_EVIDENCE) \
		--text-embedding-evidence $(MODEL_CORPUS_TEXT_EMBEDDING_EVIDENCE) \
		--visual-embedding-evidence $(MODEL_CORPUS_VISUAL_EMBEDDING_EVIDENCE) \
		--thresholds-json $(MODEL_CORPUS_THRESHOLDS_JSON) \
		--gold-metrics-json $(MODEL_CORPUS_GOLD_METRICS_JSON) \
		--gold-thresholds-json $(MODEL_CORPUS_GOLD_THRESHOLDS_JSON)

model-corpus-release:
	$(PYTHON) scripts/run_model_corpus.py --require-model-backed --manifest $(MODEL_CORPUS_RELEASE_MANIFEST)

backup-restore-rehearsal:
	$(PYTHON) scripts/rehearse_backup_restore.py

release-readiness: contracts golden-corpus model-corpus-release backup-restore-rehearsal

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
