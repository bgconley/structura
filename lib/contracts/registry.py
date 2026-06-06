from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Any, cast

import yaml
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from lib.config import Settings


@dataclass(frozen=True)
class ContractRegistry:
    root: Path
    openapi: dict[str, Any]
    schemas: dict[str, dict[str, Any]]
    events: dict[str, dict[str, Any]]
    model_outputs: dict[str, dict[str, Any]]

    @classmethod
    def from_settings(cls, settings: Settings) -> ContractRegistry:
        return cls.load(settings.contracts_dir)

    @classmethod
    def load(cls, root: str | Path) -> ContractRegistry:
        contracts_root = Path(root)
        openapi_path = contracts_root / "api" / "openapi.yaml"
        schemas_dir = contracts_root / "schemas"
        events_dir = contracts_root / "events"
        model_outputs_dir = contracts_root / "model_outputs"

        if not openapi_path.exists():
            raise FileNotFoundError(f"OpenAPI contract not found: {openapi_path}")
        if not schemas_dir.exists():
            raise FileNotFoundError(f"Schema directory not found: {schemas_dir}")
        if not events_dir.exists():
            raise FileNotFoundError(f"Event directory not found: {events_dir}")
        if not model_outputs_dir.exists():
            raise FileNotFoundError(f"Model-output schema directory not found: {model_outputs_dir}")

        openapi = yaml.safe_load(openapi_path.read_text(encoding="utf-8"))
        schemas = {
            path.name: json.loads(path.read_text(encoding="utf-8"))
            for path in sorted(schemas_dir.glob("*.json"))
        }
        events = {
            path.name: json.loads(path.read_text(encoding="utf-8"))
            for path in sorted(events_dir.glob("*.json"))
        }
        model_outputs = {
            path.name: json.loads(path.read_text(encoding="utf-8"))
            for path in sorted(model_outputs_dir.glob("*.schema.json"))
        }

        return cls(
            root=contracts_root,
            openapi=openapi,
            schemas=schemas,
            events=events,
            model_outputs=model_outputs,
        )

    def check_json_schemas(self) -> None:
        for name, schema in self.schemas.items():
            try:
                Draft202012Validator.check_schema(schema)
            except Exception as exc:  # pragma: no cover - exception text is what matters
                raise ValueError(f"Invalid JSON Schema {name}: {exc}") from exc
        for name, schema in self.events.items():
            try:
                Draft202012Validator.check_schema(schema)
            except Exception as exc:  # pragma: no cover
                raise ValueError(f"Invalid event schema {name}: {exc}") from exc
        for name, schema in self.model_outputs.items():
            try:
                Draft202012Validator.check_schema(schema)
            except Exception as exc:  # pragma: no cover
                raise ValueError(f"Invalid model-output JSON Schema {name}: {exc}") from exc

    def check_model_output_structured_schemas(self) -> None:
        for name, schema in self.model_outputs.items():
            _check_structured_output_schema(name=name, schema=schema)

    @cached_property
    def _schema_registry(self) -> Registry:
        return cast(
            Registry[Any],
            Registry().with_resources(
                (
                    name,
                    Resource.from_contents(schema, default_specification=DRAFT202012),
                )
                for name, schema in {**self.schemas, **self.events}.items()
            ),
        )

    @cached_property
    def _openapi_registry(self) -> Registry:
        return cast(
            Registry[Any],
            Registry().with_resource(
                "openapi.yaml",
                Resource.from_contents(self.openapi, default_specification=DRAFT202012),
            ),
        )

    def validate_schema_instance(self, name: str, payload: dict[str, Any]) -> None:
        schema = self.schemas[name]
        Draft202012Validator(
            schema,
            registry=self._schema_registry,
            format_checker=Draft202012Validator.FORMAT_CHECKER,
        ).validate(payload)

    def validate_event_instance(self, name: str, payload: dict[str, Any]) -> None:
        schema = self.events[name]
        Draft202012Validator(
            schema,
            registry=self._schema_registry,
            format_checker=Draft202012Validator.FORMAT_CHECKER,
        ).validate(payload)

    def validate_openapi_component(self, name: str, payload: dict[str, Any]) -> None:
        schema = {"$ref": f"openapi.yaml#/components/schemas/{name}"}
        Draft202012Validator(
            schema,
            registry=self._openapi_registry,
            format_checker=Draft202012Validator.FORMAT_CHECKER,
        ).validate(payload)

    def summary(self) -> dict[str, object]:
        paths = self.openapi.get("paths", {})
        return {
            "root": str(self.root),
            "openapi_title": self.openapi.get("info", {}).get("title"),
            "openapi_version": self.openapi.get("info", {}).get("version"),
            "path_count": len(paths),
            "schema_count": len(self.schemas),
            "event_schema_count": len(self.events),
            "model_output_schema_count": len(self.model_outputs),
            "schemas": sorted(self.schemas),
            "events": sorted(self.events),
            "model_outputs": sorted(self.model_outputs),
        }


