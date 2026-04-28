#!/usr/bin/env bash
set -euo pipefail

model_id="${STRUCTURA_GRANITE_MODEL_ID:-ibm-granite/granite-4.0-3b-vision}"
adapter_path="${STRUCTURA_GRANITE_ADAPTER_PATH:-$model_id}"
server_dir="${STRUCTURA_GRANITE_SERVER_DIR:-/srv/structura/models/granite-vllm-server}"
port="${STRUCTURA_GRANITE_PORT:-8101}"

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

exec python start_granite4_vision_server.py \
  --model "$model_id" \
  --trust_remote_code \
  --host 0.0.0.0 \
  --port "$port" \
  --hf-overrides "{\"adapter_path\":\"$adapter_path\"}"
