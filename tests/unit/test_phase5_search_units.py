from __future__ import annotations

import math

import pytest
from pydantic import ValidationError

from lib.contracts import SearchRequest
from lib.search.embedding_gateway import DeterministicEmbeddingGateway, EmbeddingProfile
from lib.search.hybrid import RankedCandidate, reciprocal_rank_fusion
from lib.search.query import SearchValidationError, parse_search_request


def test_search_request_defaults_and_filter_parsing_are_contract_safe() -> None:
    request = SearchRequest.model_validate(
        {
            "query": "  claim ABC123 money owed  ",
            "families": ["medical_eob"],
            "tags": ["medical", "urgent"],
            "reviewedOnly": True,
            "dateFrom": "2025-01-01",
            "dateTo": "2026-12-31",
            "amountMin": 10,
            "amountMax": 500,
            "limit": 12,
            "includeDebug": True,
        }
    )

    parsed = parse_search_request(request)

    assert parsed.query == "claim ABC123 money owed"
    assert parsed.mode == "hybrid"
    assert parsed.limit == 12
    assert parsed.filters.families == ("medical_eob",)
    assert parsed.filters.tags == ("medical", "urgent")
    assert parsed.filters.reviewed_only is True
    assert parsed.filters.date_from.isoformat() == "2025-01-01"
    assert parsed.filters.date_to.isoformat() == "2026-12-31"
    assert parsed.filters.amount_min == 10
    assert parsed.filters.amount_max == 500
    assert parsed.include_debug is True


def test_search_request_rejects_empty_queries_extra_filters_and_invalid_ranges() -> None:
    with pytest.raises(ValidationError):
        SearchRequest.model_validate({"query": "   "})

    with pytest.raises(ValidationError):
        SearchRequest.model_validate({"query": "invoice", "unknownFilter": "silently bad"})

    with pytest.raises(SearchValidationError):
        parse_search_request(
            SearchRequest.model_validate(
                {"query": "invoice", "dateFrom": "2026-01-02", "dateTo": "2026-01-01"}
            )
        )

    with pytest.raises(SearchValidationError):
        parse_search_request(
            SearchRequest.model_validate({"query": "invoice", "amountMin": 250, "amountMax": 10})
        )


def test_deterministic_embedding_adapter_supports_conceptual_local_search() -> None:
    gateway = DeterministicEmbeddingGateway(
        EmbeddingProfile(
            name="structura-fixture-text-embedding",
            version="v1",
            modality="text",
            dimensions=128,
            metric="cosine",
        )
    )

    query = gateway.embed_texts(["claim ABC123 where I may still owe money"])[0]
    close_match = gateway.embed_texts(
        ["Anthem EOB claim ABC123 patient responsibility amount due"]
    )[0]
    unrelated = gateway.embed_texts(["Dishwasher warranty motor replacement coverage"])[0]

    assert len(query.values) == 128
    assert query.profile.dimensions == 128
    assert _cosine(query.values, close_match.values) > _cosine(query.values, unrelated.values)


def test_reciprocal_rank_fusion_keeps_score_scales_separate_and_explained() -> None:
    lexical = [
        RankedCandidate(
            document_id="doc-a",
            chunk_id="chunk-a",
            rank=1,
            source="lexical",
            score=31.0,
        ),
        RankedCandidate(
            document_id="doc-b",
            chunk_id="chunk-b",
            rank=2,
            source="lexical",
            score=17.0,
        ),
    ]
    semantic = [
        RankedCandidate(
            document_id="doc-b",
            chunk_id="chunk-b",
            rank=1,
            source="semantic",
            score=0.82,
        )
    ]

    fused = reciprocal_rank_fusion(lexical=lexical, semantic=semantic, limit=2)

    assert [item.document_id for item in fused] == ["doc-b", "doc-a"]
    assert fused[0].source_ranks == {"lexical": 2, "semantic": 1}
    assert fused[0].explanation == "matched by lexical rank 2 and semantic rank 1"


def _cosine(left: list[float], right: list[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    return dot / (left_norm * right_norm)
