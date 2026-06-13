from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_compare_gate():
    script_path = (
        Path(__file__).resolve().parents[3] / "scripts" / "gpu" / "compare_text_lane_gate.py"
    )
    spec = importlib.util.spec_from_file_location("compare_text_lane_gate", script_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_compare_text_lane_gate_prefers_release_document_outcomes() -> None:
    compare_gate = _load_compare_gate()
    report = {
        "documentOutcomes": [
            {
                "documentId": "doc-1",
                "filename": "holdout.pdf",
                "releaseOutcome": "needs_human_review",
            }
        ],
        "documents": [
            {
                "document": {
                    "id": "doc-1",
                    "original_filename": "holdout.pdf",
                },
                "extractions": [{"quality_outcome": "pipeline_failed"}],
            }
        ],
    }

    assert compare_gate._doc_stats(report)["holdout.pdf"]["quality_outcomes"] == {
        "needs_human_review": 1
    }
