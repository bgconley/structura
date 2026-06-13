from __future__ import annotations

from typing import Any

from lib.model_runtime.reliability_admission_events import evaluate_admission_events
from lib.model_runtime.reliability_invariant_rules import (
    ViolationMap,
    evaluate_canonical_fields,
    evaluate_extractions,
    evaluate_planner_tasks,
    evaluate_semantic_annotations,
)
from lib.model_runtime.reliability_rejected_candidates import evaluate_rejected_candidate_insertions

_INVARIANTS: tuple[tuple[str, str], ...] = (
    (
        "selectedGraniteTasksMissingContract",
        "Selected or enqueued Granite semantic-region tasks must have a model-output contract.",
    ),
    (
        "selectedGraniteTasksMissingGrounding",
        "Selected or enqueued Granite semantic-region tasks must have concrete Docling grounding.",
    ),
    (
        "selectedGraniteTasksIncompatibleFamilySchema",
        "Selected or enqueued Granite semantic-region tasks must be family/schema compatible.",
    ),
    (
        "semanticAnnotationsMissingDeterministicBaseline",
        "Qwen/Docling semantic annotations must carry deterministic baseline coverage telemetry.",
    ),
    (
        "promptSchemaArtifactsAdmitted",
        "Prompt, schema, and response-format artifacts must never be admitted as candidates.",
    ),
    (
        "placeholderOrLiteralNullCandidatesAdmitted",
        "Placeholder and literal-null candidate values must never be admitted.",
    ),
    (
        "admittedCandidatesWithoutConcreteEvidence",
        "Admitted candidates must have concrete evidence locators.",
    ),
    (
        "admissionEventsMissingTelemetry",
        "Admission events must include queryable lineage, gate versions, and candidate "
        "fingerprints.",
    ),
    (
        "rejectedCandidatesInserted",
        "Rejected candidates must not be inserted as field, line-item, or observation rows.",
    ),
    (
        "modelBackedSemanticRegionAutoAccepted",
        "Model-backed semantic-region extraction rows must remain review-required.",
    ),
    (
        "fabricatedCanonicalRequiredFields",
        "Canonical required fields must not be fabricated.",
    ),
    (
        "titleDerivedMerchantSellerWithoutAllowlist",
        "Merchant or seller canonical fields must not be derived from document title "
        "without allowlist.",
    ),
    (
        "aggregateSchemasFromIncompatibleFamilies",
        "Aggregate extraction schemas must not be created from incompatible source families.",
    ),
    (
        "aggregateExtractionsMissingRunLineage",
        "Current aggregate extractions must carry source run and region-extraction lineage.",
    ),
    (
        "duplicateCurrentAggregateExtractions",
        "At most one current aggregate extraction may exist per document, schema, and scope.",
    ),
)

__all__ = ["evaluate_hard_correctness_invariants"]


def evaluate_hard_correctness_invariants(
    documents: list[dict[str, Any]],
) -> dict[str, Any]:
    violations: ViolationMap = {key: [] for key, _ in _INVARIANTS}

    evaluate_planner_tasks(documents, violations)
    evaluate_semantic_annotations(documents, violations)
    evaluate_admission_events(documents, violations)
    evaluate_rejected_candidate_insertions(documents, violations)
    evaluate_extractions(documents, violations)
    evaluate_canonical_fields(documents, violations)

    invariant_results = {
        key: {
            "description": description,
            "violationCount": len(violations[key]),
            "examples": violations[key][:10],
        }
        for key, description in _INVARIANTS
    }
    total = sum(len(items) for items in violations.values())
    return {
        "status": "passed" if total == 0 else "failed",
        "totalViolationCount": total,
        "invariants": invariant_results,
    }
