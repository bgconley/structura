"""Model span selection for the extractive KVP lane (ADR 0006 X2, E2).

The model maps the region's expected canonical keys to a span-id enum (or
null). It cannot emit a value: the schema's only vocabulary is the
deterministic span ids built by span_candidates, so transcription failure
classes are unrepresentable. Selections are cached in-process by prompt
fingerprint to dedupe identical requests within a worker process.
"""

from __future__ import annotations

import hashlib
import threading
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any, Protocol

from lib.config import get_settings
from lib.extraction.expected_field_coverage import normalized_field_name
from lib.extraction.text_lane.span_candidates import SpanCandidate
from lib.model_runtime.clients._openai_text import OpenAITextGenerateClient
from lib.model_runtime.contracts import TextGenerateRequest
from lib.model_runtime.profiles import get_model_profile

SPAN_SELECTION_PROMPT_VERSION = "text_lane_span_selection.v1"
MAX_SELECTION_KEYS = 16

_SELECTION_CACHE: dict[str, SpanSelection] = {}
_SELECTION_CACHE_LOCK = threading.Lock()


@dataclass(frozen=True)
class SpanSelection:
    selections: Mapping[str, str | None]
    model_name: str
    model_version: str
    prompt_version: str
    from_cache: bool = False

    def selections_json(self) -> dict[str, str | None]:
        return dict(sorted(self.selections.items()))


class SpanSelector(Protocol):
    def select_spans(
        self,
        *,
        family: str,
        expected_keys: Sequence[str],
        spans: Sequence[SpanCandidate],
    ) -> SpanSelection: ...


def selection_keys(expected_fields: Sequence[str]) -> tuple[str, ...]:
    """Normalized, deduplicated expected keys bounded to the schema limit."""
    keys: list[str] = []
    seen: set[str] = set()
    for raw in expected_fields:
        normalized = normalized_field_name(str(raw))
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        keys.append(normalized)
    return tuple(keys[:MAX_SELECTION_KEYS])


def span_selection_schema(
    *,
    keys: Sequence[str],
    spans: Sequence[SpanCandidate],
) -> dict[str, Any]:
    span_ids = [span.span_id for span in spans]
    return {
        "type": "object",
        "additionalProperties": False,
        "required": list(keys),
        "properties": {
            key: {"type": ["string", "null"], "enum": [*span_ids, None]} for key in keys
        },
    }


def span_selection_prompt(
    *,
    family: str,
    keys: Sequence[str],
    spans: Sequence[SpanCandidate],
) -> str:
    lines = [
        f"You are matching expected fields of a {family} document region to "
        "text spans extracted verbatim from the document.",
        "For every expected field, answer with the id of the span whose value "
        "belongs to that field, or null when no listed span contains it.",
        "Use span ids exactly as written. Never invent values.",
        "",
        "Expected fields:",
    ]
    for key in keys:
        lines.append(f"  - {key}")
    lines.append("")
    lines.append("Candidate spans:")
    for span in spans:
        lines.append(f"  {span.describe()}")
    lines.append("")
    lines.append(
        'Respond with JSON only: {"<expected field>": "<span id>" | null, ...} '
        "covering every expected field."
    )
    return "\n".join(lines)


def clear_span_selection_cache() -> None:
    with _SELECTION_CACHE_LOCK:
        _SELECTION_CACHE.clear()


class LiveSpanSelector:
    def __init__(self, *, client: OpenAITextGenerateClient | None = None) -> None:
        self._client = client

    def select_spans(
        self,
        *,
        family: str,
        expected_keys: Sequence[str],
        spans: Sequence[SpanCandidate],
    ) -> SpanSelection:
        if not expected_keys:
            raise ValueError("Span selection requires expected keys.")
        if not spans:
            raise ValueError("Span selection requires candidate spans.")
        prompt = span_selection_prompt(family=family, keys=expected_keys, spans=spans)
        cache_key = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        with _SELECTION_CACHE_LOCK:
            cached = _SELECTION_CACHE.get(cache_key)
        if cached is not None:
            return replace(cached, from_cache=True)
        selection = self._select_live(
            prompt=prompt,
            expected_keys=expected_keys,
            spans=spans,
        )
        with _SELECTION_CACHE_LOCK:
            _SELECTION_CACHE.setdefault(cache_key, selection)
        return selection

    def _select_live(
        self,
        *,
        prompt: str,
        expected_keys: Sequence[str],
        spans: Sequence[SpanCandidate],
    ) -> SpanSelection:
        client = self._ensure_client()
        request = TextGenerateRequest(
            profile_name=client.profile.name,
            prompt_version=SPAN_SELECTION_PROMPT_VERSION,
            prompt=prompt,
            response_schema_name=SPAN_SELECTION_PROMPT_VERSION,
            max_output_tokens=min(1024, 128 + 28 * len(expected_keys)),
            temperature=0.0,
            timeout_seconds=get_settings().model_http_timeout_seconds,
            response_json_schema=span_selection_schema(keys=expected_keys, spans=spans),
            seed=0,
        )
        response = client.generate(request)
        return SpanSelection(
            selections=selections_from_payload(
                response.normalized_json,
                expected_keys=expected_keys,
                spans=spans,
            ),
            model_name=response.model_name,
            model_version=response.model_version,
            prompt_version=SPAN_SELECTION_PROMPT_VERSION,
        )

    def _ensure_client(self) -> OpenAITextGenerateClient:
        if self._client is None:
            settings = get_settings()
            self._client = OpenAITextGenerateClient(
                profile=get_model_profile(settings.qwen_semantic_profile),
                http_client_base_url=settings.model_qwen_semantic_url,
            )
        return self._client


def selections_from_payload(
    payload: Mapping[str, Any],
    *,
    expected_keys: Sequence[str],
    spans: Sequence[SpanCandidate],
) -> dict[str, str | None]:
    known_ids = {span.span_id for span in spans}
    selections: dict[str, str | None] = {}
    for key in expected_keys:
        value = payload.get(key)
        selections[key] = value if isinstance(value, str) and value in known_ids else None
    return selections
