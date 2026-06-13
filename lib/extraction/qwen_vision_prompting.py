from __future__ import annotations

from lib.extraction.models import ExtractionSourceDocument
from lib.semantic_annotations.models import SemanticExtractionTask

QWEN_VISION_PROMPT_VERSION = "phase8_5-qwen-vision-fallback-v1"
MAX_QWEN_VISION_FIELDS = 10


def qwen_vision_observation_prompt(
    *,
    source: ExtractionSourceDocument,
    schema_name: str,
    route_profile: str,
    semantic_task: SemanticExtractionTask,
) -> str:
    expected = ", ".join(semantic_task.expected_fields[:MAX_QWEN_VISION_FIELDS]) or "observations"
    page_text = _bounded_page_text(source, semantic_task)
    return "\n".join(
        [
            "You are a review-only visual extraction fallback.",
            "Return JSON that matches the supplied schema exactly.",
            "Do not infer canonical facts or final document truth.",
            "Emit at most ten observations.",
            "For each observation, include field_name, value, value_type, quote, and confidence.",
            "If Docling text is present, quote must be copied verbatim from that text.",
            "If the value is only visible in the image and no text is present, set quote to null.",
            "Every emitted value remains human-review required.",
            f"Target schema: {schema_name}",
            f"Route profile: {route_profile}",
            f"Semantic type: {semantic_task.semantic_type}",
            f"Expected fields: {expected}",
            f"Docling text excerpt:\n{page_text}",
        ]
    )


def _bounded_page_text(
    source: ExtractionSourceDocument,
    semantic_task: SemanticExtractionTask,
) -> str:
    page_numbers = _task_page_numbers(semantic_task)
    texts: list[str] = []
    for page in source.pages:
        if page_numbers and page.page_number not in page_numbers:
            continue
        text = " ".join(page.text.split())
        if text:
            texts.append(f"page {page.page_number}: {text}")
    if not texts:
        return "(no Docling text for this region)"
    return "\n".join(texts)[:2000]


def _task_page_numbers(semantic_task: SemanticExtractionTask) -> set[int]:
    page_number = semantic_task.metadata.get("page_number")
    if isinstance(page_number, int):
        return {page_number}
    return set()
