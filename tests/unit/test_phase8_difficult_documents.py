from __future__ import annotations

import hashlib
from uuid import uuid4

from lib.config import get_settings
from lib.contracts import SearchRequest
from lib.documents.quality import (
    PageQualityInput,
    classify_page_quality,
    summarize_document_quality,
)
from lib.extraction.gateway import DoclingHeuristicGateway
from lib.extraction.models import ExtractionSourceDocument, ParsedElementText, ParsedPageText
from lib.model_runtime.profiles import VISUAL_EMBED_PROFILE
from lib.search import jobs as search_jobs
from lib.search.benchmark import BenchmarkCase, evaluate_ranked_results, summarize_results
from lib.search.embedding_gateway import (
    DeterministicVisualEmbeddingGateway,
    VisualEmbeddingInput,
    default_visual_embedding_profile,
)
from lib.search.hybrid import RankedCandidate, reciprocal_rank_fusion
from lib.search.query import parse_search_request
from workers.embeddings.worker import EmbeddingWorkerError, _modalities_for_job


def test_page_quality_classifier_flags_handwriting_low_text_and_degraded_layout() -> None:
    page = PageQualityInput(
        page_number=1,
        text="total due",
        has_text_layer=False,
        ocr_confidence=0.41,
        metadata={
            "hasHandwriting": True,
            "visualQuality": "degraded",
            "parseWarnings": ["image-only fallback"],
        },
        table_count=3,
        figure_count=2,
    )

    signals = classify_page_quality(page)

    assert signals.review_required is True
    assert signals.visual_embedding_eligible is True
    assert signals.qwen_route_eligible is True
    assert set(signals.reasons) >= {
        "handwriting",
        "missing_text_layer",
        "low_text_density",
        "low_ocr_confidence",
        "degraded_scan",
        "complex_layout",
    }


def test_page_quality_classifier_leaves_text_native_pages_on_text_path() -> None:
    page = PageQualityInput(
        page_number=1,
        text="This is a dense digital invoice with invoice number ABC-123 and total 42.00.",
        has_text_layer=True,
        ocr_confidence=None,
        metadata={},
    )

    signals = classify_page_quality(page)

    assert signals.review_required is False
    assert signals.visual_embedding_eligible is False
    assert signals.qwen_route_eligible is False
    assert signals.reasons == ("digital_text_page",)


def test_document_quality_summary_rolls_up_page_signals() -> None:
    summary = summarize_document_quality(
        [
            PageQualityInput(
                page_number=1,
                text="",
                has_text_layer=False,
                ocr_confidence=None,
                metadata={"hasHandwriting": True},
            ),
            PageQualityInput(
                page_number=2,
                text="Clean digital text with enough content to avoid the low text threshold.",
                has_text_layer=True,
                ocr_confidence=None,
                metadata={},
            ),
        ]
    )

    assert summary.review_required is True
    assert summary.has_handwriting is True
    assert summary.visual_embedding_eligible is True
    assert summary.qwen_route_eligible is True
    assert summary.difficult_page_numbers == (1,)


def test_search_contract_supports_explicit_visual_retrieval_policy() -> None:
    request = SearchRequest.model_validate(
        {"query": "handwritten low-text warranty form", "mode": "visual", "includeVisual": True}
    )

    parsed = parse_search_request(request)

    assert parsed.mode == "visual"
    assert parsed.include_visual is True


def test_visual_embedding_profile_uses_phase8_dimension_and_modality() -> None:
    profile = default_visual_embedding_profile(2048)

    assert profile.name == "structura-fixture-visual-byte-embedding"
    assert profile.modality == "visual"
    assert profile.dimensions == 2048


def test_visual_embedding_gateway_depends_on_image_bytes_not_metadata_only() -> None:
    profile = default_visual_embedding_profile(32)
    gateway = DeterministicVisualEmbeddingGateway(profile)
    first_bytes = b"<svg><text>first visual content</text></svg>"
    second_bytes = b"<svg><text>different visual content</text></svg>"

    first = gateway.embed_assets(
        [
            VisualEmbeddingInput(
                descriptor_text="handwritten degraded page",
                image_bytes=first_bytes,
                mime_type="image/svg+xml",
                content_sha256=hashlib.sha256(first_bytes).hexdigest(),
            )
        ]
    )[0]
    second = gateway.embed_assets(
        [
            VisualEmbeddingInput(
                descriptor_text="handwritten degraded page",
                image_bytes=second_bytes,
                mime_type="image/svg+xml",
                content_sha256=hashlib.sha256(second_bytes).hexdigest(),
            )
        ]
    )[0]

    assert first.values != second.values
    assert first.profile.name == "structura-fixture-visual-byte-embedding"


