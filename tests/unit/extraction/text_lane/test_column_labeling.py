from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import pytest

from lib.extraction.models import ParsedTableText
from lib.extraction.text_lane.column_labeling import (
    COLUMN_LABELING_PROMPT_VERSION,
    IGNORE_ROLE,
    MAX_COLUMN_LABEL_CACHE_SIZE,
    ColumnLabelingValidationError,
    LiveColumnRoleLabeler,
    clear_column_label_cache,
    column_labeling_prompt,
    column_labeling_schema,
    line_item_roles,
    roles_from_payload,
)
from lib.extraction.text_lane.table_grid import TableGrid
from lib.model_runtime.contracts import TextGenerateRequest, TextGenerateResponse

FIXTURES = Path("tests/fixtures/text_lane")


def _grid(fixture_name: str = "service_lines_grid.json") -> TableGrid:
    payload = json.loads((FIXTURES / fixture_name).read_text())
    grid = TableGrid.from_parsed_table(
        ParsedTableText(
            table_id=uuid4(),
            page_number=payload["page_number"],
            table_index=payload["table_index"],
            table_json=payload["table_json"],
        )
    )
    assert grid is not None
    return grid


def _grid_with_headers(headers: tuple[str, ...]) -> TableGrid:
    rows = [
        [
            {
                "text": header,
                "start_row_offset_idx": 0,
                "start_col_offset_idx": col,
                "row_span": 1,
                "col_span": 1,
                "column_header": True,
            }
            for col, header in enumerate(headers)
        ],
        [
            {
                "text": value,
                "start_row_offset_idx": 1,
                "start_col_offset_idx": col,
                "row_span": 1,
                "col_span": 1,
            }
            for col, value in enumerate(("Sample service", "1", "12.00")[: len(headers)])
        ],
    ]
    grid = TableGrid.from_parsed_table(
        ParsedTableText(
            table_id=uuid4(),
            page_number=1,
            table_index=1,
            table_json={
                "data": {
                    "num_rows": 2,
                    "num_cols": len(headers),
                    "grid": rows,
                }
            },
        )
    )
    assert grid is not None
    return grid


@dataclass
class _FakeProfile:
    name: str = "qwen3-vl-8b-fp8-semantic:v1"


class _FakeTextClient:
    def __init__(self, roles_payload: dict[str, object]) -> None:
        self.profile = _FakeProfile()
        self.requests: list[TextGenerateRequest] = []
        self._roles_payload = roles_payload

    def generate(self, request: TextGenerateRequest) -> TextGenerateResponse:
        self.requests.append(request)
        return TextGenerateResponse(
            profile_name=request.profile_name,
            model_name="fake-qwen",
            model_version="test-1",
            source_engine="qwen3_vl_8b",
            prompt_version=request.prompt_version,
            raw_text=json.dumps(self._roles_payload),
            normalized_json=dict(self._roles_payload),
            prompt_sha256="0" * 64,
            latency_ms=1,
            structured_output_used=True,
        )


def test_line_item_roles_come_from_claim_registry() -> None:
    roles = line_item_roles("invoice")
    assert "description" in roles
    assert "amount" in roles
    assert "unit_price" in roles
    assert IGNORE_ROLE not in roles
    assert line_item_roles("unknown_family") == ()
    assert line_item_roles("medical_eob") == (
        "description",
        "code",
        "quantity",
        "gross_amount",
        "allowed_amount",
        "plan_paid",
        "amount",
        "service_date",
        "category_hint",
    )


def test_schema_is_strict_closed_enum() -> None:
    roles = line_item_roles("invoice")
    schema = column_labeling_schema(num_cols=3, roles=roles)
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["columns"]
    columns = schema["properties"]["columns"]
    assert columns["minItems"] == 3
    assert columns["maxItems"] == 3
    items = columns["items"]
    assert items["additionalProperties"] is False
    assert sorted(items["required"]) == ["column_index", "role"]
    assert items["properties"]["column_index"]["maximum"] == 2
    enum = items["properties"]["role"]["enum"]
    assert enum == [*roles, IGNORE_ROLE]


