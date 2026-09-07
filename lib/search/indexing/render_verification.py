"""Bounded exact artifact reads outside transactions; no URL fetching or rerendering."""

from __future__ import annotations

import hashlib
import io

from PIL import Image, UnidentifiedImageError

from lib.search.indexing.errors import IndexCandidateError
from lib.search.indexing.models import IndexRenderAsset
from lib.storage import ObjectStorage
from lib.storage.service import StorageError, parse_object_uri


def read_verified_render(asset: IndexRenderAsset, storage: ObjectStorage) -> bytes:
    try:
        uri = parse_object_uri(asset.uri)
        if uri.kind != "derived" or uri.sha256 != asset.source.image_sha256:
            raise IndexCandidateError("Render object identity does not match the sealed page.")
        with storage.path_for_uri(asset.uri).open("rb") as stream:
            data = stream.read(10 * 1024 * 1024 + 1)
        verify_render_bytes(asset, data)
        return data
    except (OSError, StorageError):
        raise IndexCandidateError("Candidate render artifact is unavailable.") from None


def verify_render_bytes(asset: IndexRenderAsset, data: bytes) -> None:
    if (
        len(data) != asset.byte_size
        or len(data) > 10 * 1024 * 1024
        or hashlib.sha256(data).hexdigest() != asset.source.image_sha256
    ):
        raise IndexCandidateError("Render bytes do not match the sealed source identity.")
    try:
        with Image.open(io.BytesIO(data)) as image:
            if (
                image.format != "PNG"
                or image.mode != "RGB"
                or image.size != (asset.source.pixel_width, asset.source.pixel_height)
                or getattr(image, "n_frames", 1) != 1
                or image.width * image.height > 40_000_000
            ):
                raise IndexCandidateError(
                    "Render format or dimensions do not match its descriptor."
                )
            image.verify()
    except (OSError, UnidentifiedImageError, Image.DecompressionBombError):
        raise IndexCandidateError("Candidate render is not a valid bounded PNG.") from None
