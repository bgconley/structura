from __future__ import annotations

from uuid import uuid4

from lib.extraction.models import ExtractionSourceDocument, ParsedPageText
from scripts.gpu import run_phase8_5_semantic_canary as semantic_canary


def test_semantic_canary_parser_supports_expected_modes_and_skip_granite() -> None:
    for mode in semantic_canary.CANARY_MODES:
        args = semantic_canary.parse_args(
            [
                "--mode",
                mode,
                "--document-id",
                str(uuid4()),
                "--skip-granite",
                "--json-output",
                "/tmp/semantic-canary.json",
            ]
        )

        assert args.mode == mode
        assert args.skip_granite is True
        assert str(args.json_output) == "/tmp/semantic-canary.json"


def test_semantic_canary_parser_supports_expectations_json() -> None:
    args = semantic_canary.parse_args(
        [
            "--document-id",
            str(uuid4()),
            "--expectations-json",
            "tests/fixtures/semantic_annotations/semantic_canary_expectations.example.json",
        ]
    )

    assert str(args.expectations_json).endswith("semantic_canary_expectations.example.json")


def test_semantic_canary_scores_document_family_and_regions() -> None:
    report = {
        "document_id": str(uuid4()),
        "filename": "vehicle-service-class.pdf",
        "title": "vehicle service representative",
        "docling": {
            "page_count": 3,
            "suggested_family_hints": [],
            "lexical_anchors": [],
            "table_summaries": [{"table_signal": "weak"}],
        },
        "semantic": {
            "document_type": "service_record",
            "document_type_candidates": [
                {"document_type": "service_record", "confidence": 0.84},
                {"document_type": "receipt", "confidence": 0.42},
            ],
            "page_document_hints": [
                {
                    "page_number": 1,
                    "page_role": "line_items",
                    "extraction_usefulness": "high",
                    "docling_table_signal": "weak",
                },
                {
                    "page_number": 2,
                    "page_role": "line_items",
                    "extraction_usefulness": "high",
                    "docling_table_signal": "weak",
                },
                {
                    "page_number": 3,
                    "page_role": "payment_summary",
                    "extraction_usefulness": "medium",
                },
            ],
            "regions": [
                {
                    "semantic_type": "service_record_line_item_table",
                    "target_schema": "receipt",
                    "continuation_group": "service_lines",
                    "requires_full_page_image": True,
                    "source_signal": "mixed",
                    "extraction_scope": "page",
                },
                {
                    "semantic_type": "receipt_payment_summary",
                    "target_schema": "receipt",
                    "source_signal": "text",
                    "extraction_scope": "element",
                },
                {
                    "semantic_type": "vehicle_or_asset_block",
                    "target_schema": "document_observation",
                    "source_signal": "mixed",
                    "extraction_scope": "page",
                },
            ],
        },
    }
    expectations = {
        "documents": {
            "vehicle-service-class.pdf": {
                "expected_document_types": ["service_record", "receipt"],
                "forbidden_document_types": ["medical_eob"],
                "required_document_type_candidates": ["service_record"],
                "required_page_roles": ["line_items", "payment_summary"],
                "required_extraction_usefulness": ["high"],
                "required_semantic_types": ["service_record_line_item_table"],
                "required_target_schemas": ["receipt"],
                "required_continuation_groups": ["service_lines"],
                "required_docling_table_signals": ["weak"],
                "required_full_page_image_semantic_types": ["service_record_line_item_table"],
                "required_source_signals": ["mixed"],
                "required_extraction_scopes": ["page"],
                "required_region_attributes": [
                    {
                        "semantic_type": "service_record_line_item_table",
                        "field": "source_signal",
                        "value": "mixed",
                    }
                ],
                "min_region_count": 3,
                "require_page_coverage": True,
            }
        }
    }

    scorecard = semantic_canary._score_documents([report], expectations)

    assert scorecard["passed"] is True
    assert scorecard["documents"][0]["passed"] is True


def test_semantic_canary_scores_missing_qwen_inventory_behavior() -> None:
    report = {
        "document_id": str(uuid4()),
        "filename": "retail-order-class.pdf",
        "title": "retail order representative",
        "docling": {
            "page_count": 2,
            "suggested_family_hints": ["retail_order"],
            "lexical_anchors": ["order"],
            "table_summaries": [],
        },
        "semantic": {
            "document_type": "retail_order",
            "document_type_candidates": [],
            "page_document_hints": [{"page_number": 1}, {"page_number": 2}],
            "regions": [
                {
                    "semantic_type": "retail_order_line_item_table",
                    "target_schema": "receipt",
                }
            ],
        },
    }
    expectations = {
        "documents": {
            "retail-order-class.pdf": {
                "expected_document_types": ["retail_order"],
                "required_document_type_candidates": ["retail_order"],
                "required_page_roles": ["line_items"],
                "required_source_signals": ["mixed", "table"],
                "required_extraction_scopes": ["table", "page"],
                "require_page_coverage": True,
            }
        }
    }

    scorecard = semantic_canary._score_documents([report], expectations)

    assert scorecard["passed"] is False
    checks = scorecard["documents"][0]["checks"]
    assert any(
        check["name"] == "required_document_type_candidates" and not check["passed"]
        for check in checks
    )
    assert any(check["name"] == "required_page_roles" and not check["passed"] for check in checks)
    assert any(
        check["name"] == "required_source_signals" and not check["passed"] for check in checks
    )
    assert any(
        check["name"] == "required_extraction_scopes" and not check["passed"] for check in checks
    )


