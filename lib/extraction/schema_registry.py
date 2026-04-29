from __future__ import annotations

from typing import Any

from jsonschema.exceptions import ValidationError

from lib.config import get_settings
from lib.contracts import ContractRegistry

EXTRACTION_SCHEMA_FILES = {
    "document_classification": "document_classification.v1.schema.json",
    "receipt": "receipt.v1.schema.json",
    "invoice": "invoice.v1.schema.json",
    "medical_eob": "medical_eob.v1.schema.json",
    "document_observation": "document_observation.v1.schema.json",
}


class ExtractionSchemaError(Exception):
    pass


class ExtractionSchemaRegistry:
    def __init__(self, registry: ContractRegistry | None = None) -> None:
        self.registry = registry or ContractRegistry.from_settings(get_settings())

    def validate(self, schema_name: str, payload: dict[str, Any]) -> None:
        schema_file = EXTRACTION_SCHEMA_FILES.get(schema_name)
        if not schema_file:
            raise ExtractionSchemaError(f"Unsupported extraction schema: {schema_name}")
        try:
            self.registry.validate_schema_instance(schema_file, payload)
        except ValidationError as exc:
            raise ExtractionSchemaError(exc.message) from exc

    def validate_event(self, event_name: str, payload: dict[str, Any]) -> None:
        try:
            self.registry.validate_event_instance(event_name, payload)
        except ValidationError as exc:
            raise ExtractionSchemaError(exc.message) from exc
