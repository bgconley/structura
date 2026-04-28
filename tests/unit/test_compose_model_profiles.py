from __future__ import annotations

from pathlib import Path

import yaml


def test_model_profiles_are_safe_and_gpu_placed() -> None:
    compose = yaml.safe_load(Path("compose.yaml").read_text())
    services = compose["services"]

    for name in ("model-qwen", "model-granite", "model-embed", "model-vl-embed"):
        service = services[name]
        rendered_ports = "\n".join(service.get("ports", []))
        assert "127.0.0.1" in rendered_ports
        assert any("/srv/structura/models" in volume for volume in service.get("volumes", []))

    assert services["model-qwen"]["environment"]["NVIDIA_VISIBLE_DEVICES"].endswith(":-0}")
    assert services["model-granite"]["environment"]["NVIDIA_VISIBLE_DEVICES"].endswith(":-1}")
    assert services["model-vl-embed"]["profiles"] == ["visual-embed-live"]
    for name in (
        "model-qwen-placeholder",
        "model-granite-placeholder",
        "model-embed-placeholder",
        "model-vl-embed-placeholder",
    ):
        assert "models-placeholder" in services[name]["profiles"]
