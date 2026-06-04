from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


def _load_acceptance_runner():
    script_path = (
        Path(__file__).resolve().parents[3]
        / "scripts"
        / "gpu"
        / "run_phase8_5_resident_acceptance.py"
    )
    spec = importlib.util.spec_from_file_location(
        "run_phase8_5_resident_acceptance",
        script_path,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_resident_acceptance_runner_invokes_two_passes_and_acceptance(monkeypatch, tmp_path):
    runner = _load_acceptance_runner()
    manifest = tmp_path / "resident.json"
    manifest.write_text('{"documents":[{"path":"/tmp/a.pdf"}]}', encoding="utf-8")
    report_dir = tmp_path / "reports"
    calls: list[list[str]] = []

    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_phase8_5_resident_acceptance.py",
            "--manifest",
            str(manifest),
            "--report-dir",
            str(report_dir),
            "--run-id-prefix",
            "phase85-test",
            "--timeout-seconds",
            "30",
        ],
    )

    assert runner.main() == 0

    assert len(calls) == 3
    assert calls[0][:2] == [sys.executable, str(runner.RESIDENT_RUNNER)]
    assert calls[0][calls[0].index("--run-id") + 1] == "phase85-test-pass-1"
    assert calls[1][calls[1].index("--run-id") + 1] == "phase85-test-pass-2"
    assert calls[2][:2] == [sys.executable, str(runner.REPORT_ACCEPTANCE)]
    assert str(report_dir / "phase85-test-pass-1-report.json") in calls[2]
    assert str(report_dir / "phase85-test-pass-2-report.json") in calls[2]


def test_resident_acceptance_runner_returns_failure_when_acceptance_fails(monkeypatch, tmp_path):
    runner = _load_acceptance_runner()
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.7\n")
    report_dir = tmp_path / "reports"

    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if str(runner.REPORT_ACCEPTANCE) in command:
            return subprocess.CompletedProcess(
                command,
                1,
                stdout=json.dumps({"status": "failed"}),
                stderr="",
            )
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_phase8_5_resident_acceptance.py",
            "--pdf",
            str(pdf),
            "--report-dir",
            str(report_dir),
        ],
    )

    assert runner.main() == 1
