from __future__ import annotations

import io
from uuid import uuid4

import pytest
from PIL import Image

from lib.evidence.errors import EvidenceUnavailable
from lib.evidence.media import snapshot_render
from lib.evidence.models import RasterIdentity, RetainedPageAsset
from lib.storage import ObjectStorage


def source_fixture(tmp_path):
    storage = ObjectStorage(derived_root=tmp_path)
    buffer = io.BytesIO()
    with Image.new("RGB", (40, 20), "white") as image:
        image.save(buffer, format="PNG")
    data = buffer.getvalue()
    stored = storage.store_bytes(data, kind="derived", role="retained-source-page")
    asset = RetainedPageAsset(
        id=uuid4(),
        page_number=1,
        page_id=uuid4(),
        checkpoint_sha256="a" * 64,
        source_render_sha256="b" * 64,
        render=RasterIdentity(
            image_sha256=stored.sha256,
            pixel_width=40,
            pixel_height=20,
            renderer="controlled-raster",
            renderer_version="v1",
        ),
        uri=stored.uri,
        byte_size=stored.byte_size,
    )
    return storage, stored, asset, data


@pytest.mark.parametrize("change", ["replace", "in_place", "unlink"])
def test_stream_is_same_verified_snapshot_after_source_changes(tmp_path, change):
    storage, stored, asset, data = source_fixture(tmp_path)
    verified = snapshot_render(asset, storage)
    if change == "replace":
        replacement = tmp_path / "replacement"
        replacement.write_bytes(b"changed source")
        replacement.replace(stored.path)
    elif change == "in_place":
        stored.path.write_bytes(b"changed source")
    else:
        stored.path.unlink()
    assert b"".join(verified.chunks()) == data
    assert verified.stream.closed


@pytest.mark.parametrize("damage", ["missing", "bytes", "size", "dimensions", "over_budget"])
def test_invalid_source_cannot_become_a_verified_media_response(tmp_path, monkeypatch, damage):
    from lib.evidence import media

    storage, stored, asset, _ = source_fixture(tmp_path)
    if damage == "missing":
        stored.path.unlink()
    elif damage == "bytes":
        stored.path.write_bytes(b"bad bytes")
    elif damage == "size":
        asset = asset.model_copy(update={"byte_size": asset.byte_size + 1})
    elif damage == "dimensions":
        asset = asset.model_copy(
            update={"render": asset.render.model_copy(update={"pixel_width": 41})}
        )
    else:
        monkeypatch.setattr(media, "MAX_RENDER_BYTES", 4)
    with pytest.raises(EvidenceUnavailable, match="unavailable"):
        snapshot_render(asset, storage)


def test_disk_spool_is_private_even_with_permissive_process_umask(tmp_path, monkeypatch):
    import os
    import stat
    import tempfile

    storage, _, asset, data = source_fixture(tmp_path)
    original = tempfile.SpooledTemporaryFile

    def forced_disk(**kwargs):
        return original(**{**kwargs, "max_size": 1})

    monkeypatch.setattr("lib.evidence.media.tempfile.SpooledTemporaryFile", forced_disk)
    previous = os.umask(0)
    try:
        verified = snapshot_render(asset, storage)
    finally:
        os.umask(previous)
    try:
        assert stat.S_IMODE(os.fstat(verified.stream.fileno()).st_mode) == 0o600
        assert b"".join(verified.chunks()) == data
    finally:
        verified.close()
