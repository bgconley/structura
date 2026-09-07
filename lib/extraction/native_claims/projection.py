"""Pure diagnostic grouping of persisted claims; no selected/accepted fact output."""

from collections import defaultdict
from typing import Any

from lib.document_processing.models import content_digest
from lib.extraction.native_claims.models import NativeClaim


def diagnostic_projection(claims: tuple[NativeClaim, ...]) -> dict[str, Any]:
    fields: dict[str, list[NativeClaim]] = defaultdict(list)
    rows: dict[str, list[NativeClaim]] = defaultdict(list)
    for claim in claims:
        if claim.group_id is None:
            fields[claim.canonical_key].append(claim)
        else:
            rows[claim.group_id].append(claim)
    grouped_fields = []
    for key, items in sorted(fields.items()):
        payloads = [c.model_dump(mode="json") for c in sorted(items, key=lambda c: c.claim_id)]
        values = {content_digest(p["typed_value"]) for p in payloads}
        grouped_fields.append(
            {
                "canonical_key": key,
                "claims": payloads,
                "value_conflict": len(values) > 1,
                "requires_review": True,
            }
        )
    grouped_rows = []
    for identity, items in sorted(rows.items(), key=lambda pair: _row_order(pair[1][0])):
        grouped_rows.append(
            {
                "physical_row_id": identity,
                "requires_review": True,
                "claims": [
                    c.model_dump(mode="json") for c in sorted(items, key=lambda c: c.canonical_key)
                ],
            }
        )
    return {
        "schema_version": "native_claim_diagnostics.v1",
        "claims_are_accepted_facts": False,
        "source_pixel_support": "not_evaluated",
        "arithmetic_validation": "not_evaluated",
        "required_key_evaluation": "not_evaluated",
        "field_groups": grouped_fields,
        "line_rows": grouped_rows,
        "claim_count": len(claims),
    }


def _row_order(claim: NativeClaim) -> tuple[Any, ...]:
    anchor = claim.anchor
    return (
        anchor.page_number,
        anchor.bbox.top,
        anchor.bbox.left,
        str(anchor.table_id or anchor.element_id),
        anchor.row_index or 0,
        claim.claim_id,
    )
