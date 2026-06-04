from __future__ import annotations

from lib.documents.analysis_intake import phase9_mutation_violations


def test_phase9_output_mutation_guard_blocks_state_identifier_aliases() -> None:
    violations = phase9_mutation_violations(
        {
            "answer": "Draft analysis only.",
            "relationshipIds": ["relationship-1"],
            "documentRelationshipIds": ["relationship-2"],
            "deadlineIds": ["deadline-1"],
            "documentDeadlineIds": ["deadline-2"],
            "reviewTaskIds": ["task-1"],
            "nested": {
                "relationship_ids": ["relationship-3"],
                "document_relationship_ids": ["relationship-4"],
                "deadline_ids": ["deadline-3"],
                "document_deadline_ids": ["deadline-4"],
                "review_task_ids": ["task-2"],
            },
        }
    )

    assert violations == [
        "relationshipIds",
        "documentRelationshipIds",
        "deadlineIds",
        "documentDeadlineIds",
        "reviewTaskIds",
        "relationship_ids",
        "document_relationship_ids",
        "deadline_ids",
        "document_deadline_ids",
        "review_task_ids",
    ]
