"""Versioned combined adapter authority, exact input binding and checkpoint replay."""

import json
from dataclasses import replace

import httpx
import pytest

from lib.document_parsing.source_adapter import DocumentSource
from lib.document_processing.configuration_types import ParseRequestSettings
from lib.document_processing.errors import ProcessingError
from lib.document_processing.parse_execution import execute_parse_candidate
from lib.document_processing.understanding_configuration import understanding_configuration
from lib.model_runtime.clients.qwen_vl import QwenVLClient
from lib.model_runtime.profiles import QWEN_INGESTION_PROFILE, get_model_profile
from tests.fixtures.page_understanding_client import UnderstandingClient
from tests.fixtures.page_understanding_sources import invoice_page


@pytest.fixture
def understanding(execution, monkeypatch):
    def build(count=2):
        harness = execution(count)
        source = harness.registered
        with DocumentSource(
            harness.storage.path_for_uri(source.uri),
            asset_id=source.original_asset_id,
            expected_sha256=source.original_sha256,
            mime_type=source.mime_type,
        ) as original:
            configuration = understanding_configuration(
                harness.deployment,
                original,
                request=ParseRequestSettings(
                    max_output_tokens=14000, temperature=0, seed=None, timeout_seconds=137
                ),
            )
        harness.registered = source.model_copy(update={"configuration": configuration})
        harness.service.configuration = configuration
        monkeypatch.setattr(
            "lib.document_processing.parse_execution.load_processing_source",
            lambda _: harness.registered,
        )
        return harness

    return build


def execute(harness, client, **kwargs):
    return execute_parse_candidate(
        harness.binding,
        storage=harness.storage,
        client=client,
        deployment=harness.deployment,
        service=harness.service,
        batch_pages=1,
        **kwargs,
    )


def test_combined_pages_persist_all_products_once_and_resume_without_calls(understanding):
    harness = understanding(3)
    first = UnderstandingClient(fail_page=2)
    with harness.scope(), pytest.raises(RuntimeError, match="outage"):
        execute(harness, first)
    assert first.calls == [1, 2] and len(harness.service.checkpoints) == 1
    resumed = UnderstandingClient()
    with harness.scope():
        result = execute(harness, resumed)
        replay_client = UnderstandingClient(fail_page=1)
        replay = execute(harness, replay_client)
    assert resumed.calls == [2, 3] and replay_client.calls == []
    assert (result.resumed_pages, result.new_pages) == (1, 2)
    assert result.structure_sha256 == replay.structure_sha256
    checkpoint = harness.service.checkpoints[0]
    assert '"classification"' in checkpoint.raw_output and '"claims"' in checkpoint.raw_output
    assert checkpoint.invocation.configuration_sha256 == harness.service.configuration.fingerprint
    assert checkpoint.invocation.reported_model_version == "explicit-understanding-test-fixture"
    request = first.requests[0]
    assert (
        request.max_output_tokens,
        request.temperature,
        request.seed,
        request.timeout_seconds,
    ) == (14000, 0, None, 137)
    assert "merchant.address" in request.prompt and "line_item.coinsurance" in request.prompt
    assert len(harness.service.structure.pages) == 3


def test_source_and_frozen_settings_drift_fail_before_inference(understanding, monkeypatch):
    harness = understanding()
    client = UnderstandingClient()
    with harness.scope(), pytest.raises(ProcessingError, match="timeout"):
        execute(harness, client, timeout_seconds=180)
    config = harness.service.configuration
    for field in (
        "normalizer_sha256",
        "request_builder_sha256",
        "context_recipe_sha256",
        "profile_sha256",
    ):
        changed = config.model_copy(update={field: "0" * 64})
        harness.registered = harness.registered.model_copy(update={"configuration": changed})
        with harness.scope(), pytest.raises(ProcessingError, match="configuration"):
            execute(harness, client)
    harness.registered = harness.registered.model_copy(update={"configuration": config})
    monkeypatch.setattr(
        "lib.document_processing.parse_execution.freeze_document_context",
        lambda _: config.context.model_copy(update={"original_sha256": "a" * 64}),
    )
    with harness.scope(), pytest.raises(ProcessingError, match="context"):
        execute(harness, client)
    assert client.calls == []


