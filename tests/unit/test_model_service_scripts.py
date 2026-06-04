from __future__ import annotations

from pathlib import Path


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
