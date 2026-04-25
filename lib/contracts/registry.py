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

    @classmethod
    def from_settings(cls, settings: Settings) -> ContractRegistry:
        return cls.load(settings.contracts_dir)

    @classmethod
    def load(cls, root: str | Path) -> ContractRegistry:
        contracts_root = Path(root)
        openapi_path = contracts_root / "api" / "openapi.yaml"
        schemas_dir = contracts_root / "schemas"
        events_dir = contracts_root / "events"

        if not openapi_path.exists():
            raise FileNotFoundError(f"OpenAPI contract not found: {openapi_path}")
        if not schemas_dir.exists():
            raise FileNotFoundError(f"Schema directory not found: {schemas_dir}")
        if not events_dir.exists():
            raise FileNotFoundError(f"Event directory not found: {events_dir}")

        openapi = yaml.safe_load(openapi_path.read_text(encoding="utf-8"))
        schemas = {
            path.name: json.loads(path.read_text(encoding="utf-8"))
            for path in sorted(schemas_dir.glob("*.json"))
        }
        events = {
            path.name: json.loads(path.read_text(encoding="utf-8"))
            for path in sorted(events_dir.glob("*.json"))
        }

        return cls(root=contracts_root, openapi=openapi, schemas=schemas, events=events)

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
            "schemas": sorted(self.schemas),
            "events": sorted(self.events),
        }
