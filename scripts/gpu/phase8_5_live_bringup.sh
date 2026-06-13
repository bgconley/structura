#!/usr/bin/env bash
set -euo pipefail

export STRUCTURA_MODEL_MODE="${STRUCTURA_MODEL_MODE:-live}"
export STRUCTURA_EMBEDDING_VISUAL_ENABLED="${STRUCTURA_EMBEDDING_VISUAL_ENABLED:-true}"
export STRUCTURA_QWEN_VISION_FALLBACK="${STRUCTURA_QWEN_VISION_FALLBACK:-true}"

REBUILD=0
SKIP_PREFLIGHT=0
INCLUDE_GRANITE=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --include-granite)
      INCLUDE_GRANITE=1
      shift
      ;;
    --build)
      REBUILD=1
      shift
      ;;
    --skip-preflight)
      SKIP_PREFLIGHT=1
      shift
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

COMPOSE_PROFILES=(
  --profile models-live
  --profile visual-embed-live
  --profile extraction
  --profile semantic
  --profile visual
)
APP_SERVICES=(
  api
  worker-ingest
  worker-previews
  worker-docling
  worker-extraction
  worker-semantic-annotations
  worker-relationships
  worker-visual-embeddings
)
LIVE_MODEL_SERVICES=(
  model-qwen-semantic
  model-vl-embed
)
REBUILD_SERVICES=(
  api
  worker-extraction
  worker-semantic-annotations
  worker-visual-embeddings
)
REMOVED_LEGACY_CONTAINERS=(
  structura-model-qwen-1
  structura-model-qwen-placeholder-1
)

compose_live() {
  docker compose "${COMPOSE_PROFILES[@]}" "$@"
}

if [[ "$INCLUDE_GRANITE" == "1" ]]; then
  COMPOSE_PROFILES+=(--profile granite-live)
  LIVE_MODEL_SERVICES+=(model-granite)
  export STRUCTURA_MODEL_GRANITE_URL="${STRUCTURA_MODEL_GRANITE_URL:-http://model-granite:8101}"
  export STRUCTURA_E4_INCLUDE_GRANITE=true
fi

if [[ "$REBUILD" == "1" ]]; then
  compose_live build "${REBUILD_SERVICES[@]}"
fi

docker rm -f "${REMOVED_LEGACY_CONTAINERS[@]}" >/dev/null 2>&1 || true
compose_live up -d "${LIVE_MODEL_SERVICES[@]}"
compose_live up -d --no-deps --force-recreate "${APP_SERVICES[@]}"

if [[ "$SKIP_PREFLIGHT" != "1" ]]; then
  "${PYTHON:-python3}" scripts/gpu/phase8_5_live_runtime_preflight.py
fi

echo "Phase 8.5 live resident runtime is up with STRUCTURA_MODEL_MODE=${STRUCTURA_MODEL_MODE}"
