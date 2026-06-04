from __future__ import annotations

import os
import shutil
import stat
import subprocess
import textwrap
from pathlib import Path


def _write_executable(path: Path, content: str) -> None:
    path.write_text(textwrap.dedent(content), encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def test_qwen_vllm_start_script_forwards_mm_processor_kwargs() -> None:
    script = Path("workers/model_services/start_qwen_vllm.sh").read_text()

    assert "STRUCTURA_VLLM_MM_PROCESSOR_KWARGS" in script
    assert "--mm-processor-kwargs" in script


def test_qwen_vllm_start_script_can_disable_prefix_caching() -> None:
    script = Path("workers/model_services/start_qwen_vllm.sh").read_text()

    assert "STRUCTURA_VLLM_DISABLE_PREFIX_CACHING" in script
    assert "--no-enable-prefix-caching" in script


def test_granite_vllm_start_script_can_disable_prefix_caching() -> None:
    script = Path("workers/model_services/start_granite_vllm.sh").read_text()

    assert "STRUCTURA_GRANITE_DISABLE_PREFIX_CACHING" in script
    assert "--no-enable-prefix-caching" in script


def test_phase8_5_live_bringup_forces_live_model_mode() -> None:
    script = Path("scripts/gpu/phase8_5_live_bringup.sh").read_text()

    assert 'export STRUCTURA_MODEL_MODE="${STRUCTURA_MODEL_MODE:-live}"' in script
    assert "phase8_5_live_runtime_preflight.py" in script
    assert "--force-recreate" in script
    assert "REMOVED_LEGACY_CONTAINERS" in script
    assert "structura-model-qwen-1" in script
    assert "worker-semantic-annotations" in script
    assert "worker-extraction" in script


def test_phase8_5_live_runtime_preflight_checks_container_modes() -> None:
    script = Path("scripts/gpu/phase8_5_live_runtime_preflight.py").read_text()

    assert "REQUIRED_LIVE_SERVICES" in script
    assert "MODEL_ENV_TARGETS" in script
    assert "STRUCTURA_MODEL_MODE" in script
    assert "Qwen/Qwen3-VL-8B-Instruct-FP8" in script
    assert "model-qwen-semantic" in script
    assert "model-granite" in script
    assert 'shutil.which("docker")' in script
    assert "_docker_compose_command(" in script
    assert "urlopen(" not in script
    assert "HTTPConnection" in script


def test_phase8_5_model_smoke_fails_before_gpu_probe_when_manifest_is_missing(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "nvidia-smi-was-called"
    _write_executable(
        tmp_path / "nvidia-smi",
        f"""\
        #!/usr/bin/env bash
        touch {marker}
        echo "0, NVIDIA Test GPU, 24564 MiB, 999.0"
        """,
    )
    _write_executable(
        tmp_path / "curl",
        """\
        #!/usr/bin/env bash
        exit 1
        """,
    )
    env = os.environ.copy()
    env["PATH"] = f"{tmp_path}{os.pathsep}{env.get('PATH', '')}"
    env["STRUCTURA_MODEL_CORPUS_MANIFEST"] = str(tmp_path / "missing-model-manifest.json")
    env["STRUCTURA_MODEL_SMOKE_HEALTH_TIMEOUT_SECONDS"] = "1"
    env["STRUCTURA_MODEL_SMOKE_HEALTH_POLL_SECONDS"] = "0"

    result = subprocess.run(
        [shutil.which("bash") or "bash", "scripts/gpu/phase8_5_model_smoke.sh"],
        cwd=Path.cwd(),
        env=env,
        text=True,
        capture_output=True,
        timeout=5,
        check=False,
    )

    assert result.returncode != 0
    output = result.stdout + result.stderr
    assert "Phase 8.5 model corpus manifest not found" in output
    assert "STRUCTURA_MODEL_CORPUS_MANIFEST" in output
    assert not marker.exists()
