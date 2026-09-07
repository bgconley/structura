from copy import deepcopy
from types import SimpleNamespace

import pytest

from lib.document_parsing.page_understanding.codec import canonical_digest
from lib.extraction.native_claims.errors import NativeClaimConflict
from lib.extraction.native_claims.model_emission.configuration import installed_configuration
from lib.extraction.native_claims.model_emission.import_page import import_checkpoint
from lib.extraction.native_claims.model_emission.models import NativeModelClaim
from lib.extraction.native_claims.model_emission.page_repository import page_digest
from lib.extraction.native_claims.model_emission.read_validation import (
    retained_claim,
    retained_page,
)
from tests.fixtures.native_model_emission_source import digest, source
from tests.fixtures.page_understanding_sources import invoice_page, quote


@pytest.mark.parametrize("kind", ["primary", "support"])
def test_retained_rebuild_rejects_equal_text_rebound_to_a_different_source_cell(kind):
    output = invoice_page()
    if kind == "support":
        output["extraction"]["claims"][2]["supporting_sources"] = [
            {**quote(1, "USD 12.3400", row=1, column=1), "role": "currency"}
        ]
    binding, parse, inventory, checkpoint = source(output)
    config = installed_configuration()
    _, claims = import_checkpoint(binding, config, parse, inventory, checkpoint, digest(checkpoint))
    header = {
        "configuration_sha256": config.fingerprint,
        "source_manifest_json": {
            "pages": [
                {
                    "page_number": 1,
                    "checkpoint_sha256": digest(checkpoint),
                    "invocation": checkpoint.invocation.model_dump(mode="json"),
                }
            ]
        },
    }

    def row_for(claim):
        return {
            "origin_kind": "native_model_emission",
            "native_payload_json": claim.model_dump(mode="json"),
            "native_content_sha256": claim.fingerprint,
            "native_page_number": 1,
            "claim_id": claim.claim_id,
            "native_member_index": claim.member.index,
            "native_member_sha256": claim.member.canonical_member_sha256,
        }

    assert (
        retained_claim(
            row_for(claims[2]), binding, header, SimpleNamespace(pages=(checkpoint.page,))
        )
        == claims[2]
    )
    payload = deepcopy(claims[2].model_dump(mode="json"))
    other = claims[4].anchor.model_dump(mode="json")
    if kind == "primary":
        payload["anchor"] = other
    else:
        payload["supporting_anchors"][0]["anchor"] = other
    altered = NativeModelClaim.model_validate(payload)
    # Recompute the entire payload hash: exact locator rebinding is checked independently.
    with pytest.raises(NativeClaimConflict, match="source|support"):
        retained_claim(row_for(altered), binding, header, SimpleNamespace(pages=(checkpoint.page,)))


@pytest.mark.parametrize("change", ["missing_obligation", "claim_index", "row", "classification"])
def test_retained_ledger_revalidates_cross_member_accounting_after_recomputed_hashes(change):
    binding, parse, inventory, checkpoint = source()
    record, claims = import_checkpoint(
        binding, installed_configuration(), parse, inventory, checkpoint, digest(checkpoint)
    )
    header = {
        "source_manifest_json": {
            "pages": [
                {
                    "page_number": 1,
                    "checkpoint_sha256": digest(checkpoint),
                    "invocation": checkpoint.invocation.model_dump(mode="json"),
                }
            ]
        }
    }
    payload = record.model_dump(mode="json")
    if change == "missing_obligation":
        payload["coverage_json"]["families"][0]["fields"] = [
            f
            for f in payload["coverage_json"]["families"][0]["fields"]
            if f["canonical_key"] != "invoice.seller.display_name"
        ]
    elif change == "claim_index":
        next(
            f
            for f in payload["coverage_json"]["families"][0]["fields"]
            if f["canonical_key"] == "invoice.invoice_number"
        )["claim_indices"] = [2]
    elif change == "row":
        payload["coverage_json"]["families"][0]["rows"][1]["physical_row"]["row"] = 1
    else:
        payload["classification_json"]["primary_family"] = "receipt"
        payload["classification_json"]["alternatives"][0]["family"] = "receipt"
    payload["coverage_sha256"] = canonical_digest(payload["coverage_json"])
    payload["classification_sha256"] = canonical_digest(payload["classification_json"])
    changed = type(record).model_validate(payload)
    row = {
        "request_json": payload,
        "page_number": 1,
        "page_id": record.page_id,
        "source_checkpoint_sha256": record.checkpoint_sha256,
        "claim_count": len(claims),
        "source_members_json": [c.raw_member_json for c in claims],
        "content_sha256": page_digest(changed, claims),
    }
    with pytest.raises(ValueError, match="obligation|Coverage|row|ledger|family"):
        retained_page(row, claims, binding, header, SimpleNamespace(pages=(checkpoint.page,)))
