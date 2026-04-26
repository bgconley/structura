from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class BenchmarkCase:
    name: str
    query: dict[str, Any]
    expected_document_ids: tuple[str, ...]
    k: int = 10


@dataclass(frozen=True)
class BenchmarkResult:
    name: str
    hit: bool
    reciprocal_rank: float
    expected_document_ids: tuple[str, ...]
    returned_document_ids: tuple[str, ...]


def evaluate_ranked_results(
    case: BenchmarkCase, returned_document_ids: list[str]
) -> BenchmarkResult:
    top_k = tuple(returned_document_ids[: case.k])
    expected = set(case.expected_document_ids)
    reciprocal_rank = 0.0
    for index, document_id in enumerate(top_k, start=1):
        if document_id in expected:
            reciprocal_rank = 1.0 / index
            break
    return BenchmarkResult(
        name=case.name,
        hit=reciprocal_rank > 0,
        reciprocal_rank=reciprocal_rank,
        expected_document_ids=case.expected_document_ids,
        returned_document_ids=top_k,
    )


def summarize_results(results: list[BenchmarkResult]) -> dict[str, float | int]:
    if not results:
        return {"caseCount": 0, "hitRateAtK": 0.0, "meanReciprocalRank": 0.0}
    return {
        "caseCount": len(results),
        "hitRateAtK": sum(1 for result in results if result.hit) / len(results),
        "meanReciprocalRank": (sum(result.reciprocal_rank for result in results) / len(results)),
    }
