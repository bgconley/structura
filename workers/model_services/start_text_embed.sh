#!/usr/bin/env bash
set -euo pipefail

: "${MODEL_ID:?MODEL_ID is required}"

if [[ -z "${CUDA_VISIBLE_DEVICES:-}" && -n "${NVIDIA_VISIBLE_DEVICES:-}" && "$NVIDIA_VISIBLE_DEVICES" != "all" ]]; then
  export CUDA_VISIBLE_DEVICES="$NVIDIA_VISIBLE_DEVICES"
fi

port="${PORT:-8102}"
hostname="${HOSTNAME:-0.0.0.0}"
dtype="${DTYPE:-float16}"
served_model_name="${SERVED_MODEL_NAME:-$MODEL_ID}"

exec text-embeddings-router-120 \
  --model-id "$MODEL_ID" \
  --served-model-name "$served_model_name" \
  --hostname "$hostname" \
  --port "$port" \
  --dtype "$dtype" \
  --json-output
