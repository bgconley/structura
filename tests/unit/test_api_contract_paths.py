from __future__ import annotations

from pathlib import Path

import yaml

from apps.api.structura_api.main import app


def test_runtime_openapi_paths_match_active_contract() -> None:
    contract = yaml.safe_load(Path("contracts/api/openapi.yaml").read_text(encoding="utf-8"))

    assert sorted(app.openapi()["paths"]) == sorted(contract["paths"])


def test_phase6_runtime_response_statuses_match_active_contract() -> None:
    contract = yaml.safe_load(Path("contracts/api/openapi.yaml").read_text(encoding="utf-8"))
    runtime_paths = app.openapi()["paths"]
    phase6_mutations = [
        ("/api/v1/contacts", "post"),
        ("/api/v1/filing-rules", "post"),
        ("/api/v1/filing-rules/{ruleId}/dry-run", "post"),
        ("/api/v1/filing-rules/{ruleId}/apply", "post"),
        ("/api/v1/filing-suggestions/{runId}/accept", "post"),
        ("/api/v1/filing-suggestions/{runId}/reject", "post"),
        ("/api/v1/filing-suggestions/{runId}/defer", "post"),
        ("/api/v1/watched-folders", "post"),
        ("/api/v1/documents/{documentId}/contacts", "post"),
    ]

    for path, method in phase6_mutations:
        expected = sorted(contract["paths"][path][method].get("responses", {}))
        actual = sorted(runtime_paths[path][method].get("responses", {}))
        assert actual == expected, f"{method.upper()} {path} response status drift"


def test_phase7_runtime_response_statuses_match_active_contract() -> None:
    contract = yaml.safe_load(Path("contracts/api/openapi.yaml").read_text(encoding="utf-8"))
    runtime_paths = app.openapi()["paths"]
    phase7_routes = [
        ("/api/v1/relationships", "post"),
        ("/api/v1/relationships/{relationshipId}/accept", "post"),
        ("/api/v1/relationships/{relationshipId}/reject", "post"),
        ("/api/v1/timeline", "get"),
        ("/api/v1/deadlines", "get"),
        ("/api/v1/smart-views", "get"),
    ]

    for path, method in phase7_routes:
        expected = sorted(contract["paths"][path][method].get("responses", {}))
        actual = sorted(runtime_paths[path][method].get("responses", {}))
        assert actual == expected, f"{method.upper()} {path} response status drift"


def test_deferred_placeholder_mutations_advertise_runtime_501_contract() -> None:
    contract = yaml.safe_load(Path("contracts/api/openapi.yaml").read_text(encoding="utf-8"))
    runtime_paths = app.openapi()["paths"]
    placeholders = [
        ("/api/v1/analysis-notes", "post", {"202"}),
        ("/api/v1/exports", "post", {"202"}),
    ]

    for path, method, success_codes in placeholders:
        expected = set(contract["paths"][path][method].get("responses", {}))
        actual = set(runtime_paths[path][method].get("responses", {}))
        assert "501" in expected, f"{method.upper()} {path} must advertise deferred runtime status"
        assert expected.isdisjoint(success_codes), (
            f"{method.upper()} {path} must not advertise success before implementation"
        )
        assert actual == expected, f"{method.upper()} {path} response status drift"


def test_phase0_contract_skeleton_routes_are_protected() -> None:
    protected_paths = [
        "/api/v1/documents",
        "/api/v1/documents/00000000-0000-0000-0000-000000000000",
        "/api/v1/assets/00000000-0000-0000-0000-000000000000",
        "/api/v1/folders",
        "/api/v1/tags",
        "/api/v1/relationships",
        "/api/v1/deadlines",
        "/api/v1/timeline",
        "/api/v1/smart-views",
        "/api/v1/contacts",
        "/api/v1/contact-merge-suggestions",
        "/api/v1/filing-rules",
        "/api/v1/filing-suggestions",
        "/api/v1/import-status",
        "/api/v1/watched-folders",
        "/api/v1/review-tasks",
        "/api/v1/admin/jobs",
    ]

    from fastapi.testclient import TestClient

    client = TestClient(app)
    for path in protected_paths:
        assert client.get(path).status_code == 401
