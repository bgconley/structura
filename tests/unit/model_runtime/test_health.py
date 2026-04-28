from __future__ import annotations

from lib.config import get_settings
from lib.model_runtime.health import configured_model_health_snapshots


def test_model_health_snapshots_report_mode_and_profiles_without_private_payloads(
    monkeypatch,
) -> None:
    monkeypatch.setenv("STRUCTURA_MODEL_MODE", "fixture")
    get_settings.cache_clear()

    try:
        snapshots = configured_model_health_snapshots()
    finally:
        get_settings.cache_clear()

    names = {snapshot["service_name"] for snapshot in snapshots}
    assert names == {"model-qwen", "model-granite", "model-embed", "model-vl-embed"}
    for snapshot in snapshots:
        metrics = snapshot["metrics_json"]
        assert metrics["model_mode"] == "fixture"
        rendered = repr(snapshot)
        assert "prompt" not in rendered
        assert "filesystem://" not in rendered
        assert "data:image" not in rendered
        assert "/srv/structura/tmp/model-inputs" not in rendered
