from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.api.structura_api import routes_generation_evidence as routes
from apps.api.structura_api.dependencies import require_document_read
from lib.auth import AuthPrincipal
from lib.evidence.models import GenerationEvidenceManifest, GenerationEvidencePage
from lib.evidence.read_service import GenerationEvidenceReader
from lib.evidence.render_execution import retain_source_pages


def test_generation_routes_return_exact_content_and_private_same_snapshot_bytes(
    retained, monkeypatch
):
    harness, writer = retained
    retain_source_pages(harness.binding, storage=harness.storage, service=writer)
    monkeypatch.setattr(
        "lib.evidence.read_service.read_generation", lambda *a, **k: writer.read_row(**k)
    )
    principal = AuthPrincipal(
        user_id=uuid4(),
        household_id=uuid4(),
        email="reader@example.com",
        display_name="Reader",
        auth_method="session",
        household_role="owner",
    )
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[require_document_read] = lambda: principal
    app.dependency_overrides[routes._reader] = lambda: GenerationEvidenceReader(harness.storage)
    base = (
        f"/api/v1/documents/{harness.binding.document_id}/parse-generations/"
        f"{harness.binding.parse_generation_id}"
    )
    with TestClient(app) as client:
        manifest = client.get(base, params={"offset": 1, "limit": 1})
        assert manifest.status_code == 200 and manifest.json()["pages"][0]["pageNumber"] == 2
        assert "isCurrent" not in manifest.json()
        page = client.get(base + "/pages/2")
        assert page.status_code == 200 and page.json()["page"]["id"] == str(
            harness.service.structure.pages[1].id
        )
        response = client.get(base + "/pages/2/render")
        expected = harness.storage.path_for_uri(writer.assets[1].uri).read_bytes()
        assert response.content == expected
        assert response.headers["content-length"] == str(len(expected))
        assert response.headers["cache-control"] == "private, no-store"
        assert response.headers["content-type"] == "image/png"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert client.get(base, params={"limit": 101}).status_code == 422


def test_distinct_openapi_generation_components_match_runtime_dtos():
    source = yaml.safe_load(Path("contracts/api/openapi.yaml").read_text())
    schemas = {}
    for model in (GenerationEvidenceManifest, GenerationEvidencePage):
        schema = model.model_json_schema(by_alias=True)
        schemas.update(schema.pop("$defs", {}))
        schemas[model.__name__] = schema
    names = {
        name: name if name.startswith("GenerationEvidence") else "GenerationEvidence" + name
        for name in schemas
    }

    def refs(value):
        if isinstance(value, dict):
            return {
                k: ("#/components/schemas/" + names[v.split("/")[-1]] if k == "$ref" else refs(v))
                for k, v in value.items()
            }
        if isinstance(value, list):
            return [refs(v) for v in value]
        return value

    for name, schema in schemas.items():
        assert source["components"]["schemas"][names[name]] == refs(schema)


def test_transport_failure_before_first_chunk_closes_verified_spool(tmp_path):
    import asyncio

    import pytest
    from starlette.requests import ClientDisconnect

    from lib.evidence.media import snapshot_render
    from tests.unit.evidence.test_media import source_fixture

    storage, _, asset, _ = source_fixture(tmp_path)
    verified = snapshot_render(asset, storage)
    response = routes.VerifiedRenderResponse(verified)

    async def disconnected(message):
        raise OSError("Controlled disconnected client")

    async def receive():
        return {"type": "http.disconnect"}

    with pytest.raises(ClientDisconnect):
        asyncio.run(
            response({"type": "http", "asgi": {"spec_version": "2.4"}}, receive, disconnected)
        )
    assert verified.stream.closed
