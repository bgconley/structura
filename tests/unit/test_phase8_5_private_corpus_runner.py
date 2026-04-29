from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from uuid import uuid4

from lib.jobs.event_payloads import build_semantic_annotate_document_job_payload


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

    assert args.high_quality is False
    assert args.allow_8b_rescue is False
    assert args.rescue_stress is False
    payload = build_semantic_annotate_document_job_payload(
        job_id=uuid4(),
        document_id=uuid4(),
        quality_mode="smart",
        semantic_quality_mode="smart",
        allow_8b_rescue=args.allow_8b_rescue,
        requested_by=args.requested_by,
        reason="phase8_5.private_corpus_standard_smart_pass",
    )
    assert payload["requested_by"] == args.requested_by
    assert payload["quality_mode"] == "smart"
    assert payload["semantic_quality_mode"] == "smart"
    assert payload["allow_8b_rescue"] is False


def test_private_corpus_high_quality_flag_is_explicit(
    monkeypatch,
    tmp_path,
) -> None:
    runner = _load_private_corpus_runner()
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(b"%PDF-1.7\n")
    monkeypatch.setattr(
        sys,
        "argv",
        ["run_phase8_5_private_corpus.py", "--pdf", str(pdf_path), "--high-quality"],
    )

    args = runner._parse_args()

    assert args.high_quality is True
    assert args.allow_8b_rescue is False


def test_private_corpus_allow_8b_rescue_is_separate_from_hq(
    monkeypatch,
    tmp_path,
) -> None:
    runner = _load_private_corpus_runner()
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(b"%PDF-1.7\n")
    monkeypatch.setattr(
        sys,
        "argv",
        ["run_phase8_5_private_corpus.py", "--pdf", str(pdf_path), "--allow-8b-rescue"],
    )

    args = runner._parse_args()

    assert args.high_quality is False
    assert args.allow_8b_rescue is True
    assert args.rescue_stress is False


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
