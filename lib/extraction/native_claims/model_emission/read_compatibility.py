"""Explicit retained contract support, independent of current implementation bytes."""

from lib.extraction.native_claims.errors import NativeClaimConflict
from lib.extraction.native_claims.model_emission.models import NativeModelEmissionConfiguration

# These are the supported 106 raw-member-import-v1 contract definitions. Future
# readers must add explicit dispatch, not replace historical validators in place.
_V1_DEFINITIONS = (
    "8a1630253a3026a288ce18e1a68c7f913391f37da05c3b48e96013810ef18a45",
    "81b4248651ec70ebbf8d2cb31f16d37f414027ad0838a5cf335cd6ffbe94790d",
    "1fa55014eaa4b15130acf4d1fd00d59783e4c249041a4ac2ffb7059fe550f2e3",
    "e1fb29f85b6a34725fb6963fe53695c9e5ac7a4d53657714080b8627c2f1949c",
    "1c6421f8575cc50bf504e29a8ac4a99d32ba77377cc1ad6e79bc45467a05cb16",
)


def require_readable_configuration(header):
    # Literal versions in this DTO reject unsupported importer/schema/review policy.
    configuration = NativeModelEmissionConfiguration.model_validate(header["configuration_json"])
    definitions = configuration.definitions
    versions = (
        definitions.taxonomy_version,
        definitions.registry_version,
        definitions.typing_version,
    )
    if (
        versions
        != ("page-family-taxonomy-v2", "page-claim-obligations-v2", "page-proposed-value-typing-v2")
        or (
            definitions.schema_sha256,
            definitions.taxonomy_sha256,
            definitions.registry_sha256,
            definitions.typing_sha256,
            definitions.validation_sha256,
        )
        != _V1_DEFINITIONS
    ):
        raise NativeClaimConflict("Retained native model contract is unsupported.")
    return configuration
