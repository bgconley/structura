from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

ACCEPTED_REVIEW_STATUSES = {"auto_accepted", "user_confirmed", "user_corrected"}
TRUTH_OBSERVATION_STATUSES = {"promoted", "auto_accepted", "user_confirmed", "user_corrected"}
REVIEW_STATUSES = {"needs_review", "proposed", "unreviewed"}

BLOCKED_PHASE9_MUTATION_KEYS = (
    "canonicalFacts",
    "canonicalFields",
    "canonicalLineItems",
    "canonicalObservations",
    "relationships",
    "documentRelationships",
    "folders",
    "folderIds",
    "primaryFolderId",
    "tags",
    "deadlines",
    "documentDeadlines",
    "reviewStatus",
    "reviewTasks",
)


def build_phase9_document_intake(document: Mapping[str, Any]) -> dict[str, Any]:
    truth = _truth_surface(document)
    review = _review_surface(document)
    debug = _debug_surface(document)
    quality = _document_quality(document, truth=truth, review=review)
    return {
        "documentId": _value(document, "id", "documentId"),
        "eligibility": phase9_document_eligibility(quality),
        "documentQuality": quality,
        "truth": truth,
        "review": review,
        "debug": debug,
        "mutationPolicy": {
            "readOnly": True,
            "blockedTargets": list(BLOCKED_PHASE9_MUTATION_KEYS),
        },
    }


def phase9_document_eligibility(document_quality: Mapping[str, Any]) -> str:
    if _value(document_quality, "operational_status", "operationalStatus") != "completed":
        return "analysis_disabled_operational_failure"
    if (
        _int(_value(document_quality, "canonical_fact_count", "canonicalFactCount")) == 0
        and _int(_value(document_quality, "candidate_count", "candidateCount")) == 0
    ):
        return "analysis_limited_no_extracted_facts"
    evidence_coverage = _float(
        _value(document_quality, "evidence_locator_coverage", "evidenceLocatorCoverage")
    )
    if evidence_coverage < 0.80:
        return "analysis_review_only_evidence_sparse"
    if bool(_value(document_quality, "has_admitted_artifact", "hasAdmittedArtifact")):
        return "analysis_disabled_artifact_regression"
    return "analysis_enabled_with_uncertainty"


def phase9_mutation_violations(output: Mapping[str, Any]) -> list[str]:
    found: list[str] = []
    _collect_mutation_keys(output, found)
    return found


def _truth_surface(document: Mapping[str, Any]) -> dict[str, Any]:
    canonical_fields = [
        _surface_item(field, surface="truth")
        for field in _rows(document, "fields", "canonicalFields")
        if _status(field, "reviewStatus", "review_status") in ACCEPTED_REVIEW_STATUSES
    ]
    canonical_line_items = [
        _surface_item(item, surface="truth")
        for item in _rows(document, "lineItems", "canonicalLineItems")
        if _status(item, "reviewStatus", "review_status") in ACCEPTED_REVIEW_STATUSES
    ]
    canonical_observations = [
        _surface_item(observation, surface="truth")
        for observation in _rows(document, "observations", "canonicalObservations")
        if _status(observation, "status") in TRUTH_OBSERVATION_STATUSES
    ]
    user_confirmed = [
        item
        for item in [*canonical_fields, *canonical_line_items, *canonical_observations]
        if _status(item, "reviewStatus", "review_status", "status")
        in {"user_confirmed", "user_corrected"}
        or _value(item, "sourceKind", "source_kind") == "human"
    ]
    return {
        "canonicalFields": canonical_fields,
        "canonicalLineItems": canonical_line_items,
        "canonicalObservations": canonical_observations,
        "userConfirmedFacts": user_confirmed,
    }


