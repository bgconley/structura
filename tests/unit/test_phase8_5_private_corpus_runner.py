from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

from lib.jobs.event_payloads import build_semantic_annotate_document_job_payload
from scripts.gpu.phase8_5_corpus_run_guard import (
    CORPUS_CONTAINER_LABEL,
    CORPUS_CONTAINER_RUN_LABEL,
    CorpusRunGuard,
)


def _load_private_corpus_runner():
    script_path = (
        Path(__file__).resolve().parents[2] / "scripts" / "gpu" / "run_phase8_5_private_corpus.py"
    )
    spec = importlib.util.spec_from_file_location(
        "run_phase8_5_private_corpus",
        script_path,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_private_corpus_default_actor_matches_semantic_job_contract(
    monkeypatch,
    tmp_path,
) -> None:
    runner = _load_private_corpus_runner()
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(b"%PDF-1.7\n")
    monkeypatch.setattr(
        sys,
        "argv",
        ["run_phase8_5_private_corpus.py", "--pdf", str(pdf_path)],
    )

    args = runner._parse_args()

    payload = build_semantic_annotate_document_job_payload(
        job_id=uuid4(),
        document_id=uuid4(),
        quality_mode="smart",
        semantic_quality_mode="smart",
        allow_8b_rescue=False,
        requested_by=args.requested_by,
        reason="phase8_5.private_corpus_standard_smart_pass",
    )
    assert payload["requested_by"] == args.requested_by
    assert payload["quality_mode"] == "smart"
    assert payload["semantic_quality_mode"] == "smart"
    assert payload["allow_8b_rescue"] is False


def test_private_corpus_manifest_argument_is_supported_without_committing_private_paths(
    monkeypatch,
    tmp_path,
) -> None:
    runner = _load_private_corpus_runner()
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(b"%PDF-1.7\n")
    manifest_path = tmp_path / "phase8_5_canary_manifest.local.json"
    manifest_path.write_text(
        '{"documents":[{"path":"' + str(pdf_path) + '","expected_family":"receipt"}]}',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_phase8_5_private_corpus.py",
            "--manifest",
            str(manifest_path),
        ],
    )

    args = runner._parse_args()

    assert args.manifest == manifest_path
    assert args.pdf == [pdf_path]
    assert args.lock_path == runner.CORPUS_LOCK_PATH


def test_private_corpus_one_off_containers_are_labeled_and_named(monkeypatch, tmp_path) -> None:
    runner = _load_private_corpus_runner()
    captured: dict[str, object] = {}

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["command"] = command
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(command, 0, stdout="{}", stderr="")

    guard = CorpusRunGuard(root=tmp_path, lock_path=tmp_path / "corpus.lock", title_prefix="test")
    guard.run_id = "20260501T000000Z-1234-abcdef12"
    monkeypatch.setattr(runner, "_ACTIVE_CORPUS_RUN", guard)
    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    runner._compose_python("worker-semantic-annotations", "print('ok')")

    command = captured["command"]
    assert isinstance(command, list)
    assert command[:3] == ["docker", "compose", "run"]
    assert "--name" in command
    assert "structura-phase85-" in command[command.index("--name") + 1]
    assert "--label" in command
    assert f"{CORPUS_CONTAINER_LABEL}=true" in command
    assert f"{CORPUS_CONTAINER_RUN_LABEL}=20260501T000000Z-1234-abcdef12" in command


def test_private_corpus_timeout_cleans_current_run_containers(monkeypatch) -> None:
    runner = _load_private_corpus_runner()
    cleaned: list[str] = []

    class FakeGuard:
        def compose_run_options(self, _service: str) -> list[str]:
            return []

        def cleanup_current_run_containers(self) -> None:
            cleaned.append("cleaned")

    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(command, timeout=10)

    monkeypatch.setattr(runner, "_ACTIVE_CORPUS_RUN", FakeGuard())
    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    try:
        runner._compose_python("worker-extraction", "print('ok')", timeout_seconds=10)
    except subprocess.TimeoutExpired:
        pass
    else:
        raise AssertionError("TimeoutExpired should propagate after cleanup")

    assert cleaned == ["cleaned"]


def test_private_corpus_summary_does_not_select_removed_document_parse_status() -> None:
    sql = (
        Path(__file__)
        .resolve()
        .parents[2]
        .joinpath("scripts/gpu/run_phase8_5_private_corpus.py")
        .read_text(encoding="utf-8")
    )

    assert "d.parse_status" not in sql
    assert "count(DISTINCT p.id) > 0" in sql


def test_cancel_text_embedding_jobs_types_corpus_actor_for_postgres(
    monkeypatch,
) -> None:
    runner = _load_private_corpus_runner()
    executed: dict[str, object] = {}

    class FakeCursor:
        def __enter__(self) -> FakeCursor:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def execute(self, sql: str, params: tuple[object, ...]) -> None:
            executed["sql"] = sql
            executed["params"] = params

    class FakeConnection:
        def __enter__(self) -> FakeConnection:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def cursor(self) -> FakeCursor:
            return FakeCursor()

        def commit(self) -> None:
            executed["committed"] = True

    monkeypatch.setattr(runner, "db_connection", lambda: FakeConnection())
    document_id = uuid4()

    runner._cancel_text_embedding_jobs(document_id)

    assert "'requested_by', %s::text" in str(executed["sql"])
    assert executed["params"] == (runner.CORPUS_RUN_ID, document_id)
    assert executed["committed"] is True


def test_private_corpus_extraction_drain_marks_model_timeout_as_fatal(
    monkeypatch,
    capsys,
) -> None:
    runner = _load_private_corpus_runner()
    document_id = uuid4()
    failed_jobs = [
        {
            "id": str(uuid4()),
            "job_type": "extract",
            "status": "failed",
            "error_json": {"error_class": "ModelTimeoutError"},
        }
    ]

    monkeypatch.setattr(runner, "_drain", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(
        runner,
        "_failed_jobs",
        lambda doc_id, *, queue_name: failed_jobs if queue_name == "extraction" else [],
    )

    try:
        runner._drain_extraction(document_id)
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("Model timeout should stop the corpus run by default")

    output = capsys.readouterr().out
    assert '"stage": "extraction_failures"' in output
    assert '"error_class": "ModelTimeoutError"' in output
    assert '"stage": "model_timeout_fatal"' in output
