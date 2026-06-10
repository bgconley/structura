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


def test_phase8_5_live_runtime_preflight_checks_profile_registry_limits() -> None:
    script = Path("scripts/gpu/phase8_5_live_runtime_preflight.py").read_text()

    assert "MODEL_LIMIT_TARGETS" in script
    assert "required_live_profile_names" in script
    assert "STRUCTURA_GRANITE_MAX_MODEL_LEN" in script
    assert "STRUCTURA_GRANITE_LIMIT_MM_PER_PROMPT" in script
    assert "STRUCTURA_VLLM_MAX_MODEL_LEN" in script
    assert "STRUCTURA_VLLM_LIMIT_MM_PER_PROMPT" in script
    assert "model-vl-embed" in script


def test_phase8_5_live_runtime_preflight_limit_checks_use_profile_registry(monkeypatch) -> None:
    from scripts.gpu import phase8_5_live_runtime_preflight as preflight

    granite_env = {
        "STRUCTURA_GRANITE_MAX_MODEL_LEN": "16384",
        "STRUCTURA_GRANITE_LIMIT_MM_PER_PROMPT": '{"image":1,"video":0}',
    }
    monkeypatch.setattr(preflight, "_compose_exec_env", lambda _service: granite_env)

    ok_result = preflight._check_model_service_limits(
        "model-granite",
        preflight.MODEL_LIMIT_TARGETS["model-granite"],
    )
    assert ok_result.ok is True

    granite_env["STRUCTURA_GRANITE_MAX_MODEL_LEN"] = "32768"
    granite_env["STRUCTURA_GRANITE_LIMIT_MM_PER_PROMPT"] = '{"image":4,"video":0}'
    drift_result = preflight._check_model_service_limits(
        "model-granite",
        preflight.MODEL_LIMIT_TARGETS["model-granite"],
    )
    assert drift_result.ok is False
    assert "16384" in drift_result.message
    assert "image limit" in drift_result.message

    registry_result = preflight._check_required_live_profiles_registered()
    assert registry_result.ok is True


def test_granite_start_script_default_max_model_len_matches_compose() -> None:
    script = Path("workers/model_services/start_granite_vllm.sh").read_text()

    assert 'max_model_len="${STRUCTURA_GRANITE_MAX_MODEL_LEN:-16384}"' in script


def test_text_embed_start_script_selects_router_binary_by_compute_capability() -> None:
    script = Path("workers/model_services/start_text_embed.sh").read_text()

    assert "exec text-embeddings-router-120" not in script
    assert "STRUCTURA_TEI_ROUTER_BINARY" in script
    assert "compute_cap" in script
    assert 'command -v "text-embeddings-router-${compute_cap}"' in script
    assert 'exec "$router_binary"' in script


def test_phase8_5_model_smoke_probes_models_before_manifest_gate_when_manifest_is_missing(
    tmp_path: Path,
) -> None:
    nvidia_marker = tmp_path / "nvidia-smi-was-called"
    python_marker = tmp_path / "python-probe-was-called"
    _write_executable(
        tmp_path / "nvidia-smi",
        f"""\
        #!/usr/bin/env bash
        touch {nvidia_marker}
        echo "0, NVIDIA Test GPU, 24564 MiB, 999.0"
        """,
    )
    _write_executable(
        tmp_path / "curl",
        """\
        #!/usr/bin/env bash
        exit 0
        """,
    )
    _write_executable(
        tmp_path / "python-probe",
        f"""\
        #!/usr/bin/env bash
        touch {python_marker}
        case "$1" in
          scripts/gpu/probe_phase8_5_live_models.py)
            exit 0
            ;;
          *)
            echo "unexpected python command: $*" >&2
            exit 2
            ;;
        esac
        """,
    )
    env = os.environ.copy()
    env["PATH"] = f"{tmp_path}{os.pathsep}{env.get('PATH', '')}"
    env["PYTHON"] = str(tmp_path / "python-probe")
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
    assert nvidia_marker.exists()
    assert python_marker.exists()


def test_phase8_5_model_smoke_restores_gpu1_models_in_staged_order() -> None:
    script = Path("scripts/gpu/phase8_5_model_smoke.sh").read_text()

    assert "compose_model up -d --force-recreate model-granite model-vl-embed" not in script
    restore_block = script.split("remove_model_services model-embed", maxsplit=1)[1]
    granite_start = restore_block.index(
        'compose_model up -d --force-recreate "${BLACKWELL_BASE_SERVICES[@]}"'
    )
    granite_health = restore_block.index('probe_health "model-granite" "${GRANITE_URL}"')
    visual_start = restore_block.index("compose_model up -d --force-recreate model-vl-embed")
    visual_health = restore_block.index('probe_health "model-vl-embed" "${VISUAL_EMBED_URL}"')
    restored_probe = restore_block.index("probe_live_models --skip-qwen-semantic --skip-text-embed")

    assert granite_start < granite_health < visual_start < visual_health < restored_probe


def test_phase8_5_model_smoke_runs_live_phase8_e2e() -> None:
    script = Path("scripts/gpu/phase8_5_model_smoke.sh").read_text()

    assert "run_phase8_live_e2e" in script
    assert "STRUCTURA_E2E_LIVE=1" in script
    assert "tests/e2e/phase8-live.spec.ts" in script


def test_gpu_live_smoke_schedule_runs_model_smoke() -> None:
    workflow = Path(".github/workflows/gpu-live-smoke.yml").read_text()

    assert "github.event_name == 'schedule' || inputs.run_model_smoke == 'true'" in workflow
