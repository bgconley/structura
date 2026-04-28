from __future__ import annotations

import hashlib
import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path


class ModelMediaError(Exception):
    pass


@dataclass(frozen=True)
class StagedModelInput:
    path: Path
    sha256: str
    byte_size: int
    mime_type: str


@contextmanager
def stage_model_input_bytes(
    *,
    root: Path,
    content: bytes,
    suffix: str,
    mime_type: str,
) -> Iterator[StagedModelInput]:
    if not content:
        raise ModelMediaError("Model input content is empty.")

    safe_suffix = _safe_suffix(suffix)
    root_path = root.expanduser().resolve()
    root_path.mkdir(parents=True, exist_ok=True, mode=0o700)

    sha256 = hashlib.sha256(content).hexdigest()
    staged_path = (root_path / f"{sha256}{safe_suffix}").resolve()
    if staged_path.parent != root_path:
        raise ModelMediaError("Model input staging path escapes the configured root.")

    fd = os.open(staged_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
        os.chmod(staged_path, 0o600)
        yield StagedModelInput(
            path=staged_path,
            sha256=sha256,
            byte_size=len(content),
            mime_type=mime_type,
        )
    finally:
        try:
            staged_path.unlink()
        except FileNotFoundError:
            pass


def _safe_suffix(suffix: str) -> str:
    if not re.fullmatch(r"\.[A-Za-z0-9]{1,12}", suffix):
        raise ModelMediaError("Model input suffix is unsafe.")
    return suffix.lower()
