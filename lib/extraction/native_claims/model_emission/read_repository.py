"""Verify retained model-claim currency without decoding the provider envelope."""

from collections import Counter
from typing import Any

from psycopg.types.json import Jsonb

from lib.auth.request_authority import RequestCredential
from lib.document_parsing.page_understanding.codec import canonical_digest
from lib.document_parsing.structure import DocumentStructure
from lib.extraction.native_claims.authority_repository import fence_set, lock_set
from lib.extraction.native_claims.errors import NativeClaimConflict, NativeClaimError
from lib.extraction.native_claims.model_emission.configuration import (
    require_supported_configuration,
)
from lib.extraction.native_claims.model_emission.models import NativeModelEmissionConfiguration
from lib.extraction.native_claims.model_emission.read_compatibility import (
    require_readable_configuration,
)
from lib.extraction.native_claims.model_emission.read_validation import (
    retained_claim,
    retained_page,
)
from lib.extraction.native_claims.models import NativeClaimBinding
from lib.extraction.native_claims.retained_repository import assert_retained_read, lock_retained_set


def read_inventory(cur: Any, binding: NativeClaimBinding, header: dict[str, Any]):
    if header["interpretation_kind"] != "model_emission":
        raise NativeClaimError("Model-emission reader cannot reinterpret recorded-text claims.")
    cur.execute(
        "SELECT structure_json FROM document_parse_generations WHERE id=%s AND document_id=%s",
        (binding.processing.parse_generation_id, binding.processing.document_id),
    )
    structure = DocumentStructure.model_validate(cur.fetchone()["structure_json"])
    cur.execute(
        "SELECT * FROM native_claim_page_checkpoints WHERE claim_set_id=%s ORDER BY page_number",
        (binding.claim_set_id,),
    )
    stored_pages = cur.fetchall()
    if tuple(p["page_number"] for p in stored_pages) != tuple(
        range(1, header["expected_pages"] + 1)
    ):
        raise NativeClaimError("Native model page inventory is incomplete.")
    cur.execute(
        "SELECT * FROM extraction_claims WHERE native_claim_set_id=%s "
        "ORDER BY native_page_number,native_member_index",
        (binding.claim_set_id,),
    )
    rows = cur.fetchall()
    claims = tuple(retained_claim(row, binding, header, structure) for row in rows)
    records = tuple(retained_page(row, claims, binding, header, structure) for row in stored_pages)
    completion = {
        "schema_version": "native_model_claim_completion.v1",
        "claim_set_id": str(binding.claim_set_id),
        "source_pages": header["expected_pages"],
        "claim_count": len(claims),
        "page_dispositions": dict(
            sorted(Counter(r.coverage_json["disposition"] for r in records).items())
        ),
        "page_classifications": dict(
            sorted(Counter(r.classification_json["outcome"] for r in records).items())
        ),
        "pages": [
            {
                "page_number": p["page_number"],
                "content_sha256": p["content_sha256"],
                "claim_count": p["claim_count"],
            }
            for p in stored_pages
        ],
        "requires_review": True,
        "source_pixel_support": "not_evaluated",
    }
    return tuple(claims), tuple(records), completion


def seal_set(
    cur: Any, binding: NativeClaimBinding, *, implementation: NativeModelEmissionConfiguration
):
    header, _ = lock_set(cur, binding)
    require_supported_configuration(header, implementation)
    _, _, completion = read_inventory(cur, binding, header)
    digest = canonical_digest(completion)
    if header["state"] == "sealed":
        if header["completion_json"] != completion or header["completion_sha256"] != digest:
            raise NativeClaimConflict("Sealed model-emission completion is inconsistent.")
    else:
        cur.execute(
            "UPDATE native_claim_sets SET state='sealed',completion_json=%s,completion_sha256=%s,"
            "sealed_at=clock_timestamp() WHERE id=%s",
            (Jsonb(completion), digest, binding.claim_set_id),
        )
    fence_set(cur, binding, header)
    return completion


def read_sealed(cur: Any, binding: NativeClaimBinding, credential: RequestCredential):
    header = lock_retained_set(cur, binding, credential)
    require_readable_configuration(header)
    if header["state"] != "sealed":
        raise NativeClaimError("Native model diagnostic rebuild requires a sealed set.")
    claims, records, completion = read_inventory(cur, binding, header)
    if header["completion_json"] != completion or header["completion_sha256"] != canonical_digest(
        completion
    ):
        raise NativeClaimConflict("Retained model-emission completion is inconsistent.")
    assert_retained_read(cur, binding, credential)
    return claims, records, completion
