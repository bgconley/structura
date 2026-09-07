from __future__ import annotations

import json
import socket
import subprocess
import threading
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import httpx
import psycopg
import pytest
import yaml

import lib.uploads.cleanup as cleanup
import workers.upload_cleanup.runtime_repository as runtime_repository
import workers.upload_cleanup.worker as worker
from lib.storage.verified_publication import PublicationConflict
from lib.uploads.cleanup import CleanupSweep
from lib.uploads.policy import UploadPolicy
from lib.uploads.staging import UploadStaging
from tests.unit.uploads.test_storage import storage_at
from workers.upload_cleanup.configuration import CleanupRuntimeConfiguration, retry_delay
from workers.upload_cleanup.health import CleanupHealth, start_cleanup_health
from workers.upload_cleanup.runtime_repository import CleanupRuntimeUnavailable


def test_sweep_continues_after_poison_and_busy_sources_without_waiving_cleanup(monkeypatch):
    identities = tuple(uuid4() for _ in range(3))
    attempted = []
    monkeypatch.setattr(cleanup, "expire_inactive_attempts", lambda **_: 2)
    monkeypatch.setattr(cleanup, "cleanup_candidates", lambda **_: identities)

    def clean(_staging, identity, _policy):
        attempted.append(identity)
        if identity == identities[0]:
            raise PublicationConflict("private filename")
        return identity == identities[2]

    monkeypatch.setattr(cleanup, "clean_transfer", clean)
    result = cleanup.sweep_expired_uploads(None, UploadPolicy())
    assert attempted == list(identities)
    assert (result.inactive_expired, result.cleaned, result.deferred, result.failed) == (2, 1, 1, 1)
    assert result.error_codes == ("cleanup_source_conflict",)


def test_sweep_stops_new_claims_after_stop_or_budget_and_does_not_hide_db_failure(monkeypatch):
    identities = tuple(uuid4() for _ in range(3))
    monkeypatch.setattr(cleanup, "expire_inactive_attempts", lambda **_: 0)
    monkeypatch.setattr(cleanup, "cleanup_candidates", lambda **_: identities)
    stop = threading.Event()
    attempted = []

    def clean(*_):
        attempted.append(1)
        stop.set()
        return True

    monkeypatch.setattr(cleanup, "clean_transfer", clean)
    result = cleanup.sweep_expired_uploads(None, UploadPolicy(), should_stop=stop.is_set)
    assert result.cleaned == 1 and result.interrupted and len(attempted) == 1
    clock = iter([100, 100.1])
    monkeypatch.setattr(cleanup.time, "monotonic", lambda: next(clock))
    result = cleanup.sweep_expired_uploads(
        None,
        UploadPolicy(),
        budget_seconds=0.001,
    )
    assert result.attempted == 0 and result.interrupted
    monkeypatch.setattr(cleanup.time, "monotonic", lambda: 100)

    def fail(*_):
        raise psycopg.OperationalError("private password or source")

    monkeypatch.setattr(cleanup, "clean_transfer", fail)
    result = cleanup.sweep_expired_uploads(None, UploadPolicy())
    assert result.attempted == 1 and result.error_codes == ("cleanup_database_unavailable",)


