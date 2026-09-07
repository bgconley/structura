"""Pre-inference failure diagnosis remains private, static and exclusive."""

import json
import stat
from types import SimpleNamespace

from lib.model_runtime.http_client import ModelProtocolError
from scripts.gpu import probe_page_understanding as probe


def test_preflight_failure_gets_private_stage_code_without_exception_text(
    tmp_path, monkeypatch, capsys
):
    output = tmp_path / "fresh"
    monkeypatch.setattr(probe, "arguments", lambda: SimpleNamespace(output_dir=output))

    def failed(args, progress):
        progress.stage = "frozen_parser_configuration"
        raise RuntimeError("PRIVATE TOKEN CONNECTION STRING OR SOURCE TEXT")

    monkeypatch.setattr(probe, "run", failed)
    assert probe.main() == 1
    captured = capsys.readouterr()
    assert "PRIVATE" not in captured.out + captured.err
    report = json.loads((output / "failed-stage.json").read_text())
    assert report["stage"] == "frozen_parser_configuration"
    assert report["code"] == "probe_stage_failed"
    assert report["exception_text_retained"] is False
    assert "PRIVATE" not in (output / "failed-stage.json").read_text()
    assert stat.S_IMODE(output.stat().st_mode) == 0o700
    assert stat.S_IMODE((output / "failed-stage.json").stat().st_mode) == 0o600


def test_previous_output_namespace_is_never_modified(tmp_path):
    before = tmp_path / "failed-stage.json"
    before.write_text("previous immutable evidence")
    probe.record_failed_stage(tmp_path, probe.ProbeProgress(), RuntimeError("private"))
    assert before.read_text() == "previous immutable evidence"


def test_protocol_error_distinguishes_model_rejection_without_raw_message(tmp_path):
    output = tmp_path / "fresh"
    probe.record_failed_stage(
        output,
        probe.ProbeProgress(stage="candidate_parse_replay_and_retention"),
        ModelProtocolError("PRIVATE MODEL OUTPUT"),
    )
    assert (
        json.loads((output / "failed-stage.json").read_text())["code"] == "model_protocol_rejected"
    )
