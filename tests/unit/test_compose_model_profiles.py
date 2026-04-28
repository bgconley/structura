from __future__ import annotations

from pathlib import Path

import yaml


def test_model_profiles_are_safe_and_gpu_placed() -> None:
    compose = yaml.safe_load(Path("compose.yaml").read_text())
    services = compose["services"]

    for name in (
        "model-qwen",
        "model-qwen-semantic",
        "model-granite",
        "model-embed",
        "model-vl-embed",
    ):
        service = services[name]
        rendered_ports = "\n".join(service.get("ports", []))
        assert "127.0.0.1" in rendered_ports
        assert any("/srv/structura/models" in volume for volume in service.get("volumes", []))

    assert services["model-qwen"]["environment"]["NVIDIA_VISIBLE_DEVICES"].endswith(":-0}")
    assert services["model-qwen-semantic"]["environment"]["NVIDIA_VISIBLE_DEVICES"].endswith(":-0}")
    assert services["model-granite"]["environment"]["NVIDIA_VISIBLE_DEVICES"].endswith(":-1}")
    assert services["model-vl-embed"]["profiles"] == ["visual-embed-live"]
    semantic_worker = services["worker-semantic-annotations"]
    assert "workers.semantic_annotations.worker" in semantic_worker["command"]
    assert "semantic" in semantic_worker["profiles"]
    assert semantic_worker["environment"]["STRUCTURA_MODEL_QWEN_HQ_URL"] == (
        "http://model-qwen:8100"
    )
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
    assert qwen_semantic["environment"]["STRUCTURA_VLLM_MODEL_ID"] == ("Qwen/Qwen3-VL-2B-Instruct")
    assert qwen_semantic["environment"]["STRUCTURA_VLLM_PORT"] == "8104"

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

    granite = services["model-granite"]
    assert "voipmonitor/vllm:cu130" in granite["image"]
    assert "start_granite_vllm.sh" in " ".join(granite["command"])
    assert granite["environment"]["STRUCTURA_GRANITE_MODEL_ID"] == (
        "ibm-granite/granite-4.0-3b-vision"
    )

    text_embed = services["model-embed"]
    assert "text-embeddings-inference:cuda-1.9" in text_embed["image"]
    assert "start_text_embed.sh" in " ".join(text_embed["command"])
    assert text_embed["environment"]["MODEL_ID"] == "Qwen/Qwen3-Embedding-4B"

    visual_embed = services["model-vl-embed"]
    assert "voipmonitor/vllm:cu130" in visual_embed["image"]
    assert "start_visual_embed_vllm.sh" in " ".join(visual_embed["command"])
    assert visual_embed["environment"]["STRUCTURA_VLLM_MODEL_ID"] == ("Qwen/Qwen3-VL-Embedding-2B")
