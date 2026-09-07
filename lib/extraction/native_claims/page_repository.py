"""Atomic insert-or-verify page checkpoints and their complete immutable claim rows."""

from typing import Any

from psycopg.types.json import Jsonb

from lib.document_processing.models import content_digest
from lib.extraction.native_claims.authority_repository import fence_set, lock_set
from lib.extraction.native_claims.errors import NativeClaimConflict
from lib.extraction.native_claims.models import (
    NativeClaim,
    NativeClaimBinding,
    NativeClaimConfiguration,
    NativePageRequest,
)
from lib.extraction.native_claims.normalization import normalize_page_claims


def persist_page(cur: Any, binding: NativeClaimBinding, request: NativePageRequest) -> str:
    request = NativePageRequest.model_validate(request.model_dump(mode="json"))
    header, source = lock_set(cur, binding)
    configuration = NativeClaimConfiguration.model_validate(header["configuration_json"])
    claims = normalize_page_claims(binding, configuration, source, request)
    payload = request.model_dump(mode="json")
    digest = page_digest(payload, claims)
    cur.execute(
        "SELECT content_sha256 FROM native_claim_page_checkpoints "
        "WHERE claim_set_id=%s AND page_number=%s",
        (binding.claim_set_id, request.page_number),
    )
    existing = cur.fetchone()
    if existing:
        if existing["content_sha256"] != digest:
            raise NativeClaimConflict("Native claim page already has different content.")
    else:
        if header["state"] != "building":
            raise NativeClaimConflict("Sealed claim sets cannot acquire new page content.")
        page = next(p for p in source.structure.pages if p.page_number == request.page_number)
        cur.execute(
            """INSERT INTO native_claim_page_checkpoints
            (claim_set_id,document_id,parse_generation_id,page_number,page_id,request_json,
             content_sha256,claim_count) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
            (
                binding.claim_set_id,
                binding.processing.document_id,
                binding.processing.parse_generation_id,
                page.page_number,
                page.id,
                Jsonb(payload),
                digest,
                len(claims),
            ),
        )
        for claim in claims:
            _insert_claim(cur, claim)
    fence_set(cur, binding, header)
    return digest


def page_digest(request: dict[str, Any], claims: tuple[NativeClaim, ...]) -> str:
    return content_digest(
        {
            "request": request,
            "claims": [c.model_dump(mode="json") for c in sorted(claims, key=lambda c: c.claim_id)],
        }
    )


def _insert_claim(cur: Any, claim: NativeClaim) -> None:
    payload = claim.model_dump(mode="json")
    cur.execute(
        """INSERT INTO extraction_claims
        (extraction_id,document_id,claim_id,method,source_engine,canonical_key,raw_value,
         typed_value_json,value_type,group_id,anchor_json,evidence_json,metadata_json,
         origin_kind,native_claim_set_id,native_page_number,native_payload_json,native_content_sha256)
        VALUES (NULL,%s,%s,'structure_normalization:v1','qwen3_8_27b',%s,%s,%s,%s,%s,%s,%s,%s,
                'native_structure',%s,%s,%s,%s)""",
        (
            claim.document_id,
            claim.claim_id,
            claim.canonical_key,
            claim.raw_value,
            Jsonb(payload["typed_value"]),
            claim.value_type,
            claim.group_id,
            Jsonb(payload["anchor"]),
            Jsonb([payload["anchor"]]),
            Jsonb({"schema_version": "native_claim.v2", "requires_review": True}),
            claim.claim_set_id,
            claim.anchor.page_number,
            Jsonb(payload),
            claim.fingerprint,
        ),
    )
