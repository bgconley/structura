"""Installed importer identity, resolved before entering database transactions."""

import hashlib
from dataclasses import asdict
from pathlib import Path

from lib.document_parsing.page_understanding.codec import canonical_digest
from lib.document_parsing.page_understanding.definitions import frozen_definitions
from lib.document_processing.configuration_types import UnderstandingDefinitions
from lib.extraction.native_claims.errors import NativeClaimConflict
from lib.extraction.native_claims.model_emission.models import NativeModelEmissionConfiguration


def installed_configuration() -> NativeModelEmissionConfiguration:
    directory = Path(__file__).resolve().parent
    return NativeModelEmissionConfiguration(
        definitions=UnderstandingDefinitions.model_validate(asdict(frozen_definitions())),
        implementation_sha256=canonical_digest(
            {
                name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
                for name in (
                    "models.py",
                    "page_models.py",
                    "anchors.py",
                    "identity.py",
                    "import_page.py",
                    "projection.py",
                    "page_evidence.py",
                    "read_validation.py",
                    "retained_products.py",
                )
            }
        ),
    )


def require_supported_configuration(header, implementation: NativeModelEmissionConfiguration):
    """Only the captured implementation may append or seal an existing building set.

    The service resolves installed bytes before taking any database locks. A future
    importer must not silently append new typing/anchor rules under an old header's
    fingerprint. Retained reads instead use explicit read_compatibility dispatch.
    """
    stored = NativeModelEmissionConfiguration.model_validate(header["configuration_json"])
    if stored != implementation:
        raise NativeClaimConflict("Native model importer configuration is unsupported.")
    return stored
