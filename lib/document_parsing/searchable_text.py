"""Complete element/table text projections retaining their source lineage."""

from __future__ import annotations

from uuid import UUID, uuid5

from lib.document_parsing.structure import StructureChunk, StructurePage


def page_chunks(
    page: StructurePage, generation_id: UUID, *, max_chars: int = 3000
) -> tuple[StructureChunk, ...]:
    if max_chars < 1:
        raise ValueError("Chunk size must be positive.")
    tables = {table.element_id: table for table in page.tables}
    chunks = []
    for element in page.elements:
        parts = [element.text]
        origins = [element.text_origin]
        table = tables.get(element.id)
        if table:
            for row in range(table.row_count):
                cells = sorted(
                    (cell for cell in table.cells if cell.row == row), key=lambda cell: cell.column
                )
                parts.append("\t".join(cell.text for cell in cells))
                origins.extend(cell.text_origin for cell in cells)
        text = "\n".join(part for part in parts if part)
        for offset in range(0, len(text), max_chars):
            chunks.append(
                StructureChunk(
                    id=uuid5(generation_id, f"chunk:{element.id}:{offset}:{max_chars}"),
                    page_number=page.page_number,
                    element_ids=(element.id,),
                    text=text[offset : offset + max_chars],
                    text_origins=tuple(dict.fromkeys(origins)),
                )
            )
    return tuple(chunks)
