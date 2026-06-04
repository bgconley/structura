from __future__ import annotations

import re
from pathlib import Path

README = Path("README.md")
SEMANTIC_PLAN = Path("STRUCTURA_PHASE_8_5_SEMANTIC_ANNOTATION_PLAN.md")
EVENT_CONTRACT_NOTES = Path("contracts/events/README.md")
PHASE85_PLAN = Path("STRUCTURA_PHASE_8_5_IMPLEMENTATION_PLAN.md")
PHASE9_PLAN = Path("STRUCTURA_PHASE_9_IMPLEMENTATION_PLAN.md")
ROOT_PLAN = Path("STRUCTURA_IMPLEMENTATION_PLAN.md")
MODEL_CORPUS_README = Path("tests/fixtures/model_corpus/README.md")


def test_readme_uses_model_corpus_runner_for_model_backed_release_gate() -> None:
    content = README.read_text(encoding="utf-8")

    assert "run_golden_corpus.py --require-model-backed" not in content
    assert "make model-corpus-release" in content
    assert "run_model_corpus.py --require-model-backed" in content


def test_readme_does_not_describe_active_high_quality_qwen_runtime() -> None:
    content = README.read_text(encoding="utf-8")

    assert "Qwen Smart/High Quality" not in content
    assert "model-qwen-semantic" in content


def test_semantic_plan_does_not_advertise_deferred_hq_rescue_controls() -> None:
    content = SEMANTIC_PLAN.read_text(encoding="utf-8")

    forbidden_runtime_controls = (
        "/semantic-annotations/high-quality",
        "/semantic-annotations/allow-8b-rescue",
        "RescuePolicy may enqueue",
        "Qwen smart/HQ gateways",
    )
    for phrase in forbidden_runtime_controls:
        assert phrase not in content


def test_event_contract_notes_describe_smart_parse_only() -> None:
    content = EVENT_CONTRACT_NOTES.read_text(encoding="utf-8")

    assert "Smart/High Quality" not in content
    assert "Smart Parse semantic planning" in content


def test_phase85_plan_uses_current_live_model_commands() -> None:
    content = PHASE85_PLAN.read_text(encoding="utf-8")

    assert "docker compose --profile models-live up -d model-qwen model-granite" not in content
    assert "Add explicit `--high-quality`, `--allow-8b-rescue`" not in content
    assert "Run optional HQ/rescue gates separately from the standard corpus gate" not in content
    assert "model-qwen-semantic model-granite model-embed" in content


def test_phase9_plan_does_not_reintroduce_removed_model_qwen_service() -> None:
    content = PHASE9_PLAN.read_text(encoding="utf-8")

    assert "`model-qwen`" not in content
    assert not re.search(r"\bmodel-qwen\b(?!-semantic)", content)
    assert "analysis model profile" in content
    assert "model-qwen-semantic is not an analysis service" in content


def test_root_plan_model_placeholder_section_matches_current_compose() -> None:
    content = ROOT_PLAN.read_text(encoding="utf-8")

    assert not re.search(r"\bmodel-qwen\b(?!-semantic)", content)
    assert "model-granite-placeholder" in content
    assert "model-qwen-semantic" in content


def test_model_corpus_readme_requires_manifest_run_mode() -> None:
    content = MODEL_CORPUS_README.read_text(encoding="utf-8")
    normalized = re.sub(r"\s+", " ", content)

    assert (
        "private `phase8_5_model_manifest.json` must include "
        "`runManifest.model_mode` set to `live` or `required`"
    ) in normalized
