"""Pure retained payload/source checks, without provider-envelope decoding."""

from lib.document_parsing.page_understanding.locators import SourceQuote
from lib.extraction.native_claims.errors import NativeClaimConflict
from lib.extraction.native_claims.model_emission.anchors import bind_quote, bind_row
from lib.extraction.native_claims.model_emission.models import NativeModelClaim
from lib.extraction.native_claims.model_emission.page_evidence import bound_page_evidence
from lib.extraction.native_claims.model_emission.page_models import (
    NativeModelPageRecord,
    page_digest,
)
from lib.extraction.native_claims.model_emission.retained_products import validate_retained_products


def retained_claim(row, binding, header, structure):
    claim = NativeModelClaim.model_validate(row["native_payload_json"])
    page = next((p for p in structure.pages if p.page_number == claim.anchor.page_number), None)
    source = next(
        (
            p
            for p in header["source_manifest_json"]["pages"]
            if p["page_number"] == claim.anchor.page_number
        ),
        None,
    )
    if (
        row["origin_kind"] != "native_model_emission"
        or claim.fingerprint != row["native_content_sha256"]
        or claim.claim_set_id != binding.claim_set_id
        or claim.document_id != binding.processing.document_id
        or claim.anchor.parse_generation_id != binding.processing.parse_generation_id
        or claim.anchor.page_number != row["native_page_number"]
        or claim.claim_id != row["claim_id"]
        or claim.member.index != row["native_member_index"]
        or claim.member.canonical_member_sha256 != row["native_member_sha256"]
        or claim.configuration_sha256 != header["configuration_sha256"]
        or page is None
        or source is None
    ):
        raise NativeClaimConflict("Retained native model claim binding is inconsistent.")
    if (
        claim.checkpoint_sha256 != source["checkpoint_sha256"]
        or str(claim.invocation_request_id) != source["invocation"]["request_id"]
        or claim.raw_output_sha256 != source["invocation"]["raw_output_sha256"]
        or claim.source_engine != source["invocation"]["source_engine"]
    ):
        raise NativeClaimConflict("Retained native model invocation binding is inconsistent.")
    expected = bind_quote(
        page,
        SourceQuote(locator=claim.proposed.primary_source, quote=claim.proposed.raw_value),
        binding.processing.parse_generation_id,
    )
    if (
        expected != claim.anchor
        or bind_row(page, claim.proposed.physical_row) != claim.physical_row
    ):
        raise NativeClaimConflict("Retained native model claim source is inconsistent.")
    for support, raw in zip(
        claim.supporting_anchors, claim.proposed.supporting_sources, strict=True
    ):
        if support.anchor != bind_quote(page, raw, binding.processing.parse_generation_id):
            raise NativeClaimConflict("Retained native model claim support is inconsistent.")
    return claim


def retained_page(row, claims, binding, header, structure):
    record = NativeModelPageRecord.model_validate(row["request_json"])
    items = tuple(c for c in claims if c.anchor.page_number == record.page_number)
    page = next((p for p in structure.pages if p.page_number == record.page_number), None)
    source = next(
        (
            p
            for p in header["source_manifest_json"]["pages"]
            if p["page_number"] == record.page_number
        ),
        None,
    )
    if (
        record.page_number != row["page_number"]
        or record.page_id != row["page_id"]
        or record.checkpoint_sha256 != row["source_checkpoint_sha256"]
        or len(items) != row["claim_count"]
        or [c.raw_member_json for c in items] != row["source_members_json"]
        or record.members != tuple(c.member for c in items)
        or page_digest(record, items) != row["content_sha256"]
        or page is None
        or source is None
    ):
        raise NativeClaimConflict("Retained native model page accounting is inconsistent.")
    if (
        record.checkpoint_sha256 != source["checkpoint_sha256"]
        or record.raw_output_sha256 != source["invocation"]["raw_output_sha256"]
        or record.page_id != page.id
        or record.bound_evidence
        != bound_page_evidence(
            page,
            binding.processing.parse_generation_id,
            record.classification_json,
            record.coverage_json,
        )
    ):
        raise NativeClaimConflict("Retained native model page source is inconsistent.")
    validate_retained_products(page, record, items)
    return record
