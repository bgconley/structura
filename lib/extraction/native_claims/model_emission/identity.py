"""Versioned physical claim identity, independent of value and model member order."""

from typing import Any

from lib.document_parsing.page_understanding.codec import canonical_digest


def physical_identity(anchor: Any, row: Any | None) -> str:
    source = {
        "version": "native-model-physical-v1",
        "parse_generation_id": str(anchor.parse_generation_id),
        "page_id": str(anchor.page_id),
    }
    if row is None:
        return canonical_digest(
            {
                **source,
                "occurrence": anchor.model_dump(
                    mode="json",
                    include={
                        "element_id",
                        "table_id",
                        "cell_id",
                        "cell_row",
                        "cell_column",
                        "text_start",
                        "text_end",
                    },
                ),
            }
        )
    return canonical_digest({**source, "row": row.model_dump(mode="json")})


def claim_identity(claim_set_id: Any, physical_source_id: str, canonical_key: str) -> str:
    return canonical_digest(
        {
            "version": "native-model-claim-id-v1",
            "claim_set_id": str(claim_set_id),
            "physical_source_id": physical_source_id,
            "canonical_key": canonical_key,
        }
    )
