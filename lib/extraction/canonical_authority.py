"""Human authority over canonical facts, independent of storage and review entrypoints."""

from collections.abc import Mapping


def canonical_field_is_human_controlled(row: Mapping[str, object] | None) -> bool:
    # Confirmation retains candidate origin; deleted users can lose actor FKs.
    # Each independent human marker therefore preserves the decision's authority.
    return bool(
        row
        and (
            row.get("source_kind") == "human"
            or row.get("review_status") in {"user_confirmed", "user_corrected"}
            or row.get("accepted_by_user_id") is not None
        )
    )
