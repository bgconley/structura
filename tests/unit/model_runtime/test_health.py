from __future__ import annotations

import httpx

from lib.config import get_settings
from lib.model_runtime import health as health_module
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
        "model-qwen-semantic",
        "model-granite",
        "model-embed",
        "model-vl-embed",
    }
    for snapshot in snapshots:
        metrics = snapshot["metrics_json"]
        assert metrics["model_mode"] == "fixture"
        assert metrics["last_success_at"] is None
        assert metrics["timeout_count"] == 0
        assert metrics["error_count"] == 0
        assert metrics["queue_depth"] is None
        assert metrics["oldest_job_age_seconds"] is None
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
        if request.url.port == 8104:
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
    assert by_name["model-qwen-semantic"]["status"] == "ok"
    assert by_name["model-granite"]["status"] == "unavailable"
    assert by_name["model-granite"]["checked_at"] is not None
    assert by_name["model-qwen-semantic"]["metrics_json"]["last_success_at"] is None
    assert by_name["model-qwen-semantic"]["metrics_json"]["timeout_count"] == 0
    assert by_name["model-qwen-semantic"]["metrics_json"]["error_count"] == 0
    assert by_name["model-qwen-semantic"]["metrics_json"]["queue_depth"] is None
    assert by_name["model-qwen-semantic"]["metrics_json"]["oldest_job_age_seconds"] is None
    rendered = repr(snapshots)
    assert "prompt" not in rendered
    assert "data:image" not in rendered


def test_model_health_probe_records_probed_service_url_without_credentials(monkeypatch) -> None:
    monkeypatch.setenv("STRUCTURA_MODEL_MODE", "live")
    monkeypatch.setenv(
        "STRUCTURA_MODEL_GRANITE_URL",
        "http://operator:secret-token@127.0.0.1:8101/v1",
    )
    get_settings.cache_clear()

    try:
        snapshots = probed_model_health_snapshots(
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(200, json={"status": "ok"})
            ),
            timeout_seconds=0.01,
        )
    finally:
        get_settings.cache_clear()

    by_name = {snapshot["service_name"]: snapshot for snapshot in snapshots}
    granite_metrics = by_name["model-granite"]["metrics_json"]
    assert granite_metrics["service_url"] == "http://127.0.0.1:8101"
    qwen_metrics = by_name["model-qwen-semantic"]["metrics_json"]
    assert qwen_metrics["service_url"] == "http://127.0.0.1:8104"
    rendered = repr(snapshots)
    assert "secret-token" not in rendered
    assert "operator" not in rendered


def test_model_health_probe_persists_snapshots_through_service_health_path(monkeypatch) -> None:
    monkeypatch.setenv("STRUCTURA_MODEL_MODE", "live")
    get_settings.cache_clear()
    persisted: list[list[dict[str, object]]] = []
    monkeypatch.setattr(
        health_module,
        "persist_model_health_snapshots",
        lambda snapshots: persisted.append(snapshots),
    )

    try:
        snapshots = probed_model_health_snapshots(
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(200, json={"status": "ok"})
            ),
            timeout_seconds=0.01,
            persist=True,
        )
        unpersisted = probed_model_health_snapshots(
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(200, json={"status": "ok"})
            ),
            timeout_seconds=0.01,
        )
    finally:
        get_settings.cache_clear()

    assert persisted == [snapshots]
    assert unpersisted


def test_persist_model_health_snapshots_writes_each_snapshot(monkeypatch) -> None:
    import lib.jobs as jobs_module

    recorded: list[dict[str, object]] = []

    def record(**kwargs: object) -> None:
        recorded.append(kwargs)

    monkeypatch.setattr(jobs_module, "record_service_health", record)

    health_module.persist_model_health_snapshots(
        [
            {
                "service_name": "model-granite",
                "status": "unavailable",
                "metrics_json": {"service_url": "http://127.0.0.1:8101"},
                "checked_at": "2026-06-09T00:00:00+00:00",
            }
        ]
    )

    assert recorded == [
        {
            "service_name": "model-granite",
            "status": "unavailable",
            "metrics": {"service_url": "http://127.0.0.1:8101"},
        }
    ]
