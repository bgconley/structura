#!/usr/bin/env bash
set -euo pipefail

export STRUCTURA_MODEL_MODE="${STRUCTURA_MODEL_MODE:-live}"
export STRUCTURA_QWEN8_ENABLED="${STRUCTURA_QWEN8_ENABLED:-false}"
export STRUCTURA_EMBEDDING_VISUAL_ENABLED="${STRUCTURA_EMBEDDING_VISUAL_ENABLED:-true}"

REBUILD=0
SKIP_PREFLIGHT=0

while [[ $# -gt 0 ]]; do
  case "$1" in
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
  model-granite
  model-vl-embed
)
REBUILD_SERVICES=(
  api
  worker-extraction
  worker-semantic-annotations
  worker-visual-embeddings
)

compose_live() {
  docker compose "${COMPOSE_PROFILES[@]}" "$@"
}

if [[ "$REBUILD" == "1" ]]; then
  compose_live build "${REBUILD_SERVICES[@]}"
fi

compose_live up -d "${LIVE_MODEL_SERVICES[@]}"
compose_live up -d --no-deps --force-recreate "${APP_SERVICES[@]}"

if [[ "$SKIP_PREFLIGHT" != "1" ]]; then
  "${PYTHON:-python3}" scripts/gpu/phase8_5_live_runtime_preflight.py
fi

echo "Phase 8.5 live resident runtime is up with STRUCTURA_MODEL_MODE=${STRUCTURA_MODEL_MODE}"
