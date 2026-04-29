from __future__ import annotations

from pathlib import Path


def test_qwen_vllm_start_script_forwards_mm_processor_kwargs() -> None:
    script = Path("workers/model_services/start_qwen_vllm.sh").read_text()

    assert "STRUCTURA_VLLM_MM_PROCESSOR_KWARGS" in script
    assert "--mm-processor-kwargs" in script
