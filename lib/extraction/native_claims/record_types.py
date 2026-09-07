"""Explicit native interpretation versions; old recorded-text semantics stay intact."""

from typing import Any

from lib.extraction.native_claims.model_emission.models import NativeModelEmissionConfiguration
from lib.extraction.native_claims.models import NativeClaimConfiguration

NativeConfiguration = NativeClaimConfiguration | NativeModelEmissionConfiguration


def decode_configuration(payload: Any) -> NativeConfiguration:
    if isinstance(payload, (NativeClaimConfiguration, NativeModelEmissionConfiguration)):
        payload = payload.model_dump(mode="json")
    if not isinstance(payload, dict):
        raise ValueError("Native claim configuration version is unavailable.")
    version = payload.get("schema_version")
    if version == "native_claim_configuration.v1":
        return NativeClaimConfiguration.model_validate(payload)
    if version == "native_model_emission_configuration.v1":
        return NativeModelEmissionConfiguration.model_validate(payload)
    raise ValueError("Native claim configuration version is unsupported.")
