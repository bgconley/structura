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
    assert report["requested_output_tokens"] == 3840
    assert report["selected_fan_in_sequence"] == [2]
    assert report["docling_context_text_token_estimate"] > 0
    assert report["schema_token_estimate"] > 0
    assert report["prompt_token_estimate"] > report["docling_context_text_token_estimate"]

    first_page = report["page_images"][0]
    assert first_page["width_px"] == 2480
    assert first_page["height_px"] == 3508
    assert first_page["raw_visual_token_estimate"] > 2560
    assert first_page["qwen_grid_estimate"]["visual_tokens"] <= 2560

    first_window = report["request_windows"][0]
    assert first_window["page_numbers"] == [1, 2]
    assert first_window["image_count"] == 2
    assert first_window["visual_token_estimate"] <= 5120
    assert first_window["conservative_total_token_estimate"] > 3840


def _png_bytes(*, width: int, height: int) -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR"
        + width.to_bytes(4, "big")
        + height.to_bytes(4, "big")
        + b"\x08\x02\x00\x00\x00"
        + b"\x00\x00\x00\x00"
    )
