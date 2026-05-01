#!/usr/bin/env bash
set -euo pipefail

model_id="${STRUCTURA_GRANITE_MODEL_ID:-ibm-granite/granite-4.0-3b-vision}"
adapter_path="${STRUCTURA_GRANITE_ADAPTER_PATH:-$model_id}"
server_dir="${STRUCTURA_GRANITE_SERVER_DIR:-/srv/structura/models/granite-vllm-server}"
port="${STRUCTURA_GRANITE_PORT:-8101}"
max_model_len="${STRUCTURA_GRANITE_MAX_MODEL_LEN:-32768}"
gpu_memory="${STRUCTURA_GRANITE_GPU_MEMORY_UTILIZATION:-0.45}"
max_num_seqs="${STRUCTURA_GRANITE_MAX_NUM_SEQS:-8}"
limit_mm="${STRUCTURA_GRANITE_LIMIT_MM_PER_PROMPT:-}"
if [[ -z "$limit_mm" ]]; then
  limit_mm='{"image":1,"video":0}'
fi

export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"
if [[ -n "${STRUCTURA_CUDA_VISIBLE_DEVICES:-}" ]]; then
  export CUDA_VISIBLE_DEVICES="$STRUCTURA_CUDA_VISIBLE_DEVICES"
elif [[ ("${CUDA_VISIBLE_DEVICES:-}" == "" || "${CUDA_VISIBLE_DEVICES:-}" == "void") && -n "${NVIDIA_VISIBLE_DEVICES:-}" && "$NVIDIA_VISIBLE_DEVICES" != "all" && "$NVIDIA_VISIBLE_DEVICES" != "void" ]]; then
  export CUDA_VISIBLE_DEVICES="$NVIDIA_VISIBLE_DEVICES"
fi

mkdir -p "$server_dir"
cd "$server_dir"

if [[ ! -f granite4_vision.py || ! -f start_granite4_vision_server.py ]]; then
  hf download "$model_id" \
    granite4_vision.py \
    start_granite4_vision_server.py \
    --local-dir "$server_dir"
fi

args=(
  --model "$model_id"
  --trust_remote_code
  --host 0.0.0.0
  --port "$port"
  --max-model-len "$max_model_len"
  --gpu-memory-utilization "$gpu_memory"
  --max-num-seqs "$max_num_seqs"
  --limit-mm-per-prompt "$limit_mm"
  --hf-overrides "{\"adapter_path\":\"$adapter_path\"}"
)

case "${STRUCTURA_GRANITE_DISABLE_PREFIX_CACHING:-}" in
  1|true|TRUE|yes|YES)
    args+=(--no-enable-prefix-caching)
    ;;
esac

exec python start_granite4_vision_server.py "${args[@]}"
