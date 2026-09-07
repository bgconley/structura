from __future__ import annotations

import hashlib
import io
from uuid import uuid4

import pytest
from PIL import Image

from lib.document_parsing.structure import SourceRender
from lib.search.indexing.errors import IndexCandidateError
from lib.search.indexing.models import IndexRenderAsset
from lib.search.indexing.render_verification import read_verified_render, verify_render_bytes
from lib.storage import ObjectStorage


def asset_and_data(tmp_path, *, mode="RGB"):
    storage = ObjectStorage(
        canonical_root=tmp_path / "canonical",
        derived_root=tmp_path / "derived",
        export_root=tmp_path / "exports",
    )
    stream = io.BytesIO()
    with Image.new(mode, (40, 20), "white") as image:
        image.save(stream, format="PNG")
    data = stream.getvalue()
    stored = storage.store_bytes(data, kind="derived", role="page")
    asset = IndexRenderAsset(
        id=uuid4(),
        page_id=uuid4(),
        page_number=1,
        uri=stored.uri,
        byte_size=len(data),
        source=SourceRender(
            page_number=1,
            image_sha256=hashlib.sha256(data).hexdigest(),
            pixel_width=40,
            pixel_height=20,
            renderer="pillow",
            renderer_version="test-fixture",
        ),
    )
    return storage, stored, asset, data


def test_exact_png_bytes_and_dimensions_are_required(tmp_path):
    storage, stored, asset, data = asset_and_data(tmp_path)
    assert read_verified_render(asset, storage) == data
    with pytest.raises(IndexCandidateError, match="bytes"):
        verify_render_bytes(asset, data + b"trailing")
    changed = asset.model_copy(
        update={"source": asset.source.model_copy(update={"pixel_width": 41})}
    )
    with pytest.raises(IndexCandidateError, match="dimensions"):
        verify_render_bytes(changed, data)
    stored.path.unlink()
    with pytest.raises(IndexCandidateError, match="unavailable"):
        read_verified_render(asset, storage)


def test_opaque_png_contract_rejects_alpha_and_arbitrary_network_uri(tmp_path):
    storage, _, asset, data = asset_and_data(tmp_path, mode="RGBA")
    with pytest.raises(IndexCandidateError, match="format"):
        verify_render_bytes(asset, data)
    with pytest.raises(IndexCandidateError, match="unavailable"):
        read_verified_render(
            asset.model_copy(update={"uri": "https://example.com/private"}), storage
        )


@pytest.mark.parametrize("damage", ["missing", "corrupt"])
def test_service_seal_refuses_damaged_snapshot_before_opening_publication_transaction(
    tmp_path, monkeypatch, damage
):
    from lib.document_processing.models import ProcessingBinding
    from lib.search.indexing import service as module
    from lib.search.indexing.models import IndexBinding

    storage, stored, asset, _ = asset_and_data(tmp_path)
    service = module.CandidateIndexService(storage)
    binding = IndexBinding(ProcessingBinding(uuid4(), uuid4(), uuid4()), uuid4())
    monkeypatch.setattr(service, "_registered_assets", lambda _: (asset,))

    def forbidden_transaction(*args, **kwargs):
        raise AssertionError("Damaged source must fail before publication transaction")

    monkeypatch.setattr(module, "db_connection", forbidden_transaction)
    if damage == "missing":
        stored.path.unlink()
    else:
        stored.path.write_bytes(b"changed after vector checkpoint")
    with pytest.raises(IndexCandidateError):
        service.seal(binding)
