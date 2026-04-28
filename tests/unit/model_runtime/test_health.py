from __future__ import annotations

import httpx

from lib.config import get_settings
from lib.model_runtime.health import (
    configured_model_health_snapshots,
    probed_model_health_snapshots,
)


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
    assert names == {
        "model-qwen",
        "model-qwen-semantic",
        "model-granite",
        "model-embed",
        "model-vl-embed",
    }
    for snapshot in snapshots:
        metrics = snapshot["metrics_json"]
        assert metrics["model_mode"] == "fixture"
        rendered = repr(snapshot)
        assert "prompt" not in rendered
        assert "filesystem://" not in rendered
        assert "data:image" not in rendered
        assert "/srv/structura/tmp/model-inputs" not in rendered


def test_model_health_probe_reports_live_service_readiness_without_sensitive_payloads(
    monkeypatch,
) -> None:
    monkeypatch.setenv("STRUCTURA_MODEL_MODE", "live")
    get_settings.cache_clear()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.port == 8100:
            return httpx.Response(200, json={"status": "ok"})
        return httpx.Response(503, json={"status": "starting"})

    try:
        snapshots = probed_model_health_snapshots(
            transport=httpx.MockTransport(handler),
            timeout_seconds=0.01,
        )
    finally:
        get_settings.cache_clear()

    by_name = {snapshot["service_name"]: snapshot for snapshot in snapshots}
    assert by_name["model-qwen"]["status"] == "ok"
    assert by_name["model-granite"]["status"] == "unavailable"
    assert by_name["model-granite"]["checked_at"] is not None
    rendered = repr(snapshots)
    assert "prompt" not in rendered
    assert "data:image" not in rendered
