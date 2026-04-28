#!/usr/bin/env bash
set -euo pipefail

QWEN_URL="${STRUCTURA_MODEL_QWEN_URL:-http://127.0.0.1:8100}"
QWEN_SEMANTIC_URL="${STRUCTURA_MODEL_QWEN_SEMANTIC_URL:-http://127.0.0.1:8104}"
GRANITE_URL="${STRUCTURA_MODEL_GRANITE_URL:-http://127.0.0.1:8101}"
TEXT_EMBED_URL="${STRUCTURA_MODEL_TEXT_EMBED_URL:-http://127.0.0.1:8102}"
VISUAL_EMBED_URL="${STRUCTURA_MODEL_VISUAL_EMBED_URL:-http://127.0.0.1:8103}"
HEALTH_TIMEOUT_SECONDS="${STRUCTURA_MODEL_SMOKE_HEALTH_TIMEOUT_SECONDS:-1200}"
HEALTH_POLL_SECONDS="${STRUCTURA_MODEL_SMOKE_HEALTH_POLL_SECONDS:-5}"
MANAGE_COMPOSE="${STRUCTURA_MODEL_SMOKE_MANAGE_COMPOSE:-0}"
COMPOSE_PROFILES=(
  --profile models-live
  --profile qwen-hq-live
  --profile text-embed-live
  --profile visual-embed-live
)
MODEL_SERVICES=(
  model-qwen-semantic
  model-qwen
  model-granite
  model-embed
  model-vl-embed
)
BLACKWELL_CORE_SERVICES=(
  model-qwen-semantic
  model-qwen
  model-granite
  model-vl-embed
)
BLACKWELL_BASE_SERVICES=(
  model-qwen
  model-granite
)
BLACKWELL_COMPANION_SERVICES=(
  model-qwen-semantic
  model-vl-embed
)

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
  local deadline=$((SECONDS + HEALTH_TIMEOUT_SECONDS))
  echo "${name}: waiting for health at ${url} (${HEALTH_TIMEOUT_SECONDS}s timeout)"
  while ((SECONDS < deadline)); do
    if curl -fsS "${url}/healthz" >/dev/null 2>&1; then
      echo "${name}: healthz ok"
      return
    fi
    if curl -fsS "${url}/health" >/dev/null 2>&1; then
      echo "${name}: health ok"
      return
    fi
    sleep "${HEALTH_POLL_SECONDS}"
  done
  echo "${name}: no health endpoint responded at ${url} within ${HEALTH_TIMEOUT_SECONDS}s" >&2
  exit 1
}

probe_live_models() {
  "${PYTHON:-python3}" scripts/gpu/probe_phase8_5_live_models.py \
    --qwen-url "${QWEN_URL}" \
    --qwen-model "${STRUCTURA_MODEL_QWEN_MODEL:-Qwen/Qwen3-VL-8B-Instruct}" \
    --qwen-semantic-url "${QWEN_SEMANTIC_URL}" \
    --qwen-semantic-model "${STRUCTURA_MODEL_QWEN_SEMANTIC_MODEL:-Qwen/Qwen3-VL-2B-Instruct}" \
    --granite-url "${GRANITE_URL}" \
    --granite-model "${STRUCTURA_MODEL_GRANITE_MODEL:-ibm-granite/granite-4.0-3b-vision}" \
    --text-embed-url "${TEXT_EMBED_URL}" \
    --text-embed-model "${STRUCTURA_MODEL_TEXT_EMBED_MODEL:-Qwen/Qwen3-Embedding-4B}" \
    --visual-embed-url "${VISUAL_EMBED_URL}" \
    --visual-embed-model "${STRUCTURA_MODEL_VISUAL_EMBED_MODEL:-Qwen/Qwen3-VL-Embedding-2B}" \
    "$@"
}

compose_model() {
  docker compose "${COMPOSE_PROFILES[@]}" "$@"
}

remove_model_services() {
  compose_model rm -sf "$@" >/dev/null || true
}

start_core_services() {
  echo "Starting co-resident Phase 8.5 Blackwell model services"
  remove_model_services "${MODEL_SERVICES[@]}"
  compose_model up -d --force-recreate "${BLACKWELL_BASE_SERVICES[@]}"
  probe_health "model-qwen" "${QWEN_URL}"
  probe_health "model-granite" "${GRANITE_URL}"
  compose_model up -d --force-recreate "${BLACKWELL_COMPANION_SERVICES[@]}"
}

probe_core_services() {
  probe_health "model-qwen-semantic" "${QWEN_SEMANTIC_URL}"
  probe_health "model-qwen" "${QWEN_URL}"
  probe_health "model-granite" "${GRANITE_URL}"
  probe_health "model-vl-embed" "${VISUAL_EMBED_URL}"
  probe_live_models --skip-text-embed
}

probe_text_embedding() {
  echo "Validating on-demand text embedding service"
  remove_model_services model-granite model-vl-embed
  compose_model up -d --force-recreate model-embed
  probe_health "model-embed" "${TEXT_EMBED_URL}"
  probe_live_models \
    --skip-qwen \
    --skip-qwen-semantic \
    --skip-granite \
    --skip-visual-embed
  remove_model_services model-embed
  compose_model up -d --force-recreate model-granite model-vl-embed
  probe_health "model-granite" "${GRANITE_URL}"
  probe_health "model-vl-embed" "${VISUAL_EMBED_URL}"
}

if [[ "$MANAGE_COMPOSE" == "1" || "$MANAGE_COMPOSE" == "true" ]]; then
  start_core_services
  probe_core_services
  probe_text_embedding
else
  probe_health "model-qwen" "${QWEN_URL}"
  probe_health "model-qwen-semantic" "${QWEN_SEMANTIC_URL}"
  probe_health "model-granite" "${GRANITE_URL}"
  probe_health "model-embed" "${TEXT_EMBED_URL}"
  probe_health "model-vl-embed" "${VISUAL_EMBED_URL}"
  probe_live_models
fi

"${PYTHON:-python3}" scripts/run_model_corpus.py \
  --require-model-backed \
  --manifest "${STRUCTURA_MODEL_CORPUS_MANIFEST:-tests/fixtures/model_corpus/phase8_5_model_manifest.json}"

echo "Phase 8.5 GPU model smoke completed"
