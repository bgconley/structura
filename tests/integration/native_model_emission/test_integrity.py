"""Adversarial SQL branch/accounting checks, independent of normal DTO construction."""

from copy import deepcopy
from uuid import uuid4

import pytest
from psycopg import errors
from psycopg.types.json import Jsonb

from lib.auth.request_authority import RequestCredential
from lib.db.connection import db_connection
from lib.document_parsing.page_understanding.codec import canonical_digest
from lib.extraction.native_claims.errors import NativeClaimConflict, NativeClaimError
from lib.extraction.native_claims.model_emission import page_repository
from lib.extraction.native_claims.model_emission.configuration import installed_configuration
from lib.extraction.native_claims.model_emission.service import NativeModelEmissionService


def copied_claim(binding):
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT to_jsonb(c) AS payload FROM extraction_claims c "
            "WHERE native_claim_set_id=%s ORDER BY native_member_index LIMIT 1",
            (binding.claim_set_id,),
        )
        row = deepcopy(cur.fetchone()["payload"])
    row["id"] = str(uuid4())
    row["claim_id"] = uuid4().hex * 2
    row["native_payload_json"]["claim_id"] = row["claim_id"]
    row["native_payload_json"]["member"]["claim_id"] = row["claim_id"]
    return row


@pytest.mark.parametrize(
    "change",
    [
        "null_page",
        "foreign_document",
        "foreign_generation",
        "checkpoint",
        "invocation",
        "engine",
        "raw_member",
        "trusted",
        "member_null",
        "duplicate_member",
    ],
)
def test_sql_rejects_incomplete_or_foreign_native_member_bindings(model_source, change):
    processing, _, claimed, binding, _ = model_source
    with processing.scope(claimed):
        NativeModelEmissionService().checkpoint(binding, 1)
    row = copied_claim(binding)
    payload = row["native_payload_json"]
    if change == "null_page":
        row["native_page_number"] = None
    elif change == "foreign_document":
        row["document_id"] = payload["document_id"] = str(uuid4())
    elif change == "foreign_generation":
        payload["anchor"]["parse_generation_id"] = str(uuid4())
        row["anchor_json"] = payload["anchor"]
    elif change == "checkpoint":
        payload["checkpoint_sha256"] = "f" * 64
    elif change == "invocation":
        payload["invocation_request_id"] = str(uuid4())
    elif change == "engine":
        payload["source_engine"] = "docling"
    elif change == "raw_member":
        payload["raw_member_json"]["typed_value"] = "000456"
    elif change == "trusted":
        payload["requires_review"] = False
    elif change == "member_null":
        row["native_member_index"] = None
    failure = (
        errors.UniqueViolation
        if change == "duplicate_member"
        else (errors.CheckViolation if change == "trusted" else errors.RaiseException)
    )
    with (
        pytest.raises(failure),
        db_connection() as conn,
        conn.cursor() as cur,
    ):
        cur.execute(
            "INSERT INTO extraction_claims "
            "SELECT (jsonb_populate_record(NULL::extraction_claims,%s)).*",
            (Jsonb(row),),
        )
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) AS n FROM extraction_claims WHERE native_claim_set_id=%s",
            (binding.claim_set_id,),
        )
        assert cur.fetchone()["n"] == 5


def test_partial_member_inventory_never_seals_or_becomes_readable(model_source, monkeypatch):
    processing, _, claimed, binding, _ = model_source
    insert = page_repository._insert_claim
    monkeypatch.setattr(
        page_repository,
        "_insert_claim",
        lambda cur, claim: insert(cur, claim) if claim.member.index != 4 else None,
    )
    service = NativeModelEmissionService()
    with processing.scope(claimed):
        service.checkpoint(binding, 1)
        with pytest.raises(NativeClaimConflict, match="accounting"):
            service.seal(binding)
    with pytest.raises(NativeClaimError, match="sealed"):
        service.rebuild(binding, credential=RequestCredential.from_principal(processing.principal))
    with (
        pytest.raises(errors.RaiseException, match="incomplete"),
        db_connection() as conn,
        conn.cursor() as cur,
    ):
        cur.execute(
            "UPDATE native_claim_sets SET state='sealed',completion_json='{}',"
            "completion_sha256=%s,sealed_at=clock_timestamp() WHERE id=%s",
            ("a" * 64, binding.claim_set_id),
        )


def test_changed_importer_cannot_append_or_seal_existing_set(model_source, monkeypatch):
    processing, _, claimed, binding, _ = model_source
    changed = installed_configuration().model_copy(update={"implementation_sha256": "f" * 64})
    monkeypatch.setattr(
        "lib.extraction.native_claims.model_emission.service.installed_configuration",
        lambda: changed,
    )
    service = NativeModelEmissionService()
    with processing.scope(claimed):
        for operation in (lambda: service.checkpoint(binding, 1), lambda: service.seal(binding)):
            with pytest.raises(NativeClaimConflict, match="configuration is unsupported"):
                operation()
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) AS n FROM native_claim_page_checkpoints WHERE claim_set_id=%s",
            (binding.claim_set_id,),
        )
        assert cur.fetchone()["n"] == 0


@pytest.mark.parametrize("change", ["classification", "coverage", "cached_member"])
def test_database_page_cache_must_equal_exact_persisted_raw_members(
    model_source, monkeypatch, change
):
    processing, _, claimed, binding, _ = model_source
    importer = page_repository.import_checkpoint

    def substituted(*args, **kwargs):
        record, claims = importer(*args, **kwargs)
        if change == "cached_member":
            altered = {**claims[0].raw_member_json, "typed_value": "000456"}
            claims = (claims[0].model_copy(update={"raw_member_json": altered}), *claims[1:])
        else:
            value = deepcopy(record.model_dump(mode="json"))
            if change == "classification":
                value["classification_json"]["primary_family"] = "receipt"
                value["classification_json"]["alternatives"][0]["family"] = "receipt"
                value["classification_sha256"] = canonical_digest(value["classification_json"])
            else:
                value["coverage_json"]["families"][0]["fields"].pop()
                value["coverage_sha256"] = canonical_digest(value["coverage_json"])
            record = type(record).model_validate(value)
        return record, claims

    monkeypatch.setattr(page_repository, "import_checkpoint", substituted)
    with processing.scope(claimed), pytest.raises(errors.RaiseException, match="raw source"):
        NativeModelEmissionService().checkpoint(binding, 1)
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) AS n FROM native_claim_page_checkpoints WHERE claim_set_id=%s",
            (binding.claim_set_id,),
        )
        assert cur.fetchone()["n"] == 0