def test_prompt_contains_headers_samples_and_roles() -> None:
    grid = _grid()
    roles = line_item_roles("invoice")
    prompt = column_labeling_prompt(family="invoice", grid=grid, roles=roles)
    assert "column 0: DESCRIPTION OF SERVICE AND PARTS" in prompt
    assert "column 2: AMOUNT" in prompt
    assert "600 mile run-in service | 1 | 289.00" in prompt
    assert IGNORE_ROLE in prompt
    assert "invoice" in prompt
    # the totals row is part of the sample window (3 data rows max)
    assert "Balance due" in prompt


def test_labeler_caches_by_family_and_header_fingerprint() -> None:
    clear_column_label_cache()
    payload = {
        "columns": [
            {"column_index": 0, "role": "description"},
            {"column_index": 1, "role": "quantity"},
            {"column_index": 2, "role": "amount"},
        ]
    }
    client = _FakeTextClient(payload)
    labeler = LiveColumnRoleLabeler(client=client)  # type: ignore[arg-type]
    first = labeler.label_columns(family="invoice", grid=_grid())
    second = labeler.label_columns(family="invoice", grid=_grid())
    assert len(client.requests) == 1
    assert first.roles == {0: "description", 1: "quantity", 2: "amount"}
    assert not first.from_cache
    assert second.from_cache
    assert second.roles == first.roles
    # a different family re-labels even for the same header shape
    labeler.label_columns(family="service_record", grid=_grid())
    assert len(client.requests) == 2
    request = client.requests[0]
    assert request.temperature == 0.0
    assert request.seed == 0
    assert request.prompt_version == COLUMN_LABELING_PROMPT_VERSION
    assert request.response_json_schema is not None


def test_roles_from_payload_rejects_duplicate_column_indexes() -> None:
    with pytest.raises(ColumnLabelingValidationError, match="duplicate_column_index:0"):
        roles_from_payload(
            {
                "columns": [
                    {"column_index": 0, "role": "description"},
                    {"column_index": 0, "role": "amount"},
                    {"column_index": 2, "role": "amount"},
                ]
            },
            num_cols=3,
        )


def test_roles_from_payload_rejects_missing_column_indexes() -> None:
    with pytest.raises(ColumnLabelingValidationError, match="missing_column_index:2"):
        roles_from_payload(
            {
                "columns": [
                    {"column_index": 0, "role": "description"},
                    {"column_index": 1, "role": "quantity"},
                ]
            },
            num_cols=3,
        )


def test_roles_from_payload_requires_well_formed_column_entries() -> None:
    with pytest.raises(ColumnLabelingValidationError, match="invalid_column_entry"):
        roles_from_payload(
            {"columns": ["not-an-object"]},
            num_cols=1,
        )


def test_labeler_cache_separates_model_profiles() -> None:
    clear_column_label_cache()
    payload = {
        "columns": [
            {"column_index": 0, "role": "description"},
            {"column_index": 1, "role": "quantity"},
            {"column_index": 2, "role": "amount"},
        ]
    }
    first_client = _FakeTextClient(payload)
    second_client = _FakeTextClient(payload)
    second_client.profile = _FakeProfile(name="qwen3-vl-8b-fp8-semantic:v2")

    first = LiveColumnRoleLabeler(client=first_client)  # type: ignore[arg-type]
    second = LiveColumnRoleLabeler(client=second_client)  # type: ignore[arg-type]
    first_result = first.label_columns(family="invoice", grid=_grid())
    second_result = second.label_columns(family="invoice", grid=_grid())

    assert not first_result.from_cache
    assert not second_result.from_cache
    assert len(first_client.requests) == 1
    assert len(second_client.requests) == 1


def test_labeler_cache_evicts_oldest_entries() -> None:
    clear_column_label_cache()
    payload = {
        "columns": [
            {"column_index": 0, "role": "description"},
            {"column_index": 1, "role": "quantity"},
            {"column_index": 2, "role": "amount"},
        ]
    }
    client = _FakeTextClient(payload)
    labeler = LiveColumnRoleLabeler(client=client)  # type: ignore[arg-type]
    grids = [
        _grid_with_headers((f"Description {index}", "Quantity", "Amount"))
        for index in range(MAX_COLUMN_LABEL_CACHE_SIZE + 1)
    ]

    first = labeler.label_columns(family="invoice", grid=grids[0])
    for grid in grids[1:]:
        labeler.label_columns(family="invoice", grid=grid)
    replay = labeler.label_columns(family="invoice", grid=grids[0])

    assert not first.from_cache
    assert not replay.from_cache
    assert len(client.requests) == MAX_COLUMN_LABEL_CACHE_SIZE + 2
