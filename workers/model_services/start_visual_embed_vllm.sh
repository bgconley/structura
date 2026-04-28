#!/usr/bin/env bash
set -euo pipefail

model_id="${STRUCTURA_VLLM_MODEL_ID:-Qwen/Qwen3-VL-Embedding-2B}"
port="${STRUCTURA_VLLM_PORT:-8103}"
served_model_name="${STRUCTURA_VLLM_SERVED_MODEL_NAME:-$model_id}"
max_model_len="${STRUCTURA_VLLM_MAX_MODEL_LEN:-32768}"
gpu_memory="${STRUCTURA_VLLM_GPU_MEMORY_UTILIZATION:-0.70}"
dtype="${STRUCTURA_VLLM_DTYPE:-bfloat16}"
limit_mm="${STRUCTURA_VLLM_LIMIT_MM_PER_PROMPT:-}"
if [[ -z "$limit_mm" ]]; then
  limit_mm='{"image":8,"video":0}'
fi

export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"
export VLLM_SLEEP_WHEN_IDLE="${VLLM_SLEEP_WHEN_IDLE:-1}"
if [[ -n "${STRUCTURA_CUDA_VISIBLE_DEVICES:-}" ]]; then
  export CUDA_VISIBLE_DEVICES="$STRUCTURA_CUDA_VISIBLE_DEVICES"
elif [[ ("${CUDA_VISIBLE_DEVICES:-}" == "" || "${CUDA_VISIBLE_DEVICES:-}" == "void") && -n "${NVIDIA_VISIBLE_DEVICES:-}" && "$NVIDIA_VISIBLE_DEVICES" != "all" && "$NVIDIA_VISIBLE_DEVICES" != "void" ]]; then
  export CUDA_VISIBLE_DEVICES="$NVIDIA_VISIBLE_DEVICES"
fi

exec python -m vllm.entrypoints.openai.api_server \
  --model "$model_id" \
  --served-model-name "$served_model_name" \
  --runner pooling \
  --host 0.0.0.0 \
  --port "$port" \
  --trust-remote-code \
  --dtype "$dtype" \
  --max-model-len "$max_model_len" \
  --gpu-memory-utilization "$gpu_memory" \
  --limit-mm-per-prompt "$limit_mm"
