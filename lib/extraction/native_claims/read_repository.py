"""Reconstruct native currency from retained typed rows; never reparse raw output."""

from collections import Counter
from typing import Any

from psycopg.types.json import Jsonb

from lib.auth.request_authority import RequestCredential
from lib.document_processing.models import content_digest
from lib.extraction.native_claims.authority_repository import fence_set, lock_set
from lib.extraction.native_claims.errors import NativeClaimConflict, NativeClaimError
from lib.extraction.native_claims.models import NativeClaim, NativeClaimBinding, NativePageRequest
from lib.extraction.native_claims.page_repository import page_digest
from lib.extraction.native_claims.retained_repository import assert_retained_read, lock_retained_set


def read_inventory(
    cur: Any, binding: NativeClaimBinding, expected_pages: int
) -> tuple[tuple[NativeClaim, ...], dict[str, Any]]:
    cur.execute(
        "SELECT * FROM native_claim_page_checkpoints WHERE claim_set_id=%s ORDER BY page_number",
        (binding.claim_set_id,),
    )
    pages = cur.fetchall()
    if tuple(p["page_number"] for p in pages) != tuple(range(1, expected_pages + 1)):
        raise NativeClaimError("Native claim inventory is incomplete.")
    cur.execute(
        "SELECT * FROM extraction_claims WHERE native_claim_set_id=%s "
        "ORDER BY native_page_number,claim_id",
        (binding.claim_set_id,),
    )
    rows = cur.fetchall()
    claims = []
    for row in rows:
        claim = NativeClaim.model_validate(row["native_payload_json"])
        if (
            claim.fingerprint != row["native_content_sha256"]
            or claim.claim_set_id != binding.claim_set_id
            or claim.document_id != binding.processing.document_id
            or claim.anchor.parse_generation_id != binding.processing.parse_generation_id
            or claim.anchor.page_number != row["native_page_number"]
            or claim.claim_id != row["claim_id"]
        ):
            raise NativeClaimConflict("Persisted native claim identity is inconsistent.")
        claims.append(claim)
    summaries = []
    for page in pages:
        request = NativePageRequest.model_validate(page["request_json"])
        items = tuple(c for c in claims if c.anchor.page_number == page["page_number"])
        if (
            len(items) != page["claim_count"]
            or len(request.claims) != len(items)
            or request.page_number != page["page_number"]
            or page_digest(page["request_json"], items) != page["content_sha256"]
        ):
            raise NativeClaimConflict("Persisted native claim page manifest is inconsistent.")
        summaries.append(
            {
                "page_number": page["page_number"],
                "content_sha256": page["content_sha256"],
                "claim_count": len(items),
                "disposition": request.disposition,
                "reasons": list(request.reasons),
            }
        )
    counts = dict(sorted(Counter(p["disposition"] for p in summaries).items()))
    completion = {
        "schema_version": "native_claim_completion.v1",
        "claim_set_id": str(binding.claim_set_id),
        "source_pages": expected_pages,
        "claim_count": len(claims),
        "page_dispositions": counts,
        "pages": summaries,
        "requires_review": True,
        "source_pixel_support": "not_evaluated",
    }
    return tuple(claims), completion


def seal_set(cur: Any, binding: NativeClaimBinding) -> dict[str, Any]:
    header, _ = lock_set(cur, binding)
    _, completion = read_inventory(cur, binding, header["expected_pages"])
    digest = content_digest(completion)
    if header["state"] == "sealed":
        if header["completion_json"] != completion or header["completion_sha256"] != digest:
            raise NativeClaimConflict("Sealed native claims have inconsistent completion content.")
    else:
        cur.execute(
            "UPDATE native_claim_sets SET state='sealed',completion_json=%s,completion_sha256=%s,"
            "sealed_at=clock_timestamp() WHERE id=%s",
            (Jsonb(completion), digest, binding.claim_set_id),
        )
    fence_set(cur, binding, header)
    return completion


def read_sealed(
    cur: Any, binding: NativeClaimBinding, credential: RequestCredential
) -> tuple[NativeClaim, ...]:
    header = lock_retained_set(cur, binding, credential)
    if header["state"] != "sealed":
        raise NativeClaimError("Diagnostic rebuild requires a sealed native claim set.")
    claims, completion = read_inventory(cur, binding, header["expected_pages"])
    if header["completion_json"] != completion or header["completion_sha256"] != content_digest(
        completion
    ):
        raise NativeClaimConflict("Sealed native claims have inconsistent completion content.")
    assert_retained_read(cur, binding, credential)
    return claims
