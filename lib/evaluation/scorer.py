"""Compute neutral parse diagnostics from independently bound inputs."""

from __future__ import annotations

from collections import Counter
from typing import Any

from lib.evaluation.annotations import DocumentAnnotation
from lib.evaluation.binding import validate_case
from lib.evaluation.captures import DocumentCapture
from lib.evaluation.identity import artifact_digest
from lib.evaluation.layout_scoring import continuation_scores, page_layout_scores
from lib.evaluation.manifest import EvaluationManifest
from lib.evaluation.text_scoring import counts, page_text_scores

SCORER_VERSION = "structura.native_parse_scorer.v1"
UNEVALUATED = (
    "source_pixel_support",
    "live_invocation_authenticity",
    "holdout_registry_authenticity",
    "classification",
    "typed_extraction",
    "canonical_correctness",
    "review_effort",
    "retrieval_relevance",
    "operational_recovery",
    "release_acceptance",
)
LIMITATIONS = (
    "Hashes establish consistency with the caller's manifest pin, not independent authenticity.",
    "Text uses NFC and whitespace tokenization with occurrence-aware contiguous-block alignment; "
    "it is not minimum edit distance, CER, or WER. Case, punctuation and digits are preserved.",
    "Text on pages with unresolved annotation regions is not evaluated; those pages remain in "
    "coverage totals. Partial reference scoring needs a future adjudicated alignment policy.",
    "Exact sensitive-text counts cover annotated literal values only, "
    "not all possible identifiers.",
    "Region matching is greedy, same-kind and one-to-one; segmentation differences can reduce "
    "layout scores independently of full-page text fidelity. IoU does not establish pixel support.",
    "Table cells match fixed grid positions; shifted/segmented rows and uncertain continuation "
    "labels need adjudication. Empty unannotated grid positions are not assumed absent cells.",
    "Only the single-page structura.page_parse.v1 raw-to-normalized contract is supported.",
    "No quality thresholds are ratified; computed diagnostics cannot pass a release gate.",
)


def score_evaluation(
    manifest: EvaluationManifest,
    annotations: list[DocumentAnnotation],
    captures: list[DocumentCapture],
    *,
    expected_manifest_sha256: str,
) -> dict[str, Any]:
    if artifact_digest(manifest) != expected_manifest_sha256:
        raise ValueError("Manifest differs from the separately supplied frozen identity.")
    annotation_map = {item.item_id: item for item in annotations}
    capture_map = {item.item_id: item for item in captures}
    expected = {case.item_id for case in manifest.cases}
    if (
        len(annotation_map) != len(annotations)
        or len(capture_map) != len(captures)
        or set(annotation_map) != expected
        or set(capture_map) != expected
    ):
        raise ValueError("Evaluation inputs must contain every frozen case exactly once.")
    documents = []
    for case in manifest.cases:
        annotation, capture = annotation_map[case.item_id], capture_map[case.item_id]
        validate_case(case, annotation, capture, manifest)
        documents.append(_score_document(annotation, capture))
    return {
        "schema_version": "structura.parse_score_report.v1",
        "scorer_version": SCORER_VERSION,
        "matching_policy": manifest.matching_policy,
        "evaluation_id": str(manifest.evaluation_id),
        "manifest_sha256": expected_manifest_sha256,
        "status": "computed",
        "threshold_policy": "not_ratified",
        "documents_expected": len(manifest.cases),
        "documents_scored": len(documents),
        "unevaluated_stages": {stage: "not_evaluated" for stage in UNEVALUATED},
        "limitations": list(LIMITATIONS),
        "documents": documents,
    }


def _score_document(annotation: DocumentAnnotation, capture: DocumentCapture) -> dict[str, Any]:
    pages: list[dict[str, Any]] = []
    continuation = []
    for gold, actual in zip(annotation.pages, capture.structure.pages, strict=True):
        chunks = tuple(
            chunk for chunk in capture.structure.chunks if chunk.page_number == gold.page_number
        )
        layout = page_layout_scores(gold, actual)
        continuation.extend(layout["tables"].pop("continuation_observations"))
        pages.append(
            {
                "page_number": gold.page_number,
                "state": actual.state,
                "text": page_text_scores(gold, actual, chunks),
                "layout": layout,
            }
        )
    states = Counter(page.state for page in capture.structure.pages)
    text_pages = [page["text"] for page in pages if page["text"]["status"] == "computed"]
    return {
        "item_id": annotation.item_id,
        "annotation_sha256": artifact_digest(annotation),
        "capture_sha256": artifact_digest(capture),
        "fixture_type": capture.fixture_type,
        "processing_run_id": str(capture.structure.processing_run_id),
        "parse_generation_id": str(capture.structure.parse_generation_id),
        "coverage": {
            "source_pages": len(annotation.pages),
            "inventoried_pages": len(pages),
            "state_counts": dict(sorted(states.items())),
            "reported_processed_pages": states["processed"],
            "reported_processed_fraction": states["processed"] / len(pages),
            "text_scored_pages": len(text_pages),
            "text_not_evaluated_pages": len(pages) - len(text_pages),
        },
        "parse_tokens": _sum_counts(text_pages, "parse_tokens"),
        "searchable_tokens": _sum_counts(text_pages, "searchable_tokens"),
        "continuation": continuation_scores(continuation),
        "pages": pages,
    }


def _sum_counts(pages: list[dict[str, Any]], metric: str) -> dict[str, Any]:
    return {
        "status": "computed" if pages else "not_evaluated",
        **counts(
            *(
                sum(page[metric][key] for page in pages)
                for key in ("expected", "observed", "matched")
            )
        ),
    }
