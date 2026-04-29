from __future__ import annotations

from pathlib import Path

import yaml


def test_model_profiles_are_safe_and_gpu_placed() -> None:
    compose = yaml.safe_load(Path("compose.yaml").read_text())
    services = compose["services"]

    expected_gpu_bindings = {
        "model-qwen": "${STRUCTURA_MODEL_QWEN_GPU:-0}",
        "model-qwen-semantic": "${STRUCTURA_MODEL_QWEN_SEMANTIC_GPU:-0}",
        "model-granite": "${STRUCTURA_MODEL_GRANITE_GPU:-1}",
        "model-embed": "${STRUCTURA_MODEL_EMBED_GPU:-1}",
        "model-vl-embed": "${STRUCTURA_MODEL_VISUAL_EMBED_GPU:-1}",
    }
    for name, host_gpu in expected_gpu_bindings.items():
        service = services[name]
        rendered_ports = "\n".join(service.get("ports", []))
        assert "127.0.0.1" in rendered_ports
        assert "gpus" not in service
        assert service["ipc"] == "host"
        assert service["shm_size"] == "${STRUCTURA_MODEL_SHM_SIZE:-8gb}"
        assert service["ulimits"]["memlock"] == -1
        assert service["ulimits"]["stack"] == 67108864
        devices = service["deploy"]["resources"]["reservations"]["devices"]
        assert devices == [
            {
                "driver": "nvidia",
                "device_ids": [host_gpu],
                "capabilities": ["gpu"],
            }
        ]
        environment = service["environment"]
        assert environment["CUDA_DEVICE_ORDER"] == "PCI_BUS_ID"
        assert environment["STRUCTURA_CUDA_VISIBLE_DEVICES"] == "0"
        assert any("/srv/structura/models" in volume for volume in service.get("volumes", []))

    assert "models-live" not in services["model-qwen"]["profiles"]
    assert services["model-qwen"]["profiles"] == ["qwen-hq-disabled"]
    assert services["model-embed"]["profiles"] == ["text-embed-live"]
    assert services["model-vl-embed"]["profiles"] == ["models-live", "visual-embed-live"]
    semantic_worker = services["worker-semantic-annotations"]
    assert "workers.semantic_annotations.worker" in semantic_worker["command"]
    assert "semantic" in semantic_worker["profiles"]
    assert semantic_worker["environment"]["STRUCTURA_MODEL_QWEN_HQ_URL"] == (
        "http://model-qwen:8100"
    )
    assert semantic_worker["environment"]["STRUCTURA_QWEN8_ENABLED"] == "false"
    assert semantic_worker["environment"]["STRUCTURA_MODEL_QWEN_SEMANTIC_URL"] == (
        "http://model-qwen-semantic:8104"
    )
    for name in (
        "model-qwen-placeholder",
        "model-granite-placeholder",
        "model-embed-placeholder",
        "model-vl-embed-placeholder",
    ):
        assert "models-placeholder" in services[name]["profiles"]