def _review_surface(document: Mapping[str, Any]) -> dict[str, Any]:
    field_candidates = [
        _uncertain_item(candidate)
        for candidate in _rows(document, "fieldCandidates")
        if _is_review_required(candidate)
    ]
    line_item_candidates = [
        _uncertain_item(candidate)
        for candidate in _rows(document, "lineItemCandidates")
        if _is_review_required(candidate)
    ]
    observation_candidates = [
        _uncertain_item(candidate)
        for candidate in _rows(document, "observations", "observationCandidates")
        if _is_review_required(candidate)
    ]
    rejections = [
        _surface_item(event, surface="review", uncertainty_label="rejected_not_truth")
        for event in _rows(document, "admissionEvents", "candidateAdmissionEvents")
        if str(_value(event, "decision") or "").startswith("rejected")
    ]
    review_items = [*field_candidates, *line_item_candidates, *observation_candidates]
    return {
        "fieldCandidates": field_candidates,
        "lineItemCandidates": line_item_candidates,
        "observationCandidates": observation_candidates,
        "candidateRejections": rejections,
        "uncertainObservations": observation_candidates,
        "evidenceRefs": _evidence_refs(review_items),
        "plannerExplanations": _planner_explanations(document),
        "qualitySignals": _quality_signals(document),
    }


def _debug_surface(document: Mapping[str, Any]) -> dict[str, Any]:
    available: set[str] = set()
    refs: list[dict[str, Any]] = []
    for extraction in _rows(document, "semanticRegionExtractions"):
        ref: dict[str, Any] = {
            "extractionId": _value(extraction, "id"),
            "semanticType": _value(extraction, "semanticType", "semantic_type"),
        }
        if _value(extraction, "promptVersion", "prompt_version"):
            available.add("prompt_versions")
        normalization = _mapping(_value(extraction, "normalization", "normalization_json"))
        metadata = _mapping(_value(extraction, "metadata", "metadata_json"))
        if _value(normalization, "regionEnvelope", "region_envelope"):
            available.add("region_envelope")
        if _value(normalization, "repairs") or _value(
            _mapping(_value(normalization, "regionEnvelope", "region_envelope")),
            "repairs",
        ):
            available.add("normalization_repairs")
        if _value(metadata, "visualInputPlan", "visual_input_plan"):
            available.add("visual_plan_internals")
        if _value(metadata, "adapterTrace", "adapter_trace"):
            available.add("adapter_traces")
        if _value(metadata, "rawModelOutput", "raw_model_output"):
            available.add("raw_model_output")
        if _value(extraction, "modelOutputPayload", "model_output_payload"):
            available.add("model_output_payloads")
        refs.append({key: value for key, value in ref.items() if value not in (None, "")})
    return {
        "excludedFromTruth": True,
        "availableSurfaces": sorted(available),
        "surfaceRefs": refs,
    }


def _document_quality(
    document: Mapping[str, Any],
    *,
    truth: Mapping[str, list[Mapping[str, Any]]],
    review: Mapping[str, Any],
) -> dict[str, Any]:
    explicit = _mapping(_value(document, "documentQuality", "document_quality"))
    canonical_count = sum(
        len(truth.get(key, []))
        for key in ("canonicalFields", "canonicalLineItems", "canonicalObservations")
    )
    candidate_count = sum(
        len(review.get(key, []))
        for key in ("fieldCandidates", "lineItemCandidates", "observationCandidates")
    )
    return {
        "operational_status": _value(explicit, "operational_status", "operationalStatus")
        or _operational_status(document),
        "canonical_fact_count": _value(explicit, "canonical_fact_count", "canonicalFactCount")
        if _value(explicit, "canonical_fact_count", "canonicalFactCount") is not None
        else canonical_count,
        "candidate_count": _value(explicit, "candidate_count", "candidateCount")
        if _value(explicit, "candidate_count", "candidateCount") is not None
        else candidate_count,
        "evidence_locator_coverage": _value(
            explicit,
            "evidence_locator_coverage",
            "evidenceLocatorCoverage",
        )
        if _value(explicit, "evidence_locator_coverage", "evidenceLocatorCoverage") is not None
        else _evidence_locator_coverage([truth, review]),
        "has_admitted_artifact": _value(
            explicit,
            "has_admitted_artifact",
            "hasAdmittedArtifact",
        )
        if _value(explicit, "has_admitted_artifact", "hasAdmittedArtifact") is not None
        else _has_admitted_artifact(document),
    }


def _operational_status(document: Mapping[str, Any]) -> str:
    extraction_statuses = {
        str(_value(row, "status") or "")
        for row in [*_rows(document, "extractions"), *_rows(document, "semanticRegionExtractions")]
    }
    failed_statuses = {"failed", "dead_letter", "pipeline_failed"}
    if any(status in failed_statuses for status in extraction_statuses):
        return "pipeline_failed"
    return "completed"


