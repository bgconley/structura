from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

from psycopg.types.json import Jsonb

from lib.extraction.claims import Claim, ClaimAnchor, ClaimSourceEngine, ClaimValueType
from lib.extraction.models import ExtractionRunScope


def persist_extraction_claims(
    cur: Any,
    *,
    extraction_id: UUID,
    claims: Sequence[Claim],
    run_scope: ExtractionRunScope,
) -> None:
    if not claims:
        return
    cur.executemany(
        """
        INSERT INTO extraction_claims
          (
            extraction_id, document_id, claim_id, semantic_annotation_id,
            source_semantic_region_id, semantic_type, granite_task, method,
            region_envelope_version, source_engine, canonical_key, raw_value,
            typed_value_json, value_type, confidence, group_id, anchor_json,
            evidence_json, metadata_json
          )
        VALUES (
          %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
          %s::jsonb, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb
        )
        ON CONFLICT (extraction_id, claim_id) DO UPDATE
        SET semantic_annotation_id = EXCLUDED.semantic_annotation_id,
            source_semantic_region_id = EXCLUDED.source_semantic_region_id,
            semantic_type = EXCLUDED.semantic_type,
            granite_task = EXCLUDED.granite_task,
            method = EXCLUDED.method,
            region_envelope_version = EXCLUDED.region_envelope_version,
            source_engine = EXCLUDED.source_engine,
            canonical_key = EXCLUDED.canonical_key,
            raw_value = EXCLUDED.raw_value,
            typed_value_json = EXCLUDED.typed_value_json,
            value_type = EXCLUDED.value_type,
            confidence = EXCLUDED.confidence,
            group_id = EXCLUDED.group_id,
            anchor_json = EXCLUDED.anchor_json,
            evidence_json = EXCLUDED.evidence_json,
            metadata_json = EXCLUDED.metadata_json,
            updated_at = now()
        """,
        [
            _claim_insert_params(
                extraction_id=extraction_id,
                claim=claim,
                run_scope=run_scope,
            )
            for claim in claims
        ],
    )


def list_claims_for_extraction(cur: Any, extraction_id: UUID) -> list[Claim]:
    cur.execute(
        """
        SELECT
          extraction_id, claim_id, document_id, source_engine,
          semantic_annotation_id, source_semantic_region_id, semantic_type,
          granite_task, method, region_envelope_version, canonical_key,
          raw_value, typed_value_json, value_type, confidence, group_id,
          anchor_json, evidence_json, metadata_json
        FROM extraction_claims
        WHERE extraction_id = %s
        ORDER BY canonical_key, group_id NULLS FIRST, claim_id
        """,
        (extraction_id,),
    )
    return claims_from_rows(cur.fetchall())


def list_current_document_claims(
    cur: Any,
    document_id: UUID,
    *,
    schema_name: str | None = None,
    extraction_scope: str | None = None,
) -> list[Claim]:
    cur.execute(
        """
        SELECT
          ec.extraction_id, ec.claim_id, ec.document_id, ec.source_engine,
          ec.semantic_annotation_id, ec.source_semantic_region_id, ec.semantic_type,
          ec.granite_task, ec.method, ec.region_envelope_version, ec.canonical_key,
          ec.raw_value, ec.typed_value_json, ec.value_type, ec.confidence, ec.group_id,
          ec.anchor_json, ec.evidence_json, ec.metadata_json
        FROM extraction_claims ec
        JOIN document_extractions de ON de.id = ec.extraction_id
        WHERE de.document_id = %s
          AND de.is_current
          AND (%s IS NULL OR de.schema_name = %s)
          AND (%s IS NULL OR de.extraction_scope = %s)
        ORDER BY de.created_at DESC, ec.canonical_key, ec.group_id NULLS FIRST, ec.claim_id
        """,
        (document_id, schema_name, schema_name, extraction_scope, extraction_scope),
    )
    return claims_from_rows(cur.fetchall())


def claims_from_rows(rows: Iterable[Mapping[str, Any]]) -> list[Claim]:
    return [claim_from_row(row) for row in rows]


def claim_from_row(row: Mapping[str, Any]) -> Claim:
    return Claim(
        claim_id=str(row["claim_id"]),
        document_id=str(row["document_id"]),
        source_engine=cast(ClaimSourceEngine, str(row["source_engine"])),
        anchor=_anchor_from_json(row.get("anchor_json")),
        canonical_key=str(row["canonical_key"]),
        raw_value=str(row.get("raw_value") or ""),
        typed_value=row.get("typed_value_json"),
        value_type=cast(ClaimValueType, str(row["value_type"])),
        confidence=_confidence(row.get("confidence")),
        method=str(row["method"]),
        group_id=_optional_str(row.get("group_id")),
        evidence=tuple(_dict_items(row.get("evidence_json"))),
    )


def _claim_insert_params(
    *,
    extraction_id: UUID,
    claim: Claim,
    run_scope: ExtractionRunScope,
) -> tuple[object, ...]:
    return (
        extraction_id,
        UUID(claim.document_id),
        claim.claim_id,
        run_scope.semantic_annotation_id,
        run_scope.source_semantic_region_id,
        run_scope.semantic_type,
        run_scope.granite_task,
        claim.method,
        run_scope.region_envelope_version,
        claim.source_engine,
        claim.canonical_key,
        claim.raw_value,
        Jsonb(claim.typed_value),
        claim.value_type,
        claim.confidence,
        claim.group_id,
        Jsonb(claim.anchor.as_json()),
        Jsonb(list(claim.evidence)),
        Jsonb({}),
    )


def _anchor_from_json(value: Any) -> ClaimAnchor:
    payload = value if isinstance(value, Mapping) else {}
    return ClaimAnchor(
        page_number=_optional_int(payload.get("page_number")),
        page_id=_optional_str(payload.get("page_id")),
        docling_element_ids=tuple(
            str(item) for item in _list_items(payload.get("docling_element_ids"))
        ),
        table_id=_optional_str(payload.get("table_id")),
        row_index=_optional_int(payload.get("row_index")),
        bbox=_bbox(payload.get("bbox")),
        text_span=dict(payload["text_span"])
        if isinstance(payload.get("text_span"), Mapping)
        else None,
        semantic_region_id=_optional_str(payload.get("semantic_region_id")),
    )


def _dict_items(value: Any) -> list[dict[str, Any]]:
    return [dict(item) for item in _list_items(value) if isinstance(item, Mapping)]


def _list_items(value: Any) -> list[Any]:
    if isinstance(value, list | tuple):
        return list(value)
    return []


def _bbox(value: Any) -> tuple[float, ...] | None:
    if not isinstance(value, list | tuple):
        return None
    try:
        bbox = tuple(float(item) for item in value)
    except (TypeError, ValueError):
        return None
    return bbox or None


def _optional_str(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _confidence(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