def test_fixture_qwen_route_does_not_claim_qwen_or_granite_provenance() -> None:
    source = _extraction_source(
        "Invoice Number INV-88\nSeller: Ink Clinic\nTotal: $88.00\nBalance due: $88.00\n"
    )
    result = DoclingHeuristicGateway().extract(
        source,
        schema_name="invoice",
        route_profile="qwen_primary_review_required",
    )

    assert result.route.source_engine == "docling"
    assert "qwen" not in result.route.source_engine
    assert "granite" not in result.route.source_engine
    assert result.raw_output_json["qwen_model_invoked"] is False
    assert result.normalized_json["metadata"]["phase8Route"] == "qwen_primary_review_required"


def test_visual_embedding_jobs_reject_unknown_modalities() -> None:
    assert _modalities_for_job({"modalities": ["visual"]}) == ("visual",)

    try:
        _modalities_for_job({"modalities": ["visual", "untrusted"]})
    except EmbeddingWorkerError as exc:
        assert "untrusted" in str(exc)
    else:
        raise AssertionError("Expected unsupported modality to fail.")


def test_visual_embedding_job_uses_live_visual_profile_when_model_mode_is_live(
    monkeypatch,
) -> None:
    monkeypatch.setenv("STRUCTURA_MODEL_MODE", "live")
    get_settings.cache_clear()
    captured: dict[str, object] = {}

    def capture_job(_cur: object, **kwargs: object) -> None:
        captured.update(kwargs)

    monkeypatch.setattr(search_jobs, "create_job_with_cursor", capture_job)
    try:
        search_jobs.enqueue_visual_embed_document_job(
            object(),
            document_id=uuid4(),
            household_id=uuid4(),
        )
    finally:
        get_settings.cache_clear()

    payload = captured["payload"]
    assert isinstance(payload, dict)
    assert payload["model_profile"] == VISUAL_EMBED_PROFILE


def test_reciprocal_rank_fusion_can_blend_visual_candidates() -> None:
    fused = reciprocal_rank_fusion(
        lexical=[
            RankedCandidate("doc-text", "chunk-1", 1, "lexical", 19.0),
        ],
        semantic=[
            RankedCandidate("doc-visual", None, 4, "semantic", 0.6),
        ],
        visual=[
            RankedCandidate("doc-visual", None, 1, "visual", 0.92),
        ],
        limit=2,
    )

    assert fused[0].document_id == "doc-visual"
    assert fused[0].source_ranks["visual"] == 1
    assert "visual rank 1" in fused[0].explanation


def test_phase8_benchmark_cases_cover_difficult_docs_without_hiding_text_regression() -> None:
    cases = [
        BenchmarkCase(
            name="phase8-handwriting-visual-retrieval",
            query={
                "query": "handwritten degraded warranty form",
                "mode": "visual",
                "includeVisual": True,
            },
            expected_document_ids=("doc-handwritten",),
            k=3,
        ),
        BenchmarkCase(
            name="phase8-normal-text-hybrid-regression",
            query={
                "query": "invoice total balance due",
                "mode": "hybrid",
                "includeVisual": False,
            },
            expected_document_ids=("doc-invoice",),
            k=3,
        ),
    ]

    visual_result = evaluate_ranked_results(
        cases[0], ["doc-hidden-by-acl", "doc-handwritten", "doc-other"]
    )
    text_result = evaluate_ranked_results(cases[1], ["doc-invoice", "doc-handwritten"])
    summary = summarize_results([visual_result, text_result])

    assert visual_result.reciprocal_rank == 0.5
    assert text_result.reciprocal_rank == 1.0
    assert summary["hitRateAtK"] == 1.0
    assert summary["meanReciprocalRank"] == 0.75


def _extraction_source(text: str) -> ExtractionSourceDocument:
    page_id = uuid4()
    return ExtractionSourceDocument(
        document_id=uuid4(),
        household_id=uuid4(),
        title="Fixture",
        original_filename="fixture.pdf",
        mime_type="application/pdf",
        family="generic",
        subtype=None,
        sensitivity="normal",
        document_date=None,
        counterparty_display=None,
        primary_folder_id=None,
        metadata={"phase3": {"parseStatus": "succeeded"}},
        pages=[ParsedPageText(page_id=page_id, page_number=1, text=text)],
        elements=[
            ParsedElementText(
                element_id=uuid4(),
                page_number=1,
                ordinal=1,
                text=text,
                bbox={"l": 10, "t": 20, "r": 400, "b": 120},
            )
        ],
        tables=[],
    )
