"""Atomic exact-member page import; the only derivation input is the locked checkpoint."""

from typing import Any
from uuid import uuid5

from psycopg.types.json import Jsonb

from lib.extraction.native_claims.authority_repository import fence_set, lock_set
from lib.extraction.native_claims.errors import NativeClaimConflict, NativeClaimError
from lib.extraction.native_claims.model_emission.configuration import (
    require_supported_configuration,
)
from lib.extraction.native_claims.model_emission.import_page import import_checkpoint
from lib.extraction.native_claims.model_emission.models import (
    NativeModelClaim,
    NativeModelEmissionConfiguration,
)
from lib.extraction.native_claims.model_emission.page_models import page_digest as page_digest
from lib.extraction.native_claims.model_emission.source_repository import read_checkpoint
from lib.extraction.native_claims.models import NativeClaimBinding


def persist_page(
    cur: Any,
    binding: NativeClaimBinding,
    page_number: int,
    *,
    implementation: NativeModelEmissionConfiguration,
) -> str:
    if (
        isinstance(page_number, bool)
        or not isinstance(page_number, int)
        or not 1 <= page_number <= 500
    ):
        raise NativeClaimError("Native model source page number is invalid.")
    header, source = lock_set(cur, binding)
    config = require_supported_configuration(header, implementation)
    parse_config, checkpoint, checkpoint_hash = read_checkpoint(cur, binding, page_number)
    record, claims = import_checkpoint(
        binding, config, parse_config, source.structure.source, checkpoint, checkpoint_hash
    )
    digest = page_digest(record, claims)
    cur.execute(
        "SELECT content_sha256 FROM native_claim_page_checkpoints "
        "WHERE claim_set_id=%s AND page_number=%s",
        (binding.claim_set_id, page_number),
    )
    existing = cur.fetchone()
    if existing:
        if existing["content_sha256"] != digest:
            raise NativeClaimConflict("Native model page already has different content.")
    else:
        if header["state"] != "building":
            raise NativeClaimConflict("Sealed native model claims cannot acquire new content.")
        cur.execute(
            """INSERT INTO native_claim_page_checkpoints
        (claim_set_id,document_id,parse_generation_id,page_number,page_id,request_json,
         content_sha256,claim_count,source_checkpoint_sha256,source_members_json)
         VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (
                binding.claim_set_id,
                binding.processing.document_id,
                binding.processing.parse_generation_id,
                page_number,
                record.page_id,
                Jsonb(record.model_dump(mode="json")),
                digest,
                len(claims),
                checkpoint_hash,
                Jsonb([claim.raw_member_json for claim in claims]),
            ),
        )
        for claim in claims:
            _insert_claim(cur, claim)
    fence_set(cur, binding, header)
    return digest


def _insert_claim(cur: Any, claim: NativeModelClaim) -> None:
    payload = claim.model_dump(mode="json")
    cur.execute(
        """INSERT INTO extraction_claims
    (id,extraction_id,document_id,claim_id,method,source_engine,canonical_key,raw_value,
     typed_value_json,value_type,group_id,anchor_json,evidence_json,metadata_json,
     origin_kind,native_claim_set_id,native_page_number,native_payload_json,native_content_sha256,
     native_member_index,native_member_sha256)
    VALUES (%s,NULL,%s,%s,'model_emission:v1','qwen3_8_27b',%s,%s,%s,%s,%s,%s,%s,%s,
            'native_model_emission',%s,%s,%s,%s,%s,%s)""",
        (
            uuid5(claim.claim_set_id, "native-model-claim:" + claim.claim_id),
            claim.document_id,
            claim.claim_id,
            claim.proposed.canonical_key,
            claim.proposed.raw_value,
            Jsonb(payload["proposed"]["typed_value"]),
            claim.proposed.value_type,
            claim.group_id,
            Jsonb(payload["anchor"]),
            Jsonb([payload["anchor"], *[s["anchor"] for s in payload["supporting_anchors"]]]),
            Jsonb({"schema_version": "native_model_claim.v1", "requires_review": True}),
            claim.claim_set_id,
            claim.anchor.page_number,
            Jsonb(payload),
            claim.fingerprint,
            claim.member.index,
            claim.member.canonical_member_sha256,
        ),
    )
