"""No network: stream-level budget, truncation, failure and private retention."""

import hashlib
import json
import stat

import httpx
import pytest

from scripts.gpu.page_understanding_probe.observations import MAX_RETAINED_BODY, ObservedTransport


class Chunks(httpx.SyncByteStream):
    def __init__(self, values, fail=False):
        self.values, self.fail, self.yielded, self.closed = values, fail, 0, False

    def __iter__(self):
        for value in self.values:
            self.yielded += 1
            yield value
        if self.fail:
            raise httpx.ReadTimeout("Controlled private failure")

    def close(self):
        self.closed = True


def test_wire_prefix_is_bounded_without_eager_read_and_metadata_is_honest(tmp_path):
    chunk = b"x" * 65536
    stream = Chunks([chunk] * 18)
    transport = ObservedTransport(
        tmp_path,
        httpx.MockTransport(
            lambda request: httpx.Response(
                200, stream=stream, headers={"content-encoding": "identity"}
            )
        ),
    )
    with httpx.Client(transport=transport) as client:
        with client.stream("POST", "https://model.test/v1/chat/completions") as response:
            assert stream.yielded == 0
            assert sum(len(c) for c in response.iter_bytes()) == 18 * len(chunk)
    body = (tmp_path / "http-1.body").read_bytes()
    report = json.loads((tmp_path / "http-1.json").read_text())
    assert len(body) == MAX_RETAINED_BODY and stream.closed
    assert report["entire_wire_body_retained"] is False
    assert report["retained_sha256"] == hashlib.sha256(body).hexdigest()
    assert transport.started == transport.responses == 1
    for path in tmp_path.iterdir():
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_interrupted_body_keeps_only_observed_bytes_and_incomplete_flag(tmp_path):
    stream = Chunks([b'{"partial":'], fail=True)
    transport = ObservedTransport(
        tmp_path, httpx.MockTransport(lambda r: httpx.Response(200, stream=stream))
    )
    with httpx.Client(transport=transport) as client, pytest.raises(httpx.ReadTimeout):
        client.post("https://model.test/v1/chat/completions")
    assert (tmp_path / "http-1.body").read_bytes() == b'{"partial":'
    report = json.loads((tmp_path / "http-1.json").read_text())
    assert not report["entire_wire_body_retained"] and stream.closed


def test_three_actual_attempts_no_fourth_or_wrong_route(tmp_path):
    calls = []

    def respond(request):
        calls.append(request.url.path)
        return httpx.Response(400, stream=Chunks([b'{"error":"controlled"}']))

    transport = ObservedTransport(tmp_path, httpx.MockTransport(respond))
    with httpx.Client(transport=transport) as client:
        for _ in range(3):
            assert client.post("https://model.test/v1/chat/completions").status_code == 400
        with pytest.raises(RuntimeError, match="budget"):
            client.post("https://model.test/v1/chat/completions")
    assert len(calls) == 3 and transport.started == transport.responses == 3
    assert json.loads((tmp_path / "http-3.json").read_text())["entire_wire_body_retained"]
    other = ObservedTransport(tmp_path, httpx.MockTransport(respond))
    with pytest.raises(RuntimeError):
        other.handle_request(httpx.Request("POST", "https://model.test/v1/models"))
    assert other.started == 0 and len(calls) == 3


def test_connection_failure_records_attempt_without_claiming_response(tmp_path):
    def fail(request):
        raise httpx.ConnectError("Never log credentials or private endpoint data")

    transport = ObservedTransport(tmp_path, httpx.MockTransport(fail))
    with pytest.raises(httpx.ConnectError):
        transport.handle_request(httpx.Request("POST", "https://model.test/v1/chat/completions"))
    assert transport.started == 1 and transport.responses == 0
    assert json.loads((tmp_path / "http-1.json").read_text()) == {
        "attempt": 1,
        "response_received": False,
        "body_retained": False,
    }


def test_production_status_rejection_still_retains_bounded_error_body(tmp_path):
    from lib.model_runtime.http_client import ModelHttpClient, ModelProtocolError

    body = b'{"error":"synthetic controlled rejection"}'
    stream = Chunks([body])
    transport = ObservedTransport(
        tmp_path, httpx.MockTransport(lambda r: httpx.Response(400, stream=stream))
    )
    client = ModelHttpClient(base_url="https://model.test", transport=transport)
    with pytest.raises(ModelProtocolError, match="HTTP 400"):
        client.post_json("/v1/chat/completions", {})
    assert (tmp_path / "http-1.body").read_bytes() == body
    report = json.loads((tmp_path / "http-1.json").read_text())
    assert report["entire_wire_body_retained"] and not report["diagnostic_drain_failed"]
    assert transport.started == 1 and stream.closed


def test_failure_body_drain_does_not_hide_status_or_exceed_limit(tmp_path):
    from lib.model_runtime.http_client import ModelHttpClient, ModelServiceError

    stream = Chunks([b"z" * 65536] * 30, fail=True)
    transport = ObservedTransport(
        tmp_path, httpx.MockTransport(lambda r: httpx.Response(500, stream=stream))
    )
    client = ModelHttpClient(base_url="https://model.test", transport=transport)
    with pytest.raises(ModelServiceError, match="HTTP 500"):
        client.post_json("/v1/chat/completions", {})
    assert len((tmp_path / "http-1.body").read_bytes()) == MAX_RETAINED_BODY
    assert stream.yielded == 16 and stream.closed
    assert not json.loads((tmp_path / "http-1.json").read_text())["entire_wire_body_retained"]


def test_adapter_refuses_changed_seed_or_budget_before_call_and_keeps_raw_response(tmp_path):
    from dataclasses import replace

    from lib.document_processing.configuration_types import ParseRequestSettings
    from lib.model_runtime.contracts import VisionGenerateRequest, VisionGenerateResponse
    from scripts.gpu.page_understanding_probe.observations import ObservedClient

    settings = ParseRequestSettings(
        max_output_tokens=14000, temperature=0, seed=None, timeout_seconds=137
    )
    calls = []

    class Client:
        def generate(self, request):
            calls.append(request)
            return VisionGenerateResponse(
                profile_name="test",
                model_name="test",
                model_version="",
                source_engine="test",
                prompt_version="test",
                raw_text='{"observed":true}',
                normalized_json={"observed": True},
                confidence_json={},
                input_sha256=(),
                latency_ms=1,
                finish_reason="stop",
                usage_json={"completion_tokens": 7},
                structured_output_used=True,
            )

    observed = ObservedClient(Client(), settings, tmp_path)
    request = VisionGenerateRequest(
        profile_name="test",
        prompt_version="test",
        prompt="source prompt",
        image_inputs=(),
        response_schema_name="test",
        max_output_tokens=14000,
        temperature=0,
        timeout_seconds=137,
        seed=None,
    )
    for changed in (
        replace(request, seed=0),
        replace(request, max_output_tokens=8192),
        replace(request, timeout_seconds=180),
    ):
        with pytest.raises(RuntimeError):
            observed.generate(changed)
    assert calls == [] and observed.started == 0
    for _ in range(3):
        observed.generate(request)
    with pytest.raises(RuntimeError):
        observed.generate(request)
    assert len(calls) == observed.started == observed.completed == 3
    retained = json.loads((tmp_path / "response-1.json").read_text())
    assert retained["raw_output"] == '{"observed":true}'
    assert retained["reported_model_version"] is None
    assert retained["usage"] == {"completion_tokens": 7}
