"""Bounded private verified snapshots; never reopen a public response source path."""

from __future__ import annotations

import hashlib
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass
from typing import BinaryIO, cast

from PIL import Image, UnidentifiedImageError

from lib.evidence.errors import EvidenceUnavailable
from lib.evidence.models import MAX_RENDER_BYTES, MAX_RENDER_PIXELS, RetainedPageAsset
from lib.storage import ObjectStorage, StorageError
from lib.storage.service import parse_object_uri


@dataclass
class VerifiedRender:
    stream: BinaryIO
    byte_size: int
    sha256: str

    def chunks(self) -> Iterator[bytes]:
        try:
            self.stream.seek(0)
            while data := self.stream.read(1024 * 1024):
                yield data
        finally:
            self.close()

    def close(self) -> None:
        self.stream.close()


def snapshot_render(asset: RetainedPageAsset, storage: ObjectStorage) -> VerifiedRender:
    spool = tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024, mode="w+b")
    try:
        address = parse_object_uri(asset.uri)
        if address.kind != "derived" or address.sha256 != asset.render.image_sha256:
            raise EvidenceUnavailable("Retained source image is unavailable.")
        count, digest = 0, hashlib.sha256()
        with storage.path_for_uri(asset.uri).open("rb") as source:
            while data := source.read(min(1024 * 1024, MAX_RENDER_BYTES + 1 - count)):
                count += len(data)
                if count > MAX_RENDER_BYTES or count > asset.byte_size:
                    raise EvidenceUnavailable("Retained source image is unavailable.")
                digest.update(data)
                spool.write(data)
        if count != asset.byte_size or digest.hexdigest() != asset.render.image_sha256:
            raise EvidenceUnavailable("Retained source image is unavailable.")
        spool.seek(0)
        with Image.open(spool) as image:
            if (
                image.format != "PNG"
                or image.mode != "RGB"
                or image.size != (asset.render.pixel_width, asset.render.pixel_height)
                or image.width * image.height > MAX_RENDER_PIXELS
                or getattr(image, "n_frames", 1) != 1
            ):
                raise EvidenceUnavailable("Retained source image is unavailable.")
            image.verify()
        spool.seek(0)
        return VerifiedRender(cast(BinaryIO, spool), count, digest.hexdigest())
    except (
        OSError,
        StorageError,
        UnidentifiedImageError,
        Image.DecompressionBombError,
        EvidenceUnavailable,
    ):
        spool.close()
        raise EvidenceUnavailable("Retained source image is unavailable.") from None
    except BaseException:
        spool.close()
        raise
