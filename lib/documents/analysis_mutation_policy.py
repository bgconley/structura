from __future__ import annotations

from collections.abc import Mapping
from typing import Any

BLOCKED_PHASE9_MUTATION_KEYS = (
    "canonicalFacts",
    "canonical_facts",
    "canonicalFields",
    "canonical_fields",
    "canonicalLineItems",
    "canonical_line_items",
    "canonicalObservations",
    "canonical_observations",
    "relationships",
    "relationshipIds",
    "relationship_ids",
    "documentRelationships",
    "documentRelationshipIds",
    "document_relationships",
    "document_relationship_ids",
    "folders",
    "folderIds",
    "folder_ids",
    "primaryFolderId",
    "primary_folder_id",
    "tags",
    "tagIds",
    "tag_ids",
    "deadlines",
    "deadlineIds",
    "deadline_ids",
    "documentDeadlines",
    "documentDeadlineIds",
    "document_deadlines",
    "document_deadline_ids",
    "reviewStatus",
    "review_status",
    "reviewTasks",
    "reviewTaskIds",
    "review_tasks",
    "review_task_ids",
)


def phase9_mutation_violations(output: Mapping[str, Any]) -> list[str]:
    found: list[str] = []
    _collect_mutation_keys(output, found)
    return found


def _collect_mutation_keys(value: Any, found: list[str]) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_text = str(key)
            if key_text in BLOCKED_PHASE9_MUTATION_KEYS and key_text not in found:
                found.append(key_text)
            _collect_mutation_keys(item, found)
    elif isinstance(value, list):
        for item in value:
            _collect_mutation_keys(item, found)