def _has_admitted_artifact(document: Mapping[str, Any]) -> bool:
    for event in _rows(document, "admissionEvents", "candidateAdmissionEvents"):
        decision = str(_value(event, "decision") or "")
        reasons = [str(reason) for reason in _list(_value(event, "reasons"))]
        if decision.startswith("admitted") and "prompt_or_schema_echo" in reasons:
            return True
    return False


def _surface_item(
    item: Mapping[str, Any],
    *,
    surface: str,
    uncertainty_label: str | None = None,
) -> dict[str, Any]:
    payload = dict(item)
    payload["surface"] = surface
    if uncertainty_label:
        payload["uncertaintyLabel"] = uncertainty_label
    return payload


def _uncertain_item(item: Mapping[str, Any]) -> dict[str, Any]:
    return _surface_item(
        item,
        surface="review",
        uncertainty_label="uncertain_review_required",
    )


def _is_review_required(item: Mapping[str, Any]) -> bool:
    return _status(item, "status", "reviewStatus", "review_status") in REVIEW_STATUSES


def _status(item: Mapping[str, Any], *keys: str) -> str:
    value = _value(item, *keys)
    return str(value or "").strip()


def _evidence_refs(items: Sequence[Mapping[str, Any]]) -> list[Any]:
    refs: list[Any] = []
    for item in items:
        refs.extend(_list(_value(item, "evidence", "evidenceRefs")))
    return refs


def _planner_explanations(document: Mapping[str, Any]) -> list[dict[str, Any]]:
    explanations: list[dict[str, Any]] = []
    for extraction in _rows(document, "semanticRegionExtractions"):
        reason = _value(extraction, "reason")
        metadata = _mapping(_value(extraction, "metadata", "metadata_json"))
        planner_note = _value(metadata, "plannerNote", "planner_note", "must_extract_reason")
        if reason or planner_note:
            explanations.append(
                {
                    "semanticType": _value(extraction, "semanticType", "semantic_type"),
                    "reason": reason or planner_note,
                }
            )
    return explanations


def _quality_signals(document: Mapping[str, Any]) -> dict[str, Any]:
    page_signals = [
        _value(page, "qualitySignals", "quality_signals")
        for page in _rows(document, "pages")
        if _value(page, "qualitySignals", "quality_signals")
    ]
    return {
        "document": _value(document, "qualitySummary", "quality_summary") or {},
        "pages": page_signals,
    }


def _evidence_locator_coverage(containers: list[Any]) -> float:
    evidence_refs = _collect_evidence(containers)
    if not evidence_refs:
        return 1.0
    concrete = sum(1 for evidence in evidence_refs if _has_concrete_locator(evidence))
    return round(concrete / len(evidence_refs), 4)


def _collect_evidence(value: Any) -> list[Any]:
    if isinstance(value, Mapping):
        evidence = _value(value, "evidence", "evidenceRefs")
        evidence_refs = list(_list(evidence))
        for item in value.values():
            evidence_refs.extend(_collect_evidence(item))
        return evidence_refs
    if isinstance(value, list):
        refs: list[Any] = []
        for item in value:
            refs.extend(_collect_evidence(item))
        return refs
    return []


def _has_concrete_locator(evidence: Any) -> bool:
    if not isinstance(evidence, Mapping):
        return False
    if any(
        _value(evidence, key) not in (None, "", [])
        for key in ("bbox", "elementId", "element_id", "tableId", "table_id")
    ):
        return True
    semantic_region_id = _value(evidence, "semanticRegionId", "semantic_region_id")
    page_locator = _value(evidence, "pageId", "page_id", "pageNumber", "page_number")
    return semantic_region_id not in (None, "", []) and page_locator not in (
        None,
        "",
        [],
    )


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


def _rows(mapping: Mapping[str, Any], *keys: str) -> list[Mapping[str, Any]]:
    for key in keys:
        value = _value(mapping, key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, Mapping)]
    return []


def _value(mapping: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in mapping:
            return mapping[key]
    return None


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _int(value: Any) -> int:
    if value in (None, ""):
        return 0
    return int(value)


def _float(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    return float(value)
