from __future__ import annotations

PROMPT_ECHO_PATTERNS = (
    "identify and extract",
    "extract the schema",
    "extruct the schema",
    "tabls schema",
    "table schema",
    "tables in the image",
    "reading order",
    "return only json",
    "matching the schema",
)


def contains_prompt_echo(value: object) -> bool:
    text = str(value or "").lower()
    return any(pattern in text for pattern in PROMPT_ECHO_PATTERNS)
