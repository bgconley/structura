"""Diagnostic grouping only; reported coverage is not source-verified fact acceptance."""

from collections import defaultdict

from lib.document_parsing.page_understanding.codec import canonical_digest
from lib.extraction.native_claims.model_emission.models import NativeModelClaim
from lib.extraction.native_claims.model_emission.page_models import NativeModelPageRecord


def diagnostic_projection(
    claims: tuple[NativeModelClaim, ...], pages: tuple[NativeModelPageRecord, ...]
):
    fields: dict[str, list[NativeModelClaim]] = defaultdict(list)
    rows: dict[str, list[NativeModelClaim]] = defaultdict(list)
    for claim in claims:
        (
            fields[claim.proposed.canonical_key] if claim.group_id is None else rows[claim.group_id]
        ).append(claim)
    return {
        "schema_version": "native_model_claim_diagnostics.v1",
        "claims_are_accepted_facts": False,
        "source_pixel_support": "not_evaluated",
        "arithmetic_validation": "not_evaluated",
        "document_required_key_evaluation": "not_evaluated",
        "coverage_basis": "model_reported_page_accounting",
        "claim_count": len(claims),
        "pages": [p.model_dump(mode="json") for p in pages],
        "field_groups": [
            {
                "canonical_key": key,
                "requires_review": True,
                "value_conflict": len(
                    {
                        canonical_digest(c.proposed.model_dump(mode="json")["typed_value"])
                        for c in items
                    }
                )
                > 1,
                "claims": [
                    c.model_dump(mode="json") for c in sorted(items, key=lambda c: c.claim_id)
                ],
            }
            for key, items in sorted(fields.items())
        ],
        "line_rows": [
            {
                "physical_row_id": key,
                "requires_review": True,
                "claims": [
                    c.model_dump(mode="json")
                    for c in sorted(items, key=lambda c: c.proposed.canonical_key)
                ],
            }
            for key, items in sorted(
                rows.items(),
                key=lambda p: (p[1][0].anchor.page_number, p[1][0].anchor.bbox.top, p[0]),
            )
        ],
    }
