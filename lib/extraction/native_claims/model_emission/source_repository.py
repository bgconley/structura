"""Load only persisted exact v2 page inputs after the caller locks source lineage."""

from typing import Any

from lib.document_parsing.invocations import decode_parse_invocation
from lib.document_parsing.qwen_page_parser import ParsedSourcePage
from lib.document_parsing.structure import StructurePage
from lib.document_processing.configuration_types import (
    ParseConfigurationV2,
    decode_parse_configuration,
)
from lib.extraction.native_claims.errors import NativeClaimError
from lib.extraction.native_claims.model_emission.models import NativeModelEmissionConfiguration
from lib.extraction.native_claims.models import NativeClaimBinding


def read_configuration(cur: Any, binding: NativeClaimBinding) -> ParseConfigurationV2:
    cur.execute(
        "SELECT config_json FROM document_processing_runs WHERE id=%s AND document_id=%s "
        "AND parse_generation_id=%s",
        (
            binding.processing.processing_run_id,
            binding.processing.document_id,
            binding.processing.parse_generation_id,
        ),
    )
    row = cur.fetchone()
    config = decode_parse_configuration(row["config_json"]) if row else None
    if not isinstance(config, ParseConfigurationV2):
        raise NativeClaimError("Model-emitted claims require explicit v2 parse provenance.")
    return config


def require_model_configuration(
    cur: Any, binding: NativeClaimBinding, configuration: NativeModelEmissionConfiguration
) -> None:
    if read_configuration(cur, binding).definitions != configuration.definitions:
        raise NativeClaimError("Model-emitted claim definitions differ from the recorded parse.")


def read_checkpoint(cur: Any, binding: NativeClaimBinding, page_number: int):
    config = read_configuration(cur, binding)
    cur.execute(
        "SELECT * FROM document_parse_page_checkpoints WHERE parse_generation_id=%s "
        "AND page_number=%s FOR KEY SHARE",
        (binding.processing.parse_generation_id, page_number),
    )
    row = cur.fetchone()
    if row is None:
        raise NativeClaimError("Native model source checkpoint is unavailable.")
    return (
        config,
        ParsedSourcePage(
            StructurePage.model_validate(row["page_json"]),
            decode_parse_invocation(row["invocation_json"]),
            row["raw_output"],
        ),
        row["content_sha256"],
    )
