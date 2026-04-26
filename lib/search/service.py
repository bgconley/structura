from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from lib.config import get_settings
from lib.contracts import EvidenceRef, SearchRequest, SearchResponse, SearchResult
from lib.documents.access_policy import DocumentAccessContext
from lib.search import repository
from lib.search.embedding_gateway import (
    DeterministicEmbeddingGateway,
    EmbeddingProfile,
    default_text_embedding_profile,
)
from lib.search.hybrid import RankedCandidate, reciprocal_rank_fusion
from lib.search.query import ParsedSearchQuery, parse_search_request
from lib.search.snippets import plain_search_snippet


@dataclass(frozen=True)
class SearchExecutionTrace:
    mode: str
    lexical_candidates: int
    semantic_candidates: int
    filters_applied: int
    embedding_profile: str
    result_count: int

    def as_debug(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "candidateCounts": {
                "lexical": self.lexical_candidates,
                "semantic": self.semantic_candidates,
            },
            "filtersApplied": self.filters_applied,
            "embeddingProfile": self.embedding_profile,
            "resultCount": self.result_count,
        }


class SearchService:
    def __init__(
        self,
        *,
        embedding_profile: EmbeddingProfile | None = None,
        embedding_gateway: DeterministicEmbeddingGateway | None = None,
    ) -> None:
        self.embedding_profile = embedding_profile or default_text_embedding_profile(
            get_settings().embedding_text_dimensions
        )
        self.embedding_gateway = embedding_gateway or DeterministicEmbeddingGateway(
            self.embedding_profile
        )

    def search(self, request: SearchRequest, *, access: DocumentAccessContext) -> SearchResponse:
        parsed = parse_search_request(request)
        lexical = (
            _lexical_candidates(parsed, access) if parsed.mode in {"lexical", "hybrid"} else []
        )
        semantic = (
            self._semantic_candidates(parsed, access)
            if parsed.mode in {"semantic", "hybrid"}
            else []
        )
        rows = _rank_candidates(parsed=parsed, lexical=lexical, semantic=semantic)
        facets = repository.facet_counts(access=access, filters=parsed.filters)
        trace = SearchExecutionTrace(
            mode=parsed.mode,
            lexical_candidates=len(lexical),
            semantic_candidates=len(semantic),
            filters_applied=parsed.filters.applied_count,
            embedding_profile=f"{self.embedding_profile.name}:{self.embedding_profile.version}",
            result_count=len(rows),
        )
        return SearchResponse.model_validate(
            {
                "items": [_result_payload(index, row) for index, row in enumerate(rows, start=1)],
                "facets": facets,
                "debug": trace.as_debug() if parsed.include_debug else None,
            }
        )

    def _semantic_candidates(
        self,
        parsed: ParsedSearchQuery,
        access: DocumentAccessContext,
    ) -> list[repository.SearchCandidateRow]:
        query_embedding = self.embedding_gateway.embed_texts([parsed.query])[0]
        return repository.semantic_search(
            access=access,
            query_vector=query_embedding.values,
            query=parsed.query,
            profile_name=self.embedding_profile.name,
            profile_version=self.embedding_profile.version,
            dimensions=self.embedding_profile.dimensions,
            filters=parsed.filters,
            limit=parsed.limit,
            oversample=max(parsed.limit * 8, 40),
        )


def _lexical_candidates(
    parsed: ParsedSearchQuery,
    access: DocumentAccessContext,
) -> list[repository.SearchCandidateRow]:
    return repository.lexical_search(
        access=access,
        query=parsed.query,
        filters=parsed.filters,
        limit=max(parsed.limit * 4, 40) if parsed.mode == "hybrid" else parsed.limit,
    )


def _rank_candidates(
    *,
    parsed: ParsedSearchQuery,
    lexical: list[repository.SearchCandidateRow],
    semantic: list[repository.SearchCandidateRow],
) -> list[repository.SearchCandidateRow]:
    if parsed.mode == "lexical":
        return _dedupe_by_document(lexical)[: parsed.limit]
    if parsed.mode == "semantic":
        return _dedupe_by_document(semantic)[: parsed.limit]
    fused = reciprocal_rank_fusion(
        lexical=[
            RankedCandidate(
                document_id=str(row.document_id),
                chunk_id=str(row.matched_chunk_id) if row.matched_chunk_id else None,
                rank=row.rank,
                source="lexical",
                score=row.source_score,
            )
            for row in lexical
        ],
        semantic=[
            RankedCandidate(
                document_id=str(row.document_id),
                chunk_id=str(row.matched_chunk_id) if row.matched_chunk_id else None,
                rank=row.rank,
                source="semantic",
                score=row.source_score,
            )
            for row in semantic
        ],
        limit=parsed.limit,
    )
    by_document = {
        **{str(row.document_id): row for row in reversed(lexical)},
        **{str(row.document_id): row for row in reversed(semantic)},
    }
    ranked: list[repository.SearchCandidateRow] = []
    for fused_candidate in fused:
        row = by_document.get(fused_candidate.document_id)
        if row:
            ranked.append(
                repository.SearchCandidateRow(
                    document_id=row.document_id,
                    title=row.title,
                    family=row.family,
                    rank=len(ranked) + 1,
                    source="hybrid",
                    source_score=fused_candidate.score,
                    snippet=row.snippet,
                    matched_chunk_id=(
                        UUID(fused_candidate.chunk_id)
                        if fused_candidate.chunk_id
                        else row.matched_chunk_id
                    ),
                    page_number=row.page_number,
                    counterparty_display=row.counterparty_display,
                    document_date=row.document_date,
                    amount_total=row.amount_total,
                    folder_paths=row.folder_paths,
                    tags=row.tags,
                )
            )
    return ranked


def _dedupe_by_document(
    rows: list[repository.SearchCandidateRow],
) -> list[repository.SearchCandidateRow]:
    seen: set[UUID] = set()
    deduped: list[repository.SearchCandidateRow] = []
    for row in rows:
        if row.document_id in seen:
            continue
        deduped.append(row)
        seen.add(row.document_id)
    return deduped


def _result_payload(index: int, row: repository.SearchCandidateRow) -> dict[str, object]:
    source_text = plain_search_snippet(row.snippet) or row.title
    evidence = []
    if row.page_number:
        evidence.append(
            EvidenceRef.model_validate(
                {
                    "pageNumber": row.page_number,
                    "sourceEngine": "docling",
                    "sourceText": source_text[:240],
                }
            ).model_dump(by_alias=True)
        )
    return SearchResult.model_validate(
        {
            "documentId": row.document_id,
            "title": row.title,
            "family": row.family,
            "rank": index,
            "score": row.source_score,
            "snippet": source_text,
            "matchedChunkId": row.matched_chunk_id,
            "pageNumber": row.page_number,
            "evidence": evidence,
            "explanation": _result_explanation(row),
            "counterpartyDisplay": row.counterparty_display,
            "documentDate": row.document_date,
            "amountTotal": row.amount_total,
            "folderPaths": row.folder_paths,
            "tags": row.tags,
        }
    ).model_dump(by_alias=True, exclude_none=True)


def _result_explanation(row: repository.SearchCandidateRow) -> str:
    if row.source == "hybrid":
        return "matched by lexical rank and semantic rank fusion"
    return f"matched by {row.source} rank {row.rank}"
