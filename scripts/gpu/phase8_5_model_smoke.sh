#!/usr/bin/env bash
set -euo pipefail

QWEN_URL="${STRUCTURA_MODEL_QWEN_URL:-http://127.0.0.1:8100}"
GRANITE_URL="${STRUCTURA_MODEL_GRANITE_URL:-http://127.0.0.1:8101}"
TEXT_EMBED_URL="${STRUCTURA_MODEL_TEXT_EMBED_URL:-http://127.0.0.1:8102}"
VISUAL_EMBED_URL="${STRUCTURA_MODEL_VISUAL_EMBED_URL:-http://127.0.0.1:8103}"

echo "Phase 8.5 GPU model smoke"

if command -v nvidia-smi >/dev/null 2>&1; then
  nvidia-smi --query-gpu=index,name,memory.total,driver_version --format=csv,noheader
else
  echo "nvidia-smi not found" >&2
  exit 1
fi

probe_health() {
  local name="$1"
  local url="$2"
  if curl -fsS "${url}/healthz" >/dev/null 2>&1; then
    echo "${name}: healthz ok"
    return
  fi
  if curl -fsS "${url}/health" >/dev/null 2>&1; then
    echo "${name}: health ok"
    return
  fi
  echo "${name}: no health endpoint responded at ${url}" >&2
  exit 1
}

probe_health "model-qwen" "${QWEN_URL}"
probe_health "model-granite" "${GRANITE_URL}"
probe_health "model-embed" "${TEXT_EMBED_URL}"
probe_health "model-vl-embed" "${VISUAL_EMBED_URL}"

"${PYTHON:-python3}" scripts/run_model_corpus.py \
  --require-model-backed \
  --manifest "${STRUCTURA_MODEL_CORPUS_MANIFEST:-tests/fixtures/model_corpus/phase8_5_model_manifest.json}"

echo "Phase 8.5 GPU model smoke completed"
