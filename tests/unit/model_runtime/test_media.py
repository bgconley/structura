from __future__ import annotations

import os

import pytest

from lib.model_runtime.media import ModelMediaError, stage_model_input_bytes


def test_stage_model_input_bytes_creates_content_addressed_restricted_file(tmp_path) -> None:
    root = tmp_path / "scratch"
    content = b"image-bytes"

    with stage_model_input_bytes(
        root=root,
        content=content,
        suffix=".png",
        mime_type="image/png",
    ) as staged:
        assert staged.path.parent.resolve() == root.resolve()
        assert staged.path.name == f"{staged.sha256}.png"
        assert staged.path.read_bytes() == content
        assert staged.byte_size == len(content)
        assert staged.mime_type == "image/png"
        assert oct(os.stat(staged.path).st_mode & 0o777) == "0o600"

    assert not staged.path.exists()


def test_stage_model_input_bytes_rejects_empty_content_and_unsafe_suffix(tmp_path) -> None:
    with pytest.raises(ModelMediaError, match="empty"):
        with stage_model_input_bytes(
            root=tmp_path / "scratch",
            content=b"",
            suffix=".png",
            mime_type="image/png",
        ):
            pass

    with pytest.raises(ModelMediaError, match="suffix"):
        with stage_model_input_bytes(
            root=tmp_path / "scratch",
            content=b"data",
            suffix="../secret",
            mime_type="image/png",
        ):
            pass


def test_stage_model_input_bytes_removes_file_after_exception(tmp_path) -> None:
    root = tmp_path / "scratch"
    staged_path = None

    with pytest.raises(RuntimeError, match="boom"):
        with stage_model_input_bytes(
            root=root,
            content=b"image-bytes",
            suffix=".jpg",
            mime_type="image/jpeg",
        ) as staged:
            staged_path = staged.path
            raise RuntimeError("boom")

    assert staged_path is not None
    assert not staged_path.exists()
