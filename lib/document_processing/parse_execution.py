"""Candidate-only native parsing under a caller-owned independently renewed lease.

The caller supplies the actual live client or an explicitly declared fixture.
This bridge creates no client fallback, job, worker, publication, or accepted fact.
Run admission does not establish continued authorization of an asynchronous actor;
that separate policy remains the processing lifecycle's responsibility.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from lib.document_parsing.document_context import freeze_document_context
from lib.document_parsing.document_parse import parse_document
from lib.document_parsing.qwen_page_parser import PageGenerationClient, ParsedSourcePage
from lib.document_parsing.source_adapter import DocumentSource
from lib.document_processing.checkpoint_validation import validate_checkpoint
from lib.document_processing.configuration_types import AnyParseConfiguration, ParseConfigurationV2
from lib.document_processing.errors import ProcessingAuthorityLost, ProcessingError
from lib.document_processing.models import ProcessingBinding
from lib.document_processing.parser_configuration import (
    DeclaredParserDeployment,
    validate_parser_configuration,
)
from lib.document_processing.service import DocumentProcessingService
from lib.document_processing.source_repository import load_processing_source
from lib.document_processing.understanding_adapter import UnderstandingPageParser
from lib.jobs.ownership import current_job_attempt
from lib.model_runtime.contracts import VisionGenerateRequest, VisionGenerateResponse
from lib.storage import ObjectStorage
from lib.storage.service import parse_object_uri


@dataclass(frozen=True)
class ParseExecutionResult:
    structure_sha256: str
    page_count: int
    resumed_pages: int
    new_pages: int
    batches: int
    deployment_declaration: str


def execute_parse_candidate(
    binding: ProcessingBinding,
    *,
    storage: ObjectStorage,
    client: PageGenerationClient,
    deployment: DeclaredParserDeployment,
    service: DocumentProcessingService,
    batch_pages: int = 50,
    timeout_seconds: int | None = None,
) -> ParseExecutionResult:
    """Checkpoint all supported source pages in one generation, then seal once.

    Call inside keep_job_lease (or the same explicit claimed attempt scope in
    tests). Source/model work runs after repository transactions have closed.
    Any exception propagates to the owning job lifecycle; committed checkpoints
    survive. The result is a sealed candidate, never a current publication.
    """
    if type(batch_pages) is not int or not 1 <= batch_pages <= 500:
        raise ProcessingError("Parser batch size must be between 1 and 500 pages.")
    if timeout_seconds is not None and (
        type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 600
    ):
        raise ProcessingError("Parser request timeout must be between 1 and 600 seconds.")
    if current_job_attempt() is None:
        raise ProcessingAuthorityLost("Candidate parsing requires a claimed processing job.")
    registered = load_processing_source(binding)
    configuration = registered.configuration
    validate_parser_configuration(configuration, deployment, registered.mime_type)
    if isinstance(configuration, ParseConfigurationV2):
        if timeout_seconds is not None and timeout_seconds != configuration.request.timeout_seconds:
            raise ProcessingError("Request timeout cannot override the frozen v2 configuration.")
        timeout_seconds = configuration.request.timeout_seconds
    elif timeout_seconds is None:
        timeout_seconds = 180
    address = parse_object_uri(registered.uri)
    if address.sha256 != registered.original_sha256:
        raise ProcessingError("Registered source URI does not match the requested original hash.")
    service.assert_authority(binding)
    path = storage.path_for_uri(registered.uri)
    with DocumentSource(
        path,
        asset_id=registered.original_asset_id,
        expected_sha256=registered.original_sha256,
        mime_type=registered.mime_type,
        max_bytes=registered.byte_size,
    ) as source:
        if source.inventory.byte_size != registered.byte_size:
            raise ProcessingError("Original bytes do not match their registered size.")
        if isinstance(configuration, ParseConfigurationV2) and (
            freeze_document_context(source) != configuration.context
        ):
            raise ProcessingError("Original source context differs from its frozen configuration.")
        service.initialize_inventory(binding, source.inventory)
        checkpoints = list(service.load_checkpoints(binding))
        if isinstance(configuration, ParseConfigurationV2):
            for previous in checkpoints:
                validate_checkpoint(
                    previous,
                    generation_id=binding.parse_generation_id,
                    inventory=source.inventory,
                    configuration=configuration,
                )
        resumed = len(checkpoints)
        batches = 0

        def authority() -> None:
            service.assert_authority(binding)

        def checkpoint(page: ParsedSourcePage) -> None:
            service.checkpoint(binding, page)
            checkpoints.append(page)

        frozen_client = _FrozenParserClient(client, configuration, authority)
        parser = (
            UnderstandingPageParser(frozen_client, binding.parse_generation_id, configuration)
            if isinstance(configuration, ParseConfigurationV2)
            else None
        )
        while True:
            before = len(checkpoints)
            structure = parse_document(
                source,
                frozen_client,
                generation_id=binding.parse_generation_id,
                run_id=binding.processing_run_id,
                max_new_pages=batch_pages,
                completed=tuple(checkpoints),
                assert_authority=authority,
                checkpoint=checkpoint,
                timeout_seconds=timeout_seconds,
                render_scale=configuration.render_scale,
                page_parser=parser,
            )
            if len(checkpoints) > before:
                batches += 1
            if len(checkpoints) == len(source.inventory.pages):
                digest = service.seal(binding, structure)
                return ParseExecutionResult(
                    digest,
                    len(source.inventory.pages),
                    resumed,
                    len(checkpoints) - resumed,
                    batches,
                    configuration.model_revision,
                )
            if len(checkpoints) == before:
                raise ProcessingError("Parser batch made no checkpoint progress.")


@dataclass(frozen=True)
class _FrozenParserClient:
    client: PageGenerationClient
    configuration: AnyParseConfiguration
    assert_authority: Callable[[], None]

    def generate(self, request: VisionGenerateRequest) -> VisionGenerateResponse:
        config = self.configuration
        if (request.profile_name, request.prompt_version, request.response_schema_name) != (
            config.profile,
            config.prompt_version,
            config.output_schema_version,
        ):
            raise ProcessingError("Parser request does not match its frozen configuration.")
        # Rendering may take time. Recheck immediately before sending another
        # page to the shared model; persistence is independently fenced afterward.
        self.assert_authority()
        response = self.client.generate(request)
        if (
            (
                response.profile_name,
                response.model_name,
                response.source_engine,
                response.prompt_version,
            )
            != (config.profile, config.served_model, config.source_engine, config.prompt_version)
            or not response.structured_output_used
            or response.finish_reason != "stop"
        ):
            raise ProcessingError("Parser response does not match its frozen invocation contract.")
        return response
