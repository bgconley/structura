import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from lib.document_parsing.page_understanding import definitions
from lib.document_parsing.page_understanding.codec import (
    canonical_digest,
    decode_page_understanding,
)
from lib.document_parsing.page_understanding.model import PageUnderstanding
from tests.fixtures.page_understanding_sources import invoice_page, prose_page


def test_published_schema_exactly_matches_frozen_installed_contract():
    path = (
        Path(__file__).resolve().parents[4]
        / "contracts/model_outputs/structura_page_understanding.v2.schema.json"
    )
    published = json.loads(path.read_text())
    assert published == definitions.model_output_schema() == PageUnderstanding.model_json_schema()
    Draft202012Validator.check_schema(published)
    validator = Draft202012Validator(published)
    validator.validate(invoice_page())
    validator.validate(prose_page())
    manifest = definitions.frozen_definitions()
    assert canonical_digest(published) == manifest.schema_sha256
    assert len(published["$defs"]["CanonicalKey"]["enum"]) == 109
    assert len(manifest.taxonomy_sha256) == len(manifest.typing_sha256) == 64


def test_definition_drift_fails_before_a_config_can_claim_the_old_contract(monkeypatch):
    original = definitions.installed_definitions()
    monkeypatch.setattr(
        definitions, "installed_definitions", lambda: replace(original, typing_sha256="0" * 64)
    )
    with pytest.raises(ValueError, match="frozen contract"):
        definitions.frozen_definitions()


def test_registry_validation_code_is_frozen_even_if_field_data_has_not_changed(monkeypatch):
    original = definitions.installed_definitions()
    read_bytes = Path.read_bytes

    def changed_registry(path):
        content = read_bytes(path)
        return (
            content + b"\n# Changed registry validation.\n"
            if path.name == "registry.py"
            else content
        )

    monkeypatch.setattr(Path, "read_bytes", changed_registry)
    changed = definitions.installed_definitions()
    assert changed.registry_sha256 == original.registry_sha256
    assert changed.validation_sha256 != original.validation_sha256
    with pytest.raises(ValueError, match="frozen contract"):
        definitions.frozen_definitions()


def test_fingerprint_encoding_is_explicit_literal_utf8_not_ascii_escaped():
    value = {"s": "é"}
    assert canonical_digest(value) == hashlib.sha256(b'{"s":"\xc3\xa9"}').hexdigest()
    ascii_digest = hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    assert canonical_digest(value) != ascii_digest


def test_v1_is_not_silently_interpreted_as_combined_v2():
    old = {
        key: value
        for key, value in invoice_page().items()
        if key not in {"schema_version", "classification", "extraction"}
    }
    with pytest.raises(ValueError):
        decode_page_understanding(json.dumps(old))
