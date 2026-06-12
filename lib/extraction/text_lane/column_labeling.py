"""Model column-role labeling for the extractive table lane (ADR 0006 X2).

The model's entire authority here is mapping column_index -> role through a
closed enum built from the target family's claim-registry line-item fields
plus "ignore". It sees only header labels and a few sample rows as text; it
cannot emit a value, so transcription failure classes are unrepresentable.
Labels are cached in-process by (family, header fingerprint) so identical
table shapes never re-call the model.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any, Protocol

from lib.config import get_settings
from lib.extraction.claim_registry import CLAIM_FAMILY_REGISTRIES
from lib.extraction.text_lane.table_grid import TableGrid
from lib.model_runtime.clients._openai_text import OpenAITextGenerateClient
from lib.model_runtime.contracts import TextGenerateRequest
from lib.model_runtime.profiles import get_model_profile

COLUMN_LABELING_PROMPT_VERSION = "text_lane_column_labeling.v1"
IGNORE_ROLE = "ignore"
MAX_COLUMN_LABEL_CACHE_SIZE = 128
_SAMPLE_DATA_ROWS = 3
_MAX_SAMPLE_CELL_CHARS = 48

# Role glosses must match the claim registry's canonical meaning per family:
# for medical EOBs the registry projects role "amount" to the line's patient
# responsibility, not the billed/extended total.
_DEFAULT_ROLE_GLOSS = '"amount" is the line\'s extended/net total.'
_ROLE_GLOSSES = {
    "medical_eob": (
        '"gross_amount" is the billed amount, "allowed_amount" the allowed '
        'amount, "plan_paid" the plan-paid amount, and "amount" is the '
        "patient responsibility for the line."
    ),
}

# Labels cache across gateway/service instances within the worker process:
# the extraction worker builds a fresh service per job, so an instance-level
# cache would never hit.
_LABEL_CACHE: OrderedDict[tuple[str, str, str, str], ColumnLabeling] = OrderedDict()
_LABEL_CACHE_LOCK = threading.Lock()


class ColumnLabelingValidationError(ValueError):
    """The model response did not assign exactly one role per physical column."""


@dataclass(frozen=True)
class ColumnLabeling:
    roles: Mapping[int, str]
    model_name: str
    model_version: str
    prompt_version: str
    from_cache: bool = False

    def roles_json(self) -> dict[str, str]:
        return {str(index): role for index, role in sorted(self.roles.items())}


class ColumnRoleLabeler(Protocol):
    def label_columns(self, *, family: str, grid: TableGrid) -> ColumnLabeling: ...


def line_item_roles(family: str) -> tuple[str, ...]:
    """Closed role vocabulary for a family: registry line-item fields."""
    registry = CLAIM_FAMILY_REGISTRIES.get(family)
    if registry is None or registry.line_item_projection is None:
        return ()
    return tuple(registry.line_item_projection.field_map)


def column_labeling_schema(*, num_cols: int, roles: tuple[str, ...]) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["columns"],
        "properties": {
            "columns": {
                "type": "array",
                "minItems": num_cols,
                "maxItems": num_cols,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["column_index", "role"],
                    "properties": {
                        "column_index": {
                            "type": "integer",
                            "minimum": 0,
                            "maximum": max(0, num_cols - 1),
                        },
                        "role": {"type": "string", "enum": [*roles, IGNORE_ROLE]},
                    },
                },
            }
        },
    }


def column_labeling_prompt(*, family: str, grid: TableGrid, roles: tuple[str, ...]) -> str:
    lines = [
        f"You are labeling the columns of a {family} line-item table extracted from a document.",
        "Assign exactly one role to every column index. Use role values only from this list:",
        ", ".join([*roles, IGNORE_ROLE]) + ".",
        _ROLE_GLOSSES.get(family, _DEFAULT_ROLE_GLOSS),
        'Use "ignore" for columns that are not line-item data.',
        "",
        "Column headers:",
    ]
    for index, label in enumerate(grid.header_labels()):
        lines.append(f"  column {index}: {label or '(blank header)'}")
    lines.append("")
    lines.append("Sample rows:")
    for row_index in grid.data_row_indexes[:_SAMPLE_DATA_ROWS]:
        cells = grid.row_cells(row_index)
        rendered = " | ".join(
            (cell.normalized_text[:_MAX_SAMPLE_CELL_CHARS] if cell is not None else "")
            for cell in cells
        )
        lines.append(f"  {rendered}")
    lines.append("")
    lines.append(
        "Respond with JSON only: "
        '{"columns": [{"column_index": <int>, "role": <role>}, ...]} '
        f"covering all {grid.num_cols} columns."
    )
    return "\n".join(lines)


def clear_column_label_cache() -> None:
    with _LABEL_CACHE_LOCK:
        _LABEL_CACHE.clear()


class LiveColumnRoleLabeler:
    def __init__(self, *, client: OpenAITextGenerateClient | None = None) -> None:
        self._client = client

    def label_columns(self, *, family: str, grid: TableGrid) -> ColumnLabeling:
        roles = line_item_roles(family)
        if not roles:
            raise ValueError(f"Family {family} has no registered line-item roles.")
        profile_name = self._profile_name()
        cache_key = (
            COLUMN_LABELING_PROMPT_VERSION,
            profile_name,
            family,
            grid.header_fingerprint(),
        )
        with _LABEL_CACHE_LOCK:
            cached = _LABEL_CACHE.get(cache_key)
            if cached is not None:
                _LABEL_CACHE.move_to_end(cache_key)
        if cached is not None:
            return replace(cached, from_cache=True)
        labeling = self._label_columns_live(family=family, grid=grid, roles=roles)
        with _LABEL_CACHE_LOCK:
            _LABEL_CACHE.setdefault(cache_key, labeling)
            _LABEL_CACHE.move_to_end(cache_key)
            while len(_LABEL_CACHE) > MAX_COLUMN_LABEL_CACHE_SIZE:
                _LABEL_CACHE.popitem(last=False)
        return labeling

    def _profile_name(self) -> str:
        if self._client is not None:
            return self._client.profile.name
        return get_settings().qwen_semantic_profile

    def _label_columns_live(
        self,
        *,
        family: str,
        grid: TableGrid,
        roles: tuple[str, ...],
    ) -> ColumnLabeling:
        client = self._ensure_client()
        request = TextGenerateRequest(
            profile_name=client.profile.name,
            prompt_version=COLUMN_LABELING_PROMPT_VERSION,
            prompt=column_labeling_prompt(family=family, grid=grid, roles=roles),
            response_schema_name=COLUMN_LABELING_PROMPT_VERSION,
            max_output_tokens=min(1024, 256 + 32 * grid.num_cols),
            temperature=0.0,
            timeout_seconds=get_settings().model_http_timeout_seconds,
            response_json_schema=column_labeling_schema(num_cols=grid.num_cols, roles=roles),
            seed=0,
        )
        response = client.generate(request)
        return ColumnLabeling(
            roles=roles_from_payload(response.normalized_json, num_cols=grid.num_cols),
            model_name=response.model_name,
            model_version=response.model_version,
            prompt_version=COLUMN_LABELING_PROMPT_VERSION,
        )

    def _ensure_client(self) -> OpenAITextGenerateClient:
        if self._client is None:
            settings = get_settings()
            self._client = OpenAITextGenerateClient(
                profile=get_model_profile(settings.qwen_semantic_profile),
                http_client_base_url=settings.model_qwen_semantic_url,
            )
        return self._client


def roles_from_payload(payload: Mapping[str, Any], *, num_cols: int) -> dict[int, str]:
    """Validate and collapse the columns array into column_index -> role."""
    roles: dict[int, str] = {}
    columns = payload.get("columns")
    if not isinstance(columns, list):
        raise ColumnLabelingValidationError("missing_columns_array")
    for entry in columns:
        if not isinstance(entry, Mapping):
            raise ColumnLabelingValidationError("invalid_column_entry")
        index = entry.get("column_index")
        role = entry.get("role")
        if not isinstance(index, int) or isinstance(index, bool) or not (0 <= index < num_cols):
            raise ColumnLabelingValidationError(f"invalid_column_index:{index}")
        if not isinstance(role, str) or not role:
            raise ColumnLabelingValidationError(f"invalid_column_role:{index}")
        if index in roles:
            raise ColumnLabelingValidationError(f"duplicate_column_index:{index}")
        roles[index] = role
    for index in range(num_cols):
        if index not in roles:
            raise ColumnLabelingValidationError(f"missing_column_index:{index}")
    return roles
