from __future__ import annotations

PARADEDB_HIGHLIGHT_TAGS = ("<b>", "</b>")


def plain_search_snippet(value: str | None) -> str | None:
    if value is None:
        return None
    snippet = value
    for tag in PARADEDB_HIGHLIGHT_TAGS:
        snippet = snippet.replace(tag, "")
    return snippet
