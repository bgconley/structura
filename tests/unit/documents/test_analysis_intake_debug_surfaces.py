from __future__ import annotations

import json

from lib.documents.analysis_intake import build_phase9_document_intake


def test_phase9_intake_excludes_debug_envelopes_from_truth_context() -> None:
    intake = build_phase9_document_intake(
        {
            "id": "doc-1",
            "fields": [],
            "lineItems": [],
            "semanticRegionExtractions": [
                {
                    "id": "extraction-1",
                    "promptVersion": "phase8_5-granite-structured-v1",
                    "normalized": {
                        "invoice": {
                            "total_amount": {
                                "amount": 42.5,
                                "source": "debug-only-normalized-payload",
                            }
                        }
                    },
                    "normalization": {
                        "regionEnvelope": {
                            "facts": [{"field_path": "invoice.total_amount"}],
                            "repairs": ["wrapped_data_invoice_line_items"],
                        }
                    },
                    "metadata": {
                        "visualInputPlan": {"route": "full_page"},
                        "adapterTrace": {"finish_reason": "stop"},
                        "rawModelOutput": {"text": "debug raw model output"},
                    },
                }
            ],
        }
    )

    truth_json = json.dumps(intake["truth"], sort_keys=True)
    assert "debug-only-normalized-payload" not in truth_json
    assert "regionEnvelope" not in truth_json
    assert "raw model output" not in truth_json
    assert intake["debug"]["excludedFromTruth"] is True
    assert set(intake["debug"]["availableSurfaces"]) >= {
        "prompt_versions",
        "visual_plan_internals",
        "region_envelope",
        "normalization_repairs",
        "adapter_traces",
        "raw_model_output",
    }


def test_phase9_intake_detects_raw_output_debug_payload_aliases() -> None:
    intake = build_phase9_document_intake(
        {
            "id": "doc-debug-aliases",
            "semanticRegionExtractions": [
                {
                    "id": "extraction-raw-camel",
                    "rawOutputJson": {
                        "modelOutputPayload": {
                            "line_items": [
                                {
                                    "description": "Debug-only line",
                                    "amount": "42.50",
                                }
                            ]
                        },
                        "visualInputPlan": {"scope": "full_page"},
                    },
                },
                {
                    "id": "extraction-raw-snake",
                    "raw_output_json": {
                        "raw_model_output": {"text": "debug raw transcript"},
                        "model_output_payload": {"invoice_number": "debug-only"},
                    },
                },
            ],
        }
    )

    truth_json = json.dumps(intake["truth"], sort_keys=True)
    assert "Debug-only line" not in truth_json
    assert "debug-only" not in truth_json
    assert set(intake["debug"]["availableSurfaces"]) >= {
        "raw_model_output",
        "model_output_payloads",
        "visual_plan_internals",
    }


def test_phase9_intake_includes_document_extraction_debug_refs() -> None:
    intake = build_phase9_document_intake(
        {
            "id": "doc-document-extraction-debug",
            "extractions": [
                {
                    "id": "extraction-document-1",
                    "schemaName": "invoice",
                    "promptVersion": "phase8_5-granite-structured-v1",
                    "normalizationJson": {
                        "regionEnvelope": {"observations": [{"field_name": "debug_only"}]},
                        "repairs": ["wrapped_debug_payload"],
                    },
                    "rawOutputJson": {
                        "modelOutputPayload": {"invoice_number": "debug-only-invoice"},
                        "adapterTrace": {"finish_reason": "stop"},
                        "visualInputPlan": {"scope": "full_page"},
                    },
                }
            ],
        }
    )

    truth_json = json.dumps(intake["truth"], sort_keys=True)
    assert "debug-only-invoice" not in truth_json
    assert intake["debug"]["surfaceRefs"] == [
        {
            "extractionId": "extraction-document-1",
            "schemaName": "invoice",
        }
    ]
    assert set(intake["debug"]["availableSurfaces"]) >= {
        "prompt_versions",
        "region_envelope",
        "normalization_repairs",
        "adapter_traces",
        "model_output_payloads",
        "visual_plan_internals",
    }