def test_semantic_canary_scores_forbidden_semantic_intent_normalization() -> None:
    report = {
        "document_id": str(uuid4()),
        "filename": "vehicle-service-class.pdf",
        "title": "vehicle service representative",
        "docling": {
            "page_count": 1,
            "suggested_family_hints": ["service_record"],
            "lexical_anchors": ["service"],
            "table_summaries": [],
        },
        "semantic": {
            "document_type": "service_record",
            "page_document_hints": [{"page_number": 1, "page_role": "line_items"}],
            "regions": [
                {
                    "semantic_type": "service_record_line_item_table",
                    "target_schema": "receipt",
                    "source_signal": "mixed",
                    "extraction_scope": "page",
                }
            ],
            "confidence": {
                "normalization": {"service_record_line_item_continuation_group_repaired": 1}
            },
        },
    }
    expectations = {
        "documents": {
            "vehicle-service-class.pdf": {
                "expected_document_types": ["service_record"],
                "forbidden_normalization_keys": [
                    "service_record_line_item_continuation_group_repaired",
                    "service_record_line_item_full_page_image_repaired",
                ],
                "require_page_coverage": True,
            }
        }
    }

    scorecard = semantic_canary._score_documents([report], expectations)

    assert scorecard["passed"] is False
    checks = scorecard["documents"][0]["checks"]
    assert any(
        check["name"] == "forbidden_normalization_keys" and not check["passed"] for check in checks
    )


def test_semantic_canary_scores_forbidden_masquerade_failure() -> None:
    report = {
        "document_id": str(uuid4()),
        "filename": "UWM Final Escrow Statement 4-29-24.pdf",
        "title": "UWM escrow",
        "docling": {
            "page_count": 1,
            "suggested_family_hints": ["mortgage_escrow_statement"],
            "lexical_anchors": ["escrow"],
        },
        "semantic": {
            "document_type": "medical_eob",
            "page_document_hints": [{"page_number": 1}],
            "regions": [],
        },
    }
    expectations = {
        "documents": {
            "UWM Final Escrow Statement 4-29-24.pdf": {
                "expected_document_types": ["mortgage_escrow_statement", "generic_form"],
                "forbidden_document_types": ["medical_eob"],
                "required_semantic_types": ["escrow_summary"],
                "require_page_coverage": True,
            }
        }
    }

    scorecard = semantic_canary._score_documents([report], expectations)

    assert scorecard["passed"] is False
    checks = scorecard["documents"][0]["checks"]
    assert any(
        check["name"] == "forbidden_document_type" and not check["passed"] for check in checks
    )
    assert any(
        check["name"] == "required_semantic_types" and not check["passed"] for check in checks
    )


def test_semantic_canary_estimates_adaptive_fan_in_with_fallback() -> None:
    sequence = semantic_canary._image_fan_in_sequence(
        page_count=3,
        confidence={"fallback_reason": "multi_image_page_coverage"},
    )

    assert sequence == [3, 1, 1, 1]


def test_semantic_canary_reports_qwen_visual_token_budget() -> None:
    source = ExtractionSourceDocument(
        document_id=uuid4(),
        household_id=uuid4(),
        title="BH Photo Order",
        original_filename="BH Photo desktop tripod order.pdf",
        mime_type="application/pdf",
        family="generic",
        subtype=None,
        sensitivity="normal",
        document_date=None,
        counterparty_display=None,
        primary_folder_id=None,
        metadata={},
        pages=[
            ParsedPageText(
                page_id=uuid4(),
                page_number=1,
                text="B&H Photo order confirmation with tripod line items.",
                image_bytes=_png_bytes(width=2480, height=3508),
                image_mime_type="image/png",
                image_sha256="page-1",
            ),
            ParsedPageText(
                page_id=uuid4(),
                page_number=2,
                text="Payment summary and shipping details.",
                image_bytes=_png_bytes(width=2480, height=3508),
                image_mime_type="image/png",
                image_sha256="page-2",
            ),
        ],
        elements=[],
        tables=[],
    )

    report = semantic_canary._token_budget_report(
        source,
        selected_fan_in_sequence=[2],
    )

    assert report["spatial_compression"] == 32
    assert report["visual_token_min_per_image"] == 256
    assert report["visual_token_max_per_image"] == 2560
    assert report["mm_processor_kwargs"] == {
        "size": {"shortest_edge": 262144, "longest_edge": 2621440}
    }
    assert report["requested_output_tokens"] == 6144
    assert report["selected_fan_in_sequence"] == [2]
    assert report["docling_context_text_token_estimate"] > 0
    assert report["schema_token_estimate"] > 0
    assert report["prompt_token_estimate"] > report["docling_context_text_token_estimate"]
    assert report["prompt_context_includes_legacy_pages_alias"] is False
    assert report["prompt_context_includes_page_image_hashes"] is False
    assert report["prompt_context_includes_element_bboxes"] is False

    first_page = report["page_images"][0]
    assert first_page["width_px"] == 2480
    assert first_page["height_px"] == 3508
    assert first_page["raw_visual_token_estimate"] > 2560
    assert first_page["qwen_grid_estimate"]["visual_tokens"] <= 2560

    first_window = report["request_windows"][0]
    assert first_window["page_numbers"] == [1, 2]
    assert first_window["image_count"] == 2
    assert first_window["visual_token_estimate"] <= 5120
    assert first_window["conservative_total_token_estimate"] > 6144


def _png_bytes(*, width: int, height: int) -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR"
        + width.to_bytes(4, "big")
        + height.to_bytes(4, "big")
        + b"\x08\x02\x00\x00\x00"
        + b"\x00\x00\x00\x00"
    )