def test_live_model_profiles_have_concrete_blackwell_commands() -> None:
    compose = yaml.safe_load(Path("compose.yaml").read_text())
    services = compose["services"]

    qwen_semantic = services["model-qwen-semantic"]
    assert "voipmonitor/vllm:cu130" in qwen_semantic["image"]
    assert "start_qwen_vllm.sh" in " ".join(qwen_semantic["command"])
    assert qwen_semantic["environment"]["STRUCTURA_MODEL_PROFILE"] == (
        "${STRUCTURA_QWEN_SEMANTIC_PROFILE:-qwen3-vl-4b-semantic:v1}"
    )
    assert qwen_semantic["environment"]["STRUCTURA_VLLM_MODEL_ID"] == ("Qwen/Qwen3-VL-4B-Instruct")
    assert qwen_semantic["environment"]["STRUCTURA_VLLM_SERVED_MODEL_NAME"] == (
        "Qwen/Qwen3-VL-4B-Instruct"
    )
    assert qwen_semantic["environment"]["STRUCTURA_VLLM_PORT"] == "8104"
    assert qwen_semantic["environment"]["STRUCTURA_VLLM_MAX_MODEL_LEN"] == "16384"
    assert qwen_semantic["environment"]["STRUCTURA_VLLM_GPU_MEMORY_UTILIZATION"] == "0.76"
    assert qwen_semantic["environment"]["STRUCTURA_VLLM_MAX_NUM_SEQS"] == "2"
    assert qwen_semantic["environment"]["STRUCTURA_VLLM_LIMIT_MM_PER_PROMPT"] == (
        '{"image":2,"video":0}'
    )

    qwen_hq = services["model-qwen"]
    assert "voipmonitor/vllm:cu130" in qwen_hq["image"]
    assert "start_qwen_vllm.sh" in " ".join(qwen_hq["command"])
    assert qwen_hq["environment"]["STRUCTURA_VLLM_MODEL_ID"] == (
        "${STRUCTURA_VLLM_QWEN_MODEL_ID:-lhoang8500/Qwen3-VL-8B-Instruct-NVFP4}"
    )
    assert qwen_hq["environment"]["STRUCTURA_VLLM_SERVED_MODEL_NAME"] == (
        "Qwen/Qwen3-VL-8B-Instruct"
    )
    assert qwen_hq["environment"]["STRUCTURA_VLLM_PORT"] == "8100"
    assert qwen_hq["environment"]["STRUCTURA_VLLM_MAX_MODEL_LEN"] == "32768"
    assert qwen_hq["environment"]["STRUCTURA_VLLM_GPU_MEMORY_UTILIZATION"] == "0.54"

    granite = services["model-granite"]
    assert "voipmonitor/vllm:cu130" in granite["image"]
    assert "start_granite_vllm.sh" in " ".join(granite["command"])
    assert granite["environment"]["STRUCTURA_GRANITE_MODEL_ID"] == (
        "ibm-granite/granite-4.0-3b-vision"
    )
    assert granite["environment"]["STRUCTURA_GRANITE_MAX_MODEL_LEN"] == "16384"
    assert granite["environment"]["STRUCTURA_GRANITE_GPU_MEMORY_UTILIZATION"] == "0.50"

    text_embed = services["model-embed"]
    assert "text-embeddings-inference:cuda-1.9" in text_embed["image"]
    assert "start_text_embed.sh" in " ".join(text_embed["command"])
    assert text_embed["environment"]["MODEL_ID"] == "Qwen/Qwen3-Embedding-4B"

    visual_embed = services["model-vl-embed"]
    assert "voipmonitor/vllm:cu130" in visual_embed["image"]
    assert "start_visual_embed_vllm.sh" in " ".join(visual_embed["command"])
    assert visual_embed["environment"]["STRUCTURA_VLLM_MODEL_ID"] == ("Qwen/Qwen3-VL-Embedding-2B")
    assert visual_embed["environment"]["STRUCTURA_VLLM_MAX_MODEL_LEN"] == "2048"
    assert visual_embed["environment"]["STRUCTURA_VLLM_GPU_MEMORY_UTILIZATION"] == "0.45"


def test_phase8_5_smoke_supports_managed_model_validation() -> None:
    smoke = Path("scripts/gpu/phase8_5_model_smoke.sh").read_text()
    probe = Path("scripts/gpu/probe_phase8_5_live_models.py").read_text()

    assert "STRUCTURA_MODEL_SMOKE_MANAGE_COMPOSE" in smoke
    assert "start_core_services" in smoke
    assert "BLACKWELL_CORE_SERVICES" in smoke
    assert "BLACKWELL_BASE_SERVICES" in smoke
    assert "BLACKWELL_COMPANION_SERVICES" in smoke
    assert 'probe_health "model-qwen"' not in smoke
    assert "BLACKWELL_HQ_SERVICES" not in smoke
    assert "model-vl-embed" in smoke
    assert "probe_text_embedding" in smoke
    assert "--skip-qwen" in smoke
    assert "--skip-visual-embed" in smoke
    assert "rm -sf" in smoke

    for flag in (
        "--skip-qwen",
        "--skip-qwen-semantic",
        "--skip-granite",
        "--skip-text-embed",
        "--skip-visual-embed",
    ):
        assert flag in probe
