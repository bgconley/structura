"""Pure derivation from an exact persisted checkpoint; no caller-selected values."""

import json
from typing import Any, Literal, cast

from lib.document_parsing.page_understanding.claims import ProposedClaim
from lib.document_parsing.page_understanding.codec import (
    RawClaimMember,
    canonical_digest,
    decode_page_understanding,
)
from lib.document_parsing.page_understanding.interpretation import interpretation_diagnostics
from lib.document_parsing.page_understanding.locators import SourceQuote
from lib.document_parsing.qwen_page_parser import ParsedSourcePage
from lib.document_parsing.structure import SourceInventory
from lib.document_processing.checkpoint_validation import validate_checkpoint
from lib.document_processing.configuration_types import ParseConfigurationV2
from lib.document_processing.models import content_digest
from lib.extraction.native_claims.errors import NativeClaimConflict
from lib.extraction.native_claims.model_emission.anchors import bind_quote, bind_row
from lib.extraction.native_claims.model_emission.identity import claim_identity, physical_identity
from lib.extraction.native_claims.model_emission.models import (
    ModelClaimSupport,
    NativeMemberBinding,
    NativeModelClaim,
    NativeModelEmissionConfiguration,
)
from lib.extraction.native_claims.model_emission.page_evidence import bound_page_evidence
from lib.extraction.native_claims.model_emission.page_models import (
    NativeModelPageRecord,
)
from lib.extraction.native_claims.models import NativeClaimBinding


def import_checkpoint(
    binding: NativeClaimBinding,
    configuration: NativeModelEmissionConfiguration,
    parse_configuration: ParseConfigurationV2,
    inventory: SourceInventory,
    checkpoint: ParsedSourcePage,
    checkpoint_sha256: str,
) -> tuple[NativeModelPageRecord, tuple[NativeModelClaim, ...]]:
    if configuration.definitions != parse_configuration.definitions:
        raise NativeClaimConflict("Native model import definitions differ from its parse.")
    source_engine = checkpoint.invocation.source_engine
    if source_engine != "qwen3_8_27b" or parse_configuration.source_engine != source_engine:
        raise NativeClaimConflict("Native model source engine is not the recorded Qwen provider.")
    payload = {
        "page": checkpoint.page.model_dump(mode="json"),
        "invocation": checkpoint.invocation.model_dump(mode="json"),
        "raw": checkpoint.raw_output,
    }
    if content_digest(payload) != checkpoint_sha256:
        raise NativeClaimConflict("Native model checkpoint content hash is inconsistent.")
    validate_checkpoint(
        checkpoint,
        generation_id=binding.processing.parse_generation_id,
        inventory=inventory,
        configuration=parse_configuration,
    )
    decoded = decode_page_understanding(checkpoint.raw_output)
    # The frozen decoder already rejects duplicate/nonfinite members and bounds bytes.
    raw = json.loads(checkpoint.raw_output)
    diagnostics = interpretation_diagnostics(decoded.page)
    claims = tuple(
        _derive_claim(
            binding,
            configuration,
            checkpoint,
            checkpoint_sha256,
            decoded.raw_output_sha256,
            cast(Literal["qwen3_8_27b"], source_engine),
            proposed,
            member,
            raw["extraction"]["claims"][index],
            tuple(diagnostics[index]["reasons"]),
        )
        for index, (proposed, member) in enumerate(
            zip(decoded.page.extraction.claims, decoded.claims, strict=True)
        )
    )
    classification = raw["classification"]
    coverage = {k: v for k, v in raw["extraction"].items() if k != "claims"}
    evidence = bound_page_evidence(
        checkpoint.page, binding.processing.parse_generation_id, classification, coverage
    )
    record = NativeModelPageRecord(
        page_number=checkpoint.page.page_number,
        page_id=checkpoint.page.id,
        checkpoint_sha256=checkpoint_sha256,
        raw_output_sha256=decoded.raw_output_sha256,
        classification_json=classification,
        classification_sha256=canonical_digest(classification),
        coverage_json=coverage,
        coverage_sha256=canonical_digest(coverage),
        bound_evidence=evidence,
        members=tuple(c.member for c in claims),
    )
    return record, tuple(claims)


def _derive_claim(
    binding: NativeClaimBinding,
    configuration: NativeModelEmissionConfiguration,
    checkpoint: ParsedSourcePage,
    checkpoint_sha256: str,
    raw_output_sha256: str,
    source_engine: Literal["qwen3_8_27b"],
    proposed: ProposedClaim,
    member: RawClaimMember,
    raw_member: dict[str, Any],
    diagnostics: tuple[str, ...],
) -> NativeModelClaim:
    anchor = bind_quote(
        checkpoint.page,
        SourceQuote(locator=proposed.primary_source, quote=proposed.raw_value),
        binding.processing.parse_generation_id,
    )
    row = bind_row(checkpoint.page, proposed.physical_row)
    physical = physical_identity(anchor, row)
    identity = claim_identity(binding.claim_set_id, physical, proposed.canonical_key)
    return NativeModelClaim(
        claim_id=identity,
        claim_set_id=binding.claim_set_id,
        document_id=binding.processing.document_id,
        source_engine=source_engine,
        raw_member_json=raw_member,
        proposed=proposed,
        member=NativeMemberBinding(
            index=member.index,
            pointer=member.pointer,
            canonical_member_sha256=member.canonical_member_sha256,
            claim_id=identity,
        ),
        anchor=anchor,
        supporting_anchors=tuple(
            ModelClaimSupport(
                role=s.role,
                anchor=bind_quote(checkpoint.page, s, binding.processing.parse_generation_id),
            )
            for s in proposed.supporting_sources
        ),
        physical_row=row,
        physical_source_id=physical,
        group_id=physical if row else None,
        configuration_sha256=configuration.fingerprint,
        checkpoint_sha256=checkpoint_sha256,
        invocation_request_id=checkpoint.invocation.request_id,
        raw_output_sha256=raw_output_sha256,
        interpretation_diagnostics=diagnostics,
    )
