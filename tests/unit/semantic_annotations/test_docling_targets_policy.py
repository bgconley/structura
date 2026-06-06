from __future__ import annotations

import inspect

from lib.semantic_annotations import docling_targets as docling_targets_module


def test_docling_structural_target_priority_uses_explicit_semantic_type_registry() -> None:
    source = inspect.getsource(docling_targets_module)

    assert "semantic_type.endswith" not in source
    assert "LINE_ITEM_TABLE_SEMANTIC_TYPES" in source
