"""Probe orchestration only: fake services prove ACK ordering and losing-claim behavior."""

import json
from contextlib import contextmanager, nullcontext
from types import SimpleNamespace
from uuid import uuid4

import pytest

from lib.document_processing.models import ProcessingBinding, ProcessingRun
from lib.document_processing.parse_execution import ParseExecutionResult
from lib.jobs.errors import JobOwnershipLost
from scripts.gpu.page_understanding_probe import execution


@pytest.fixture
def harness(tmp_path, monkeypatch):
    run = ProcessingRun(
        ProcessingBinding(uuid4(), uuid4(), uuid4()), uuid4(), 1, uuid4(), "requested"
    )
    claimed = SimpleNamespace(state=SimpleNamespace(job_id=run.root_job_id), claim_token=uuid4())
    client = SimpleNamespace(started=0, completed=0)
    transport = SimpleNamespace(started=0, responses=0)
    events = []

    class Service:
        def start_parse(self, **kwargs):
            events.append("start")
            return run

    class Jobs:
        def claim_next_job_record(self, **kwargs):
            events.append("claim")
            return claimed

        def complete_job(self, **kwargs):
            assert kwargs["claim_token"] == claimed.claim_token
            events.append("ack")

        def fail_job(self, **kwargs):
            assert kwargs["retryable"] is False
            assert kwargs["claim_token"] == claimed.claim_token
            events.append("fail")

    calls = []

    def parse(*args, **kwargs):
        calls.append(kwargs)
        events.append("parse" if len(calls) == 1 else "replay")
        if len(calls) == 1:
            client.started = client.completed = transport.started = transport.responses = 3
        return ParseExecutionResult(
            "a" * 64,
            3,
            0 if len(calls) == 1 else 3,
            3 if len(calls) == 1 else 0,
            3,
            "declared-live:test",
        )

    def retain(*args):
        events.append("retain")
        return {"sealed": True}

    def snapshot(*args):
        events.append("snapshot")

    monkeypatch.setattr(execution, "DocumentProcessingService", Service)
    monkeypatch.setattr(execution, "JobService", Jobs)
    monkeypatch.setattr(execution, "keep_job_lease", lambda *a, **k: nullcontext())
    monkeypatch.setattr(execution, "execute_parse_candidate", parse)
    monkeypatch.setattr(execution, "retain_and_replay", retain)
    monkeypatch.setattr(execution, "snapshot_generation", snapshot)
    source = SimpleNamespace(
        document_id=run.binding.document_id,
        principal=object(),
        asset_id=uuid4(),
        stored=SimpleNamespace(sha256="a" * 64),
        storage=object(),
    )
    return SimpleNamespace(
        run=run,
        source=source,
        client=client,
        transport=transport,
        events=events,
        configuration=object(),
        deployment=object(),
        output=tmp_path,
        calls=calls,
    )


def execute(harness):
    return execution.ingest_and_replay(
        harness.source,
        harness.configuration,
        harness.deployment,
        harness.client,
        harness.transport,
        harness.output,
    )


def test_retention_and_exact_snapshot_precede_ack(harness):
    run, report = execute(harness)
    assert run == harness.run
    assert harness.events == ["start", "claim", "parse", "replay", "retain", "snapshot", "ack"]
    assert report["actual_http_attempts"] == 3
    assert report["replay_http_attempts"] == 0
    assert all(call["batch_pages"] == 1 for call in harness.calls)


@pytest.mark.parametrize("boundary", ["execute_parse_candidate", "retain_and_replay"])
def test_failure_prevents_ack_and_preserves_diagnostics_without_retry(
    harness, monkeypatch, boundary
):
    def fail(*args, **kwargs):
        raise RuntimeError("Private failure")

    monkeypatch.setattr(execution, boundary, fail)
    with pytest.raises(RuntimeError, match="Private"):
        execute(harness)
    assert "ack" not in harness.events
    assert harness.events[-2:] == ["snapshot", "fail"]
    report = json.loads((harness.output / "failure-lifecycle.json").read_text())
    assert report == {"persisted_snapshot_retained": True, "failure_recorded_under_claim": True}


def test_absorbed_job_ownership_loss_is_not_a_success(harness, monkeypatch):
    @contextmanager
    def losing_lease(*args, **kwargs):
        try:
            yield
        except JobOwnershipLost:
            pass

    def lose(*args, **kwargs):
        raise JobOwnershipLost("Controlled lost claim")

    monkeypatch.setattr(execution, "keep_job_lease", losing_lease)
    monkeypatch.setattr(execution, "execute_parse_candidate", lose)
    with pytest.raises(RuntimeError, match="ownership"):
        execute(harness)
    assert "ack" not in harness.events and harness.events[-1] == "fail"


def test_unexpected_replay_invocation_cannot_ack(harness, monkeypatch):
    original = execution.execute_parse_candidate

    def extra(*args, **kwargs):
        result = original(*args, **kwargs)
        if len(harness.calls) == 2:
            harness.transport.started += 1
        return result

    monkeypatch.setattr(execution, "execute_parse_candidate", extra)
    with pytest.raises(RuntimeError, match="attempts"):
        execute(harness)
    assert "ack" not in harness.events
