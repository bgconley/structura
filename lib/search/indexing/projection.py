"""Pure complete-input projection from one sealed native structure.

This first policy collects parse text only; no accepted-fact or filing metadata
projection is implied. Visual dispositions are explicit for every source page.
"""

from __future__ import annotations

from uuid import UUID, uuid5

from lib.document_parsing.structure import DocumentStructure, StructurePage
from lib.document_processing.models import content_digest
from lib.model_runtime.embedding_identity import embedding_input_identity
from lib.model_runtime.profiles import get_model_profile
from lib.search.indexing.configuration import IndexConfiguration, Modality
from lib.search.indexing.errors import IndexCandidateError
from lib.search.indexing.models import IndexInput, IndexManifest, IndexRenderAsset, PageDisposition
from lib.storage.service import parse_object_uri


def visual_reasons(page: StructurePage, *, original_is_image: bool) -> tuple[str, ...]:
    reasons = []
    if original_is_image:
        reasons.append("image_original")
    if page.source is None:
        raise IndexCandidateError("Candidate indexing requires a complete rendered source.")
    if len((page.source.native_text or "").strip()) < 32:
        reasons.append("low_native_text")
    if len(page.tables) >= 2 or sum(e.kind == "figure" for e in page.elements) >= 2:
        reasons.append("layout_complexity")
    if page.state in {"partial", "insufficient_signal"}:
        reasons.append("partial_parse")
    return tuple(reasons)


def render_asset_id(index_id: UUID, page_id: UUID) -> UUID:
    return uuid5(index_id, f"render:{page_id}")


def project_inputs(
    structure: DocumentStructure,
    *,
    index_id: UUID,
    configuration: IndexConfiguration,
    assets: tuple[IndexRenderAsset, ...] = (),
) -> IndexManifest:
    """Refuse missing/extra assets or overflow; never truncate successful inputs."""
    configuration = IndexConfiguration.model_validate(configuration.model_dump(mode="json"))
    inputs: list[IndexInput] = []
    dispositions = []
    supplied = {asset.page_number: asset for asset in assets}
    if len(supplied) != len(assets):
        raise IndexCandidateError("Candidate render inventory contains duplicate pages.")
    consumed_assets: set[int] = set()
    for page in structure.pages:
        if page.state not in {"processed", "partial", "insufficient_signal"} or page.source is None:
            raise IndexCandidateError("Candidate indexing requires complete parse checkpoints.")
        page_chunks = tuple(c for c in structure.chunks if c.page_number == page.page_number)
        chunks = tuple(c for c in page_chunks if c.text.strip())
        text_requested = "text" in configuration.modalities
        if text_requested:
            for chunk in chunks:
                if len(chunk.text.encode("utf-8")) > configuration.max_text_bytes:
                    raise IndexCandidateError("Candidate text exceeds the frozen input budget.")
                inputs.append(
                    _input(
                        index_id=index_id,
                        configuration=configuration,
                        ordinal=len(inputs),
                        modality="text",
                        owner_id=chunk.id,
                        page_number=page.page_number,
                        element_ids=chunk.element_ids,
                        text=chunk.text,
                        text_origins=chunk.text_origins,
                        asset=None,
                    )
                )
        reasons = visual_reasons(
            page, original_is_image=structure.source.mime_type != "application/pdf"
        )
        visual_requested = "visual" in configuration.modalities
        if visual_requested and reasons:
            asset = supplied.get(page.page_number)
            if asset is None or asset.source != page.source or asset.page_id != page.id:
                raise IndexCandidateError("Candidate render does not match the sealed source page.")
            uri = parse_object_uri(asset.uri)
            if (
                asset.id != render_asset_id(index_id, page.id)
                or uri.kind != "derived"
                or uri.sha256 != page.source.image_sha256
            ):
                raise IndexCandidateError("Candidate render has a conflicting immutable identity.")
            consumed_assets.add(page.page_number)
            inputs.append(
                _input(
                    index_id=index_id,
                    configuration=configuration,
                    ordinal=len(inputs),
                    modality="visual",
                    owner_id=page.id,
                    page_number=page.page_number,
                    element_ids=(),
                    text="",
                    text_origins=(),
                    asset=asset,
                )
            )
        dispositions.append(
            PageDisposition.model_validate(
                {
                    "page_number": page.page_number,
                    "text": ("eligible" if chunks else "ineligible")
                    if text_requested
                    else "not_requested",
                    "text_reason": ("nonempty_chunks" if chunks else "no_text")
                    if text_requested
                    else "not_requested",
                    "visual": ("eligible" if reasons else "ineligible")
                    if visual_requested
                    else "not_requested",
                    "visual_reasons": (reasons or ("digital_text_page",))
                    if visual_requested
                    else ("not_requested",),
                    "parse_state": page.state,
                    "whitespace_chunk_ids": tuple(c.id for c in page_chunks if not c.text.strip()),
                }
            )
        )
    if set(supplied) != consumed_assets:
        raise IndexCandidateError("Candidate render inventory includes an unexpected page.")
    if len(inputs) > configuration.max_inputs:
        raise IndexCandidateError("Candidate input count exceeds the frozen budget.")
    return IndexManifest(
        index_generation_id=index_id,
        parse_generation_id=structure.parse_generation_id,
        structure_sha256=content_digest(structure.model_dump(mode="json")),
        configuration_sha256=configuration.fingerprint,
        inputs=tuple(inputs),
        pages=tuple(dispositions),
    )


def _input(
    *,
    index_id: UUID,
    configuration: IndexConfiguration,
    ordinal: int,
    modality: Modality,
    owner_id: UUID,
    page_number: int,
    element_ids: tuple[UUID, ...],
    text: str,
    text_origins: tuple[str, ...],
    asset: IndexRenderAsset | None,
) -> IndexInput:
    # The same canonical content object as EmbeddingInput.sha256; the model hash
    # below uses the shared identity implementation, not a parallel protocol.
    content_hash = content_digest(
        {
            "text": text,
            "mime_type": asset.mime_type if asset else None,
            "image_sha256": asset.source.image_sha256 if asset else None,
        }
    )
    space = configuration.space(modality)
    return IndexInput.model_validate(
        dict(
            id=uuid5(index_id, f"{modality}:{owner_id}"),
            ordinal=ordinal,
            modality=modality,
            owner_id=owner_id,
            page_number=page_number,
            element_ids=element_ids,
            text=text,
            text_origins=text_origins,
            render_asset_id=asset.id if asset else None,
            content_sha256=content_hash,
            model_input_sha256=embedding_input_identity(
                content_hash,
                get_model_profile(space.profile),
                dimensions=space.dimensions,
                purpose="document",
            ),
        )
    )
