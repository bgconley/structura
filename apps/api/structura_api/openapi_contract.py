from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

HTTP_METHODS = {"delete", "get", "patch", "post", "put"}


def install_contract_aligned_openapi(app: FastAPI, *, contracts_dir: Path) -> None:
    contract_path = contracts_dir / "api" / "openapi.yaml"

    def custom_openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title,
            version=app.version,
            openapi_version=app.openapi_version,
            summary=app.summary,
            description=app.description,
            routes=app.routes,
        )
        _overlay_contract_sections(schema, contract_path)
        app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = custom_openapi  # type: ignore[method-assign]


def _overlay_contract_sections(schema: dict[str, Any], contract_path: Path) -> None:
    contract = yaml.safe_load(contract_path.read_text(encoding="utf-8"))
    contract_components = contract.get("components")
    if isinstance(contract_components, dict):
        schema_components = schema.setdefault("components", {})
        if isinstance(schema_components, dict):
            for key, value in contract_components.items():
                if isinstance(value, dict):
                    existing = schema_components.setdefault(key, {})
                    if isinstance(existing, dict):
                        existing.update(value)
                    else:
                        schema_components[key] = value
                else:
                    schema_components[key] = value
    runtime_paths = schema.get("paths", {})
    for path, contract_path_item in contract.get("paths", {}).items():
        runtime_path_item = runtime_paths.get(path)
        if not isinstance(runtime_path_item, dict) or not isinstance(contract_path_item, dict):
            continue
        for method, contract_operation in contract_path_item.items():
            if method not in HTTP_METHODS:
                continue
            runtime_operation = runtime_path_item.get(method)
            if not isinstance(runtime_operation, dict) or not isinstance(contract_operation, dict):
                continue
            runtime_operation["responses"] = contract_operation.get("responses", {})
