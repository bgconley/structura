from dataclasses import replace

import pytest

from lib.extraction.native_claims.errors import NativeClaimConflict
from lib.extraction.native_claims.model_emission import configuration
from lib.extraction.native_claims.model_emission.read_compatibility import (
    require_readable_configuration,
)


def test_write_implementation_drift_is_rejected_but_retained_versions_remain_readable():
    original = configuration.installed_configuration()
    header = {"configuration_json": original.model_dump(mode="json")}
    changed = original.model_copy(update={"implementation_sha256": "f" * 64})
    with pytest.raises(NativeClaimConflict, match="unsupported"):
        configuration.require_supported_configuration(header, changed)
    assert configuration.require_supported_configuration(header, original) == original
    historical = {"configuration_json": changed.model_dump(mode="json")}
    assert require_readable_configuration(historical) == changed


@pytest.mark.parametrize(
    "part", ["importer_version", "review_policy_version", "typing_version", "typing_sha256"]
)
def test_read_dispatch_rejects_unsupported_contract_versions(part):
    payload = configuration.installed_configuration().model_dump(mode="json")
    if part in {"typing_version", "typing_sha256"}:
        payload["definitions"][part] = "f" * 64
    else:
        payload[part] = "unsupported-version"
    with pytest.raises((ValueError, NativeClaimConflict)):
        require_readable_configuration({"configuration_json": payload})


def test_diagnostic_validation_implementation_is_captured_in_header(monkeypatch):
    first = configuration.installed_configuration()
    actual = configuration.frozen_definitions()
    monkeypatch.setattr(
        configuration, "frozen_definitions", lambda: replace(actual, validation_sha256="f" * 64)
    )
    changed = configuration.installed_configuration()
    assert first.implementation_sha256 == changed.implementation_sha256
    assert first.fingerprint != changed.fingerprint
