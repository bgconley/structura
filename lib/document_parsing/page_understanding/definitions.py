"""Installed-definition fingerprints for a future versioned adapter configuration.

Filesystem reads are confined to this definition adapter; DTO/validation/decoding
remain pure. Hashes describe actual installed schema, data and typing source.
"""

import hashlib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from lib.document_parsing.page_understanding.claims import TYPING_VERSION
from lib.document_parsing.page_understanding.codec import canonical_digest
from lib.document_parsing.page_understanding.model import OUTPUT_VERSION, PageUnderstanding
from lib.document_parsing.page_understanding.registry import FIELD_RULES, REGISTRY_VERSION
from lib.document_parsing.page_understanding.taxonomy import FAMILIES, TAXONOMY_VERSION


@dataclass(frozen=True)
class DefinitionManifest:
    output_version: str
    taxonomy_version: str
    registry_version: str
    typing_version: str
    schema_sha256: str
    taxonomy_sha256: str
    registry_sha256: str
    typing_sha256: str
    validation_sha256: str


def model_output_schema() -> dict[str, Any]:
    return PageUnderstanding.model_json_schema(mode="validation")


def installed_definitions() -> DefinitionManifest:
    directory = Path(__file__).resolve().parent
    implementations = {
        name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
        for name in (
            "base.py",
            "claims.py",
            "classification.py",
            "codec.py",
            "coverage.py",
            "coverage_validation.py",
            "interpretation.py",
            "locators.py",
            "model.py",
            "registry.py",
            "structure.py",
            "taxonomy.py",
        )
    }
    return DefinitionManifest(
        OUTPUT_VERSION,
        TAXONOMY_VERSION,
        REGISTRY_VERSION,
        TYPING_VERSION,
        canonical_digest(model_output_schema()),
        canonical_digest({"version": TAXONOMY_VERSION, "families": FAMILIES}),
        canonical_digest({"version": REGISTRY_VERSION, "fields": [asdict(r) for r in FIELD_RULES]}),
        canonical_digest(
            {"version": TYPING_VERSION, "implementation": implementations["claims.py"]}
        ),
        canonical_digest(implementations),
    )


# Filled and reviewed with the generated artifact at this contract checkpoint.
FROZEN_HASHES: tuple[str, ...] = (
    "8a1630253a3026a288ce18e1a68c7f913391f37da05c3b48e96013810ef18a45",
    "81b4248651ec70ebbf8d2cb31f16d37f414027ad0838a5cf335cd6ffbe94790d",
    "1fa55014eaa4b15130acf4d1fd00d59783e4c249041a4ac2ffb7059fe550f2e3",
    "e1fb29f85b6a34725fb6963fe53695c9e5ac7a4d53657714080b8627c2f1949c",
    "1c6421f8575cc50bf504e29a8ac4a99d32ba77377cc1ad6e79bc45467a05cb16",
)


def frozen_definitions() -> DefinitionManifest:
    actual = installed_definitions()
    hashes = (
        actual.schema_sha256,
        actual.taxonomy_sha256,
        actual.registry_sha256,
        actual.typing_sha256,
        actual.validation_sha256,
    )
    if hashes != FROZEN_HASHES:
        raise ValueError(
            "Installed page-understanding definitions do not match the frozen contract."
        )
    return actual
