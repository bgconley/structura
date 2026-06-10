#!/usr/bin/env bash
set -euo pipefail

: "${MODEL_ID:?MODEL_ID is required}"

if [[ -n "${STRUCTURA_CUDA_VISIBLE_DEVICES:-}" ]]; then
  export CUDA_VISIBLE_DEVICES="$STRUCTURA_CUDA_VISIBLE_DEVICES"
elif [[ ("${CUDA_VISIBLE_DEVICES:-}" == "" || "${CUDA_VISIBLE_DEVICES:-}" == "void") && -n "${NVIDIA_VISIBLE_DEVICES:-}" && "$NVIDIA_VISIBLE_DEVICES" != "all" && "$NVIDIA_VISIBLE_DEVICES" != "void" ]]; then
  export CUDA_VISIBLE_DEVICES="$NVIDIA_VISIBLE_DEVICES"
fi

port="${PORT:-8102}"
hostname="${HOSTNAME:-0.0.0.0}"
dtype="${DTYPE:-float16}"
served_model_name="${SERVED_MODEL_NAME:-$MODEL_ID}"

# Select the TEI router binary for the GPU this service actually runs on:
# explicit env override first, then the binary matching the detected CUDA
# compute capability (e.g. 86 for RTX 3090, 120 for Blackwell), then the
# image's generic arch-dispatching entrypoint binary.
router_binary="${STRUCTURA_TEI_ROUTER_BINARY:-}"
if [[ -z "$router_binary" ]]; then
  compute_cap="$(nvidia-smi --query-gpu=compute_cap --format=csv,noheader 2>/dev/null | head -n1 | tr -d '. \r')"
  if [[ -n "$compute_cap" ]] && command -v "text-embeddings-router-${compute_cap}" >/dev/null 2>&1; then
    router_binary="text-embeddings-router-${compute_cap}"
  elif command -v text-embeddings-router >/dev/null 2>&1; then
    router_binary="text-embeddings-router"
  else
    echo "No text-embeddings-router binary found for compute capability '${compute_cap:-unknown}'." >&2
    echo "Set STRUCTURA_TEI_ROUTER_BINARY to the router binary for this GPU." >&2
    exit 1
  fi
fi

exec "$router_binary" \
  --model-id "$MODEL_ID" \
  --served-model-name "$served_model_name" \
  --hostname "$hostname" \
  --port "$port" \
  --dtype "$dtype" \
  --json-output
