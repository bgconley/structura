#!/usr/bin/env bash
set -euo pipefail

: "${STRUCTURA_VLLM_MODEL_ID:?STRUCTURA_VLLM_MODEL_ID is required}"

export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"
export VLLM_SLEEP_WHEN_IDLE="${VLLM_SLEEP_WHEN_IDLE:-1}"
if [[ -n "${STRUCTURA_CUDA_VISIBLE_DEVICES:-}" ]]; then
  export CUDA_VISIBLE_DEVICES="$STRUCTURA_CUDA_VISIBLE_DEVICES"
elif [[ ("${CUDA_VISIBLE_DEVICES:-}" == "" || "${CUDA_VISIBLE_DEVICES:-}" == "void") && -n "${NVIDIA_VISIBLE_DEVICES:-}" && "$NVIDIA_VISIBLE_DEVICES" != "all" && "$NVIDIA_VISIBLE_DEVICES" != "void" ]]; then
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

structured_outputs_config="${STRUCTURA_QWEN_STRUCTURED_OUTPUTS_CONFIG:-}"
if [[ -z "$structured_outputs_config" ]]; then
  # Match the Granite service: forbid whitespace loops inside guided decoding.
  structured_outputs_config='{"backend": "xgrammar", "disable_any_whitespace": true}'
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
  --structured-outputs-config "$structured_outputs_config"
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

if [[ -n "${STRUCTURA_VLLM_MM_PROCESSOR_CACHE_GB:-}" ]]; then
  args+=(--mm-processor-cache-gb "$STRUCTURA_VLLM_MM_PROCESSOR_CACHE_GB")
fi

if [[ -n "${STRUCTURA_VLLM_MM_PROCESSOR_KWARGS:-}" ]]; then
  args+=(--mm-processor-kwargs "$STRUCTURA_VLLM_MM_PROCESSOR_KWARGS")
fi

case "${STRUCTURA_VLLM_DISABLE_PREFIX_CACHING:-}" in
  1|true|TRUE|yes|YES)
    args+=(--no-enable-prefix-caching)
    ;;
esac

exec python -m vllm.entrypoints.openai.api_server "${args[@]}"
