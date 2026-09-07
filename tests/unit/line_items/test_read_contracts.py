import base64
import json
from pathlib import Path
from unittest.mock import Mock

import pytest
import yaml

from lib.contracts.line_item_authority import (
    CanonicalLineResponse,
    LineCandidateResponse,
    LineDecisionResponse,
    LineHistoryResponse,
)
from lib.review.line_items import read_budget
from lib.review.line_items.history_read import _decode_cursor


@pytest.mark.parametrize(
    "cls", [CanonicalLineResponse, LineCandidateResponse, LineDecisionResponse, LineHistoryResponse]
)
def test_openapi_read_dto_has_exact_declared_shapes(cls):
    schemas = yaml.safe_load(Path("contracts/api/openapi.yaml").read_text())["components"][
        "schemas"
    ]
    schema = cls.model_json_schema(
        mode="serialization", by_alias=True, ref_template="#/components/schemas/{model}"
    )
    definitions = schema.pop("$defs", {})
    assert schemas[cls.__name__] == schema
    for name, definition in definitions.items():
        assert schemas[name] == definition, name


@pytest.mark.parametrize("component", [None, True, 3, {}, []])
def test_opaque_history_cursor_cannot_throw_from_untyped_uuid_component(component):
    cursor = base64.urlsafe_b64encode(
        json.dumps(["scope", "2026-09-07T00:00:00+00:00", component]).encode()
    ).decode()
    with pytest.raises(ValueError, match="Invalid line history cursor"):
        _decode_cursor(cursor, "scope")


def test_read_budget_stops_issuing_queries_after_deadline(monkeypatch):
    sql = Mock()
    cursor = read_budget.LineReadCursor(sql, 20)
    monkeypatch.setattr(read_budget, "monotonic", lambda: 21)
    with pytest.raises(TimeoutError):
        cursor.execute("SELECT 1")
    sql.execute.assert_not_called()
