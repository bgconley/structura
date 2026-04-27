from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RankedCandidate:
    document_id: str
    chunk_id: str | None
    rank: int
    source: str
    score: float


@dataclass(frozen=True)
class FusedCandidate:
    document_id: str
    chunk_id: str | None
    score: float
    source_ranks: dict[str, int] = field(default_factory=dict)
    explanation: str = ""


def reciprocal_rank_fusion(
    *,
    lexical: list[RankedCandidate],
    semantic: list[RankedCandidate],
    visual: list[RankedCandidate] | None = None,
    limit: int,
    k: int = 60,
    semantic_weight: float = 1.2,
    lexical_weight: float = 1.0,
    visual_weight: float = 1.4,
) -> list[FusedCandidate]:
    scores: dict[str, float] = {}
    ranks: dict[str, dict[str, int]] = {}
    chunks: dict[str, str | None] = {}
    _accumulate(
        candidates=lexical,
        scores=scores,
        ranks=ranks,
        chunks=chunks,
        k=k,
        weight=lexical_weight,
    )
    _accumulate(
        candidates=semantic,
        scores=scores,
        ranks=ranks,
        chunks=chunks,
        k=k,
        weight=semantic_weight,
    )
    _accumulate(
        candidates=visual or [],
        scores=scores,
        ranks=ranks,
        chunks=chunks,
        k=k,
        weight=visual_weight,
    )
    ordered = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    return [
        FusedCandidate(
            document_id=document_id,
            chunk_id=chunks.get(document_id),
            score=score,
            source_ranks=ranks[document_id],
            explanation=_explain(ranks[document_id]),
        )
        for document_id, score in ordered[:limit]
    ]


def _accumulate(
    *,
    candidates: list[RankedCandidate],
    scores: dict[str, float],
    ranks: dict[str, dict[str, int]],
    chunks: dict[str, str | None],
    k: int,
    weight: float,
) -> None:
    for candidate in candidates:
        scores[candidate.document_id] = scores.get(candidate.document_id, 0.0) + (
            weight / (k + candidate.rank)
        )
        source_ranks = ranks.setdefault(candidate.document_id, {})
        source_ranks[candidate.source] = min(
            candidate.rank,
            source_ranks.get(candidate.source, candidate.rank),
        )
        if candidate.document_id not in chunks:
            chunks[candidate.document_id] = candidate.chunk_id


def _explain(source_ranks: dict[str, int]) -> str:
    ordered_sources = sorted(source_ranks.items())
    parts = [f"{source} rank {rank}" for source, rank in ordered_sources]
    return "matched by " + " and ".join(parts)
