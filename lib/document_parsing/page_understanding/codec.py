"""Strict raw decoding and member identity only; no invocation/provenance assertion."""

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from lib.document_parsing.page_understanding.model import PageUnderstanding

MAX_RAW_BYTES = 16 * 1024 * 1024


def canonical_digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True)
class RawClaimMember:
    index: int
    pointer: str
    canonical_member_sha256: str


@dataclass(frozen=True)
class DecodedUnderstanding:
    page: PageUnderstanding
    raw_output_sha256: str
    claims: tuple[RawClaimMember, ...]


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON object member is not a stable source identity.")
        result[key] = value
    return result


def _invalid_constant(value: str) -> None:
    raise ValueError("Non-finite JSON number is invalid.")


def decode_page_understanding(raw: str) -> DecodedUnderstanding:
    encoded = raw.encode("utf-8")
    if len(encoded) > MAX_RAW_BYTES:
        raise ValueError("Combined output exceeds the declared response bound.")
    value = json.loads(raw, object_pairs_hook=_unique_object, parse_constant=_invalid_constant)
    page = PageUnderstanding.model_validate(value)
    members = tuple(
        RawClaimMember(index, f"/extraction/claims/{index}", canonical_digest(member))
        for index, member in enumerate(value["extraction"]["claims"])
    )
    return DecodedUnderstanding(page, hashlib.sha256(encoded).hexdigest(), members)