def test_private_health_distinguishes_liveness_stale_dependency_and_clean_stop(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr("workers.upload_cleanup.health.time.monotonic", lambda: clock[0])
    health = CleanupHealth(90)
    assert health.snapshot()[0] == 503
    health.finish(succeeded=True)
    assert health.snapshot()[0] == 200
    clock[0] += 91
    assert health.snapshot()[1]["status"] == "stalled"
    health.progress()
    health.finish(succeeded=False)
    assert health.snapshot()[1]["status"] == "degraded"
    health.stop()
    health.finish(succeeded=True)
    assert health.snapshot()[1]["status"] == "stopping"
    with socket.socket() as available:
        available.bind(("127.0.0.1", 0))
        port = available.getsockname()[1]
    server = start_cleanup_health(health, port)
    try:
        assert server.server_address[0] == "127.0.0.1"
        assert httpx.get(f"http://127.0.0.1:{port}/livez").status_code == 200
        assert httpx.get(f"http://127.0.0.1:{port}/healthz").status_code == 503
        response = httpx.get(f"http://127.0.0.1:{port}/private-file")
        assert response.status_code == 404 and response.json() == {"status": "unavailable"}
    finally:
        server.shutdown()
        server.server_close()


def test_runtime_database_query_override_and_actual_connection_mismatch_fail_closed(monkeypatch):
    monkeypatch.setenv("STRUCTURA_RUNTIME_ROOT", "/configured/runtime")
    monkeypatch.setenv("STRUCTURA_DATABASE_URL", "postgresql:///safe?dbname=wrong")
    monkeypatch.setattr(runtime_repository, "upload_connection", lambda: pytest.fail("connected"))
    with pytest.raises(CleanupRuntimeUnavailable, match="cleanup_database_mismatch"):
        runtime_repository.validate_runtime_database("safe")
    monkeypatch.setenv("STRUCTURA_DATABASE_URL", "postgresql:///safe")

    @contextmanager
    def cursor():
        yield SimpleNamespace(execute=lambda *_: pytest.fail("SQL ran on wrong database"))

    @contextmanager
    def connection():
        yield SimpleNamespace(info=SimpleNamespace(dbname="wrong"), cursor=cursor)

    monkeypatch.setattr(runtime_repository, "upload_connection", connection)
    with pytest.raises(CleanupRuntimeUnavailable, match="cleanup_database_mismatch"):
        runtime_repository.validate_runtime_database("safe")


def test_backoff_reset_failure_isolation_and_content_free_events(tmp_path, monkeypatch):
    events, delays, health_records = [], [], []

    class Stop(threading.Event):
        def wait(self, timeout=None):
            delays.append(timeout)
            return self.is_set()

    stop = Stop()
    health = CleanupHealth(90)
    results = iter(
        [
            CleanupSweep(failed=1, error_codes=("cleanup_storage_unavailable",)),
            CleanupSweep(failed=1, error_codes=("cleanup_storage_unavailable",)),
            CleanupSweep(cleaned=1),
            CleanupSweep(deferred=1),
        ]
    )
    monkeypatch.setattr(worker, "ObjectStorage", lambda: storage_at(tmp_path))
    UploadStaging(storage_at(tmp_path))  # API/provisioning establishes the namespace first.
    monkeypatch.setattr(worker, "validate_runtime_database", lambda _: None)
    monkeypatch.setattr(worker, "record_cleanup_health", lambda *args: health_records.append(args))
    monkeypatch.setattr(worker, "log_event", lambda event, **fields: events.append((event, fields)))

    def sweep(*_args, **_kwargs):
        result = next(results)
        if result.deferred:
            stop.set()
        return result

    monkeypatch.setattr(worker, "sweep_expired_uploads", sweep)
    config = CleanupRuntimeConfiguration(expected_database="safe")
    assert worker.run_cleanup_worker(config, stop, health) == 0
    assert delays == [15, 30, 15, 15]
    assert [status for status, _ in health_records] == ["degraded", "degraded", "ok", "ok"]
    assert health.snapshot()[1]["consecutiveFailures"] == 0
    assert all("filename" not in json.dumps(event) for event in events)
    assert retry_delay(15, 999999) == 120


def test_unknown_runtime_error_never_writes_unverified_db_or_logs_its_message(monkeypatch):
    events = []

    def invalid(_):
        raise CleanupRuntimeUnavailable("private filename and secret")

    monkeypatch.setattr(worker, "validate_runtime_database", invalid)
    monkeypatch.setattr(worker, "record_cleanup_health", lambda *_: pytest.fail("unverified write"))
    monkeypatch.setattr(worker, "log_event", lambda event, **fields: events.append((event, fields)))
    result = worker.run_cleanup_worker(
        CleanupRuntimeConfiguration(expected_database="safe"),
        threading.Event(),
        CleanupHealth(90),
        once=True,
    )
    assert result == 1
    assert "private filename" not in json.dumps(events)
    assert "cleanup_configuration_unavailable" in json.dumps(events)


def test_core_compose_worker_has_same_policy_storage_and_no_model_or_public_port():
    config = yaml.safe_load(Path("compose.yaml").read_text())
    api = config["services"]["api"]
    service = config["services"]["worker-upload-cleanup"]
    assert service["restart"] == "unless-stopped" and service["init"]
    assert service["build"] == api["build"] and service["group_add"] == api["group_add"]
    assert set(service["depends_on"]) == {"postgres"}
    assert set(service).isdisjoint({"ports", "profiles", "deploy", "gpus", "devices"})
    assert len(service["volumes"]) == 1 and "objects/canonical" in service["volumes"][0]
    for key in config["x-upload-policy"]:
        assert api["environment"][key] == service["environment"][key]
    assert not any("MODEL" in key for key in service["environment"])


def test_real_worker_process_rejects_missing_configuration_without_traceback(monkeypatch):
    import os
    import sys

    environment = dict(os.environ)
    environment.pop("STRUCTURA_UPLOAD_CLEANUP_EXPECTED_DATABASE", None)
    result = subprocess.run(
        [sys.executable, "-m", "workers.upload_cleanup.worker", "--once"],
        env=environment,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 2
    assert "Traceback" not in result.stdout + result.stderr
    assert "cleanup_configuration_unavailable" in result.stderr
