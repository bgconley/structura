#!/usr/bin/env bash
set -euo pipefail

: "${STRUCTURA_VLLM_MODEL_ID:?STRUCTURA_VLLM_MODEL_ID is required}"

export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"
export VLLM_SLEEP_WHEN_IDLE="${VLLM_SLEEP_WHEN_IDLE:-1}"
if [[ -z "${CUDA_VISIBLE_DEVICES:-}" && -n "${NVIDIA_VISIBLE_DEVICES:-}" && "$NVIDIA_VISIBLE_DEVICES" != "all" ]]; then
  export CUDA_VISIBLE_DEVICES="$NVIDIA_VISIBLE_DEVICES"
fi

port="${STRUCTURA_VLLM_PORT:-8000}"
served_model_name="${STRUCTURA_VLLM_SERVED_MODEL_NAME:-$STRUCTURA_VLLM_MODEL_ID}"
max_model_len="${STRUCTURA_VLLM_MAX_MODEL_LEN:-32768}"
gpu_memory="${STRUCTURA_VLLM_GPU_MEMORY_UTILIZATION:-0.85}"
dtype="${STRUCTURA_VLLM_DTYPE:-auto}"
limit_mm="${STRUCTURA_VLLM_LIMIT_MM_PER_PROMPT:-}"
if [[ -z "$limit_mm" ]]; then
  limit_mm='{"image":4,"video":0}'
fi

args=(
  --model "$STRUCTURA_VLLM_MODEL_ID"
  --served-model-name "$served_model_name"
  --host 0.0.0.0
  --port "$port"
  --trust-remote-code
  --max-model-len "$max_model_len"
  --gpu-memory-utilization "$gpu_memory"
  --limit-mm-per-prompt "$limit_mm"
)

if [[ "$dtype" != "auto" ]]; then
  args+=(--dtype "$dtype")
fi

if [[ -n "${STRUCTURA_VLLM_KV_CACHE_DTYPE:-}" ]]; then
  args+=(--kv-cache-dtype "$STRUCTURA_VLLM_KV_CACHE_DTYPE")
fi

if [[ -n "${STRUCTURA_VLLM_MAX_NUM_SEQS:-}" ]]; then
  args+=(--max-num-seqs "$STRUCTURA_VLLM_MAX_NUM_SEQS")
fi

exec python -m vllm.entrypoints.openai.api_server "${args[@]}"