def _check_structured_output_schema(
    *,
    name: str,
    schema: dict[str, Any],
) -> None:
    _check_structured_output_root(name=name, schema=schema)
    for path, node in _schema_nodes(schema, path="$"):
        node_type = node.get("type")
        node_types = set(node_type) if isinstance(node_type, list) else {node_type}
        if "object" not in node_types:
            continue
        if node.get("additionalProperties") is not False:
            raise ValueError(
                f"Model-output structured schema {name} has open object at {path}; "
                "set additionalProperties to false."
            )
        _check_structured_output_object_required_keys(name=name, path=path, node=node)


def _check_structured_output_root(*, name: str, schema: dict[str, Any]) -> None:
    required = schema.get("required")
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        raise ValueError(f"Model-output structured schema {name} must declare properties.")
    if not isinstance(required, list):
        raise ValueError(f"Model-output structured schema {name} must declare root required keys.")
    if not any(key != "confidence" for key in required):
        raise ValueError(
            f"Model-output structured schema {name} must require at least one "
            "extraction-bearing root key."
        )
    unknown = sorted(key for key in required if key not in properties)
    if unknown:
        raise ValueError(
            f"Model-output structured schema {name} requires unknown root keys: {unknown}."
        )


def _check_structured_output_object_required_keys(
    *,
    name: str,
    path: str,
    node: dict[str, Any],
) -> None:
    properties = node.get("properties")
    required = node.get("required")
    if not isinstance(properties, dict):
        raise ValueError(
            f"Model-output structured schema {name} object at {path} must declare properties."
        )
    if not isinstance(required, list):
        raise ValueError(
            f"Model-output structured schema {name} object at {path} must declare required keys."
        )
    property_names = set(properties)
    required_names = set(required)
    missing = sorted(property_names - required_names)
    if missing:
        raise ValueError(
            f"Model-output structured schema {name} object at {path} must require every "
            f"declared object property; missing: {missing}."
        )
    unknown = sorted(required_names - property_names)
    if unknown:
        raise ValueError(
            f"Model-output structured schema {name} object at {path} requires unknown keys: "
            f"{unknown}."
        )


def _schema_nodes(schema: Any, *, path: str) -> list[tuple[str, dict[str, Any]]]:
    if not isinstance(schema, dict):
        return []
    nodes = [(path, schema)]
    properties = schema.get("properties")
    if isinstance(properties, dict):
        for key, child in properties.items():
            nodes.extend(_schema_nodes(child, path=f"{path}.properties.{key}"))
    items = schema.get("items")
    if isinstance(items, dict):
        nodes.extend(_schema_nodes(items, path=f"{path}.items"))
    for keyword in ("anyOf", "oneOf", "allOf"):
        variants = schema.get(keyword)
        if isinstance(variants, list):
            for index, child in enumerate(variants):
                nodes.extend(_schema_nodes(child, path=f"{path}.{keyword}[{index}]"))
    return nodes
