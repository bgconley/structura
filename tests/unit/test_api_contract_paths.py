from __future__ import annotations

from pathlib import Path

import yaml

from apps.api.structura_api.main import app


def test_runtime_openapi_paths_match_active_contract() -> None:
    contract = yaml.safe_load(Path("contracts/api/openapi.yaml").read_text(encoding="utf-8"))

    assert sorted(app.openapi()["paths"]) == sorted(contract["paths"])


def test_phase6_placeholder_response_statuses_match_active_contract() -> None:
    contract = yaml.safe_load(Path("contracts/api/openapi.yaml").read_text(encoding="utf-8"))
    runtime_paths = app.openapi()["paths"]
    placeholders = [
        ("/api/v1/contacts", "post"),
        ("/api/v1/filing-rules", "post"),
        ("/api/v1/watched-folders", "post"),
    ]

    for path, method in placeholders:
        expected = sorted(contract["paths"][path][method].get("responses", {}))
        actual = sorted(runtime_paths[path][method].get("responses", {}))
        assert actual == expected, f"{method.upper()} {path} response status drift"


def test_phase0_contract_skeleton_routes_are_protected() -> None:
    protected_paths = [
        "/api/v1/documents",
        "/api/v1/documents/00000000-0000-0000-0000-000000000000",
        "/api/v1/assets/00000000-0000-0000-0000-000000000000",
        "/api/v1/folders",
        "/api/v1/tags",
        "/api/v1/relationships",
        "/api/v1/contacts",
        "/api/v1/filing-rules",
        "/api/v1/watched-folders",
        "/api/v1/review-tasks",
        "/api/v1/admin/jobs",
    ]

    from fastapi.testclient import TestClient

    client = TestClient(app)
    for path in protected_paths:
        assert client.get(path).status_code == 401
