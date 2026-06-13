from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


def _load_e4_runner():
    script_path = (
        Path(__file__).resolve().parents[3] / "scripts" / "gpu" / "run_phase8_5_e4_vision_ab.py"
    )
    spec = importlib.util.spec_from_file_location(
        "run_phase8_5_e4_vision_ab",
        script_path,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_e4_vision_ab_runner_recreates_runtime_for_granite_then_qwen(
    monkeypatch,
    tmp_path,
) -> None:
    runner = _load_e4_runner()
    manifest = tmp_path / "resident.json"
    manifest.write_text('{"documents":[{"path":"/tmp/a.pdf"}]}', encoding="utf-8")
    report_dir = tmp_path / "reports"
    calls: list[tuple[list[str], dict[str, str] | None]] = []

    def fake_run(
        command: list[str],
        **kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        env = kwargs.get("env")
        calls.append((command, env if isinstance(env, dict) else None))
        if str(runner.RESIDENT_ACCEPTANCE) in command:
            _write_mode_reports(command, runner.QWEN_VISION_PROFILE)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_phase8_5_e4_vision_ab.py",
            "--manifest",
            str(manifest),
            "--report-dir",
            str(report_dir),
            "--run-id-prefix",
            "phase85-e4-test",
            "--timeout-seconds",
            "30",
        ],
    )

    assert runner.main() == 0

    assert len(calls) == 4
    granite_bringup, granite_env = calls[0]
    granite_acceptance, _ = calls[1]
    qwen_bringup, qwen_env = calls[2]
    qwen_acceptance, _ = calls[3]

    assert granite_bringup[:2] == ["bash", str(runner.LIVE_BRINGUP)]
    assert granite_env is not None
    assert granite_env["STRUCTURA_MODEL_MODE"] == "live"
    assert granite_env["STRUCTURA_QWEN_VISION_FALLBACK"] == "false"

    assert qwen_bringup[:2] == ["bash", str(runner.LIVE_BRINGUP)]
    assert qwen_env is not None
    assert qwen_env["STRUCTURA_MODEL_MODE"] == "live"
    assert qwen_env["STRUCTURA_QWEN_VISION_FALLBACK"] == "true"

    assert granite_acceptance[:2] == [sys.executable, str(runner.RESIDENT_ACCEPTANCE)]
    assert granite_acceptance[granite_acceptance.index("--run-id-prefix") + 1] == (
        "phase85-e4-test-granite"
    )
    assert str(report_dir / "granite") in granite_acceptance
    assert qwen_acceptance[:2] == [sys.executable, str(runner.RESIDENT_ACCEPTANCE)]
    assert qwen_acceptance[qwen_acceptance.index("--run-id-prefix") + 1] == ("phase85-e4-test-qwen")
    assert str(report_dir / "qwen") in qwen_acceptance


def test_e4_vision_ab_runner_stops_when_qwen_acceptance_fails(
    monkeypatch,
    tmp_path,
) -> None:
    runner = _load_e4_runner()
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.7\n")
    report_dir = tmp_path / "reports"
    calls: list[list[str]] = []

    def fake_run(
        command: list[str],
        **_kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        if str(runner.RESIDENT_ACCEPTANCE) in command and "phase85-e4-qwen" in command:
            return subprocess.CompletedProcess(command, 1, stdout="", stderr="")
        if str(runner.RESIDENT_ACCEPTANCE) in command:
            _write_mode_reports(command, runner.QWEN_VISION_PROFILE)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_phase8_5_e4_vision_ab.py",
            "--pdf",
            str(pdf),
            "--report-dir",
            str(report_dir),
            "--run-id-prefix",
            "phase85-e4",
            "--skip-preflight",
        ],
    )

    assert runner.main() == 1
    assert len(calls) == 4
    assert calls[0][-1] == "--skip-preflight"
    assert calls[2][-1] == "--skip-preflight"


def test_e4_vision_ab_report_validation_rejects_wrong_qwen_mode(tmp_path) -> None:
    runner = _load_e4_runner()
    report = tmp_path / "qwen-pass-1-report.json"
    report.write_text(
        json.dumps(
            {
                "runId": "phase85-e4-qwen-pass-1",
                "runManifest": {
                    "vision_fallback_provider": "granite",
                    "qwen_vision_fallback_enabled": False,
                },
            }
        ),
        encoding="utf-8",
    )

    failures = runner._mode_report_failures(
        mode="qwen",
        paths=[report],
        qwen_vision_profile=runner.QWEN_VISION_PROFILE,
    )

    assert failures == [
        {
            "report": str(report),
            "runId": "phase85-e4-qwen-pass-1",
            "invalid": [
                "runManifest.vision_fallback_provider",
                "runManifest.qwen_vision_fallback_enabled",
                "runManifest.qwen_vision_profile",
            ],
        }
    ]


def _write_mode_reports(command: list[str], qwen_vision_profile: str) -> None:
    report_dir = Path(command[command.index("--report-dir") + 1])
    run_id_prefix = command[command.index("--run-id-prefix") + 1]
    mode = "qwen" if run_id_prefix.endswith("-qwen") else "granite"
    report_dir.mkdir(parents=True, exist_ok=True)
    for pass_number in (1, 2):
        report = report_dir / f"{run_id_prefix}-pass-{pass_number}-report.json"
        manifest = {
            "vision_fallback_provider": mode,
            "qwen_vision_fallback_enabled": mode == "qwen",
        }
        if mode == "qwen":
            manifest["qwen_vision_profile"] = qwen_vision_profile
        report.write_text(
            json.dumps(
                {
                    "runId": f"{run_id_prefix}-pass-{pass_number}",
                    "runManifest": manifest,
                }
            ),
            encoding="utf-8",
        )
