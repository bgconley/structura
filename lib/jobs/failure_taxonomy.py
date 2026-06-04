from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

EXPLICIT_TAXONOMY_KEYS = (
    "taxonomy_code",
    "taxonomyCode",
    "failure_taxonomy",
    "failureTaxonomy",
    "failure_code",
    "failureCode",
)

ERROR_CLASS_TAXONOMY_ALIASES = {
    "ModelTimeoutError": "model_timeout",
    "ModelProtocolError": "model_protocol",
}


def failure_taxonomy_code(
    *,
    queue_name: str | None,
    job_type: str | None,
    error_class: str,
    details: Mapping[str, Any] | None,
) -> str:
    explicit = _explicit_taxonomy_code(details)
    if explicit:
        return explicit

    scope = _taxonomy_token(queue_name) or _taxonomy_token(job_type) or "pipeline_job"
    failure = ERROR_CLASS_TAXONOMY_ALIASES.get(error_class) or _taxonomy_token(error_class)
    return f"{scope}_{failure or 'operational_failure'}"


def _explicit_taxonomy_code(details: Mapping[str, Any] | None) -> str | None:
    if not details:
        return None
    for source in (details, _mapping(details.get("details"))):
        for key in EXPLICIT_TAXONOMY_KEYS:
            value = source.get(key)
            if value not in (None, ""):
                return _taxonomy_token(value)
    return None


def _taxonomy_token(value: object) -> str:
    token = re.sub(r"(?<!^)(?=[A-Z])", "_", str(value or "").strip())
    token = re.sub(r"[^A-Za-z0-9]+", "_", token).lower()
    return "_".join(part for part in token.split("_") if part)


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}