@pytest.mark.parametrize(
    "field",
    [
        "context_sha256",
        "configuration_sha256",
        "request_sha256",
        "prompt_sha256",
        "source_inventory_sha256",
        "output_schema_sha256",
    ],
)
def test_tampered_v2_resume_binding_is_rejected_without_reinference(understanding, field):
    harness = understanding()
    with harness.scope():
        execute(harness, UnderstandingClient())
    old = harness.service.checkpoints[0]
    harness.service.checkpoints[0] = replace(
        old, invocation=old.invocation.model_copy(update={field: "0" * 64})
    )
    client = UnderstandingClient()
    with harness.scope(), pytest.raises(ValueError, match="request identity"):
        execute(harness, client)
    assert client.calls == []


def test_authority_lost_during_render_prevents_next_http(understanding, monkeypatch):
    harness = understanding()
    render = DocumentSource.render

    def revoked(source, *args, **kwargs):
        result = render(source, *args, **kwargs)
        harness.service.active = False
        return result

    monkeypatch.setattr(DocumentSource, "render", revoked)
    client = UnderstandingClient()
    with harness.scope(), pytest.raises(RuntimeError, match="authority"):
        execute(harness, client)
    assert client.calls == [] and harness.service.checkpoints == []


def test_authority_lost_during_response_prevents_checkpoint_and_next_http(understanding):
    harness = understanding()
    client = UnderstandingClient(after_generate=lambda: setattr(harness.service, "active", False))
    with harness.scope(), pytest.raises(RuntimeError, match="authority"):
        execute(harness, client)
    assert client.calls == [1] and harness.service.checkpoints == []


@pytest.mark.parametrize(
    "change", ["length", "raw_duplicate", "normalized_repair", "image", "oversize"]
)
def test_malformed_or_repaired_transport_cannot_checkpoint(understanding, change):
    harness = understanding()

    class WrongClient(UnderstandingClient):
        def generate(self, request):
            response = super().generate(request)
            updates = {
                "length": {"finish_reason": "length"},
                "raw_duplicate": {
                    "raw_text": response.raw_text.replace("{", '{"schema_version":"wrong",', 1)
                },
                "normalized_repair": {
                    "normalized_json": {**response.normalized_json, "page_number": 2}
                },
                "image": {"input_sha256": ("0" * 64,)},
                "oversize": {"raw_text": " " * 2_000_001},
            }
            return replace(response, **updates[change])

    with harness.scope(), pytest.raises(ProcessingError):
        execute(harness, WrongClient())
    assert harness.service.checkpoints == []


def test_real_vision_adapter_sends_one_bounded_request_and_retains_absent_report(understanding):
    harness = understanding(1)
    calls = []

    def respond(request):
        payload = json.loads(request.content)
        calls.append(payload)
        assert request.url.path == "/v1/chat/completions"
        assert "seed" not in payload
        assert payload["max_tokens"] == 14000 and payload["temperature"] == 0
        assert payload["chat_template_kwargs"] == {"enable_thinking": False}
        assert payload["response_format"]["json_schema"]["strict"] is True
        assert "structured_outputs" not in payload
        assert len(payload["messages"]) == 1
        image = payload["messages"][0]["content"][1]
        assert image["image_url"]["url"].startswith("data:image/png;base64,")
        return httpx.Response(
            200,
            json={
                "model": "qwen38-27b-bf16-oxcart",
                "choices": [
                    {"message": {"content": json.dumps(invoice_page())}, "finish_reason": "stop"}
                ],
            },
        )

    client = QwenVLClient(
        profile=get_model_profile(QWEN_INGESTION_PROFILE),
        http_client_base_url="http://fixture.invalid",
        transport=httpx.MockTransport(respond),
    )
    with harness.scope():
        execute(harness, client)
        execute(harness, client)
    assert len(calls) == 1
    assert harness.service.checkpoints[0].invocation.reported_model_version is None
