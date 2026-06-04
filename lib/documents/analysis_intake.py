from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from lib.documents import analysis_mutation_policy
from lib.extraction.evidence import is_concrete_evidence_ref

ACCEPTED_REVIEW_STATUSES = {"auto_accepted", "user_confirmed", "user_corrected"}
TRUTH_OBSERVATION_STATUSES = {"promoted", "auto_accepted", "user_confirmed", "user_corrected"}
REVIEW_STATUSES = {"needs_review", "proposed", "unreviewed"}
ANALYSIS_TARGET_JOB_QUEUES = {
    "docling",
    "semantic-annotations",
    "extraction",
    "visual-embeddings",
}
OPERATIONAL_FAILURE_STATUSES = {"failed", "dead_letter", "pipeline_failed"}
ADMITTED_ARTIFACT_REASONS = {
    "fake_schema_line_item",
    "missing_description",
    "placeholder_field_name",
    "placeholder_or_null_value",
    "prompt_or_schema_echo",
}


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
            "blockedTargets": list(analysis_mutation_policy.BLOCKED_PHASE9_MUTATION_KEYS),
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
    return analysis_mutation_policy.phase9_mutation_violations(output)


def _truth_surface(document: Mapping[str, Any]) -> dict[str, Any]:
    canonical_fields = [
        _surface_item(field, surface="truth")
        for field in _merged_rows(document, "fields", "canonicalFields")
        if _status(field, "reviewStatus", "review_status") in ACCEPTED_REVIEW_STATUSES
    ]
    canonical_line_items = [
        _surface_item(item, surface="truth")
        for item in _merged_rows(document, "lineItems", "canonicalLineItems")
        if _status(item, "reviewStatus", "review_status") in ACCEPTED_REVIEW_STATUSES
    ]
    canonical_observations = [
        _surface_item(observation, surface="truth")
        for observation in _merged_rows(document, "observations", "canonicalObservations")
        if _status(observation, "status") in TRUTH_OBSERVATION_STATUSES
    ]
    explicit_user_confirmed = [
        _surface_item(fact, surface="truth")
        for fact in _merged_rows(document, "userConfirmedFacts", "user_confirmed_facts")
    ]
    derived_user_confirmed = [
        item
        for item in [*canonical_fields, *canonical_line_items, *canonical_observations]
        if _status(item, "reviewStatus", "review_status", "status")
        in {"user_confirmed", "user_corrected"}
        or _value(item, "sourceKind", "source_kind") == "human"
    ]
    user_confirmed = _dedupe_rows([*explicit_user_confirmed, *derived_user_confirmed])
    return {
        "canonicalFields": canonical_fields,
        "canonicalLineItems": canonical_line_items,
        "canonicalObservations": canonical_observations,
        "userConfirmedFacts": user_confirmed,
    }


def _review_surface(document: Mapping[str, Any]) -> dict[str, Any]:
    field_candidates = [
        _uncertain_item(candidate)
        for candidate in _review_required_rows(
            document,
            "fieldCandidates",
            "fields",
            "canonicalFields",
        )
    ]
    line_item_candidates = [
        _uncertain_item(candidate)
        for candidate in _review_required_rows(
            document,
            "lineItemCandidates",
            "lineItems",
            "canonicalLineItems",
        )
    ]
    observation_candidates = [
        _uncertain_item(candidate)
        for candidate in _review_required_rows(
            document,
            "observationCandidates",
            "observations",
            "canonicalObservations",
        )
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
        raw_output = _mapping(
            _value(extraction, "rawOutputJson", "raw_output_json", "rawOutput", "raw_output")
        )
        if _value(normalization, "regionEnvelope", "region_envelope"):
            available.add("region_envelope")
        if _value(normalization, "repairs") or _value(
            _mapping(_value(normalization, "regionEnvelope", "region_envelope")),
            "repairs",
        ):
            available.add("normalization_repairs")
        debug_sources = (metadata, raw_output)
        if raw_output:
            available.add("raw_model_output")
        if any(_value(source, "visualInputPlan", "visual_input_plan") for source in debug_sources):
            available.add("visual_plan_internals")
        if any(_value(source, "adapterTrace", "adapter_trace") for source in debug_sources):
            available.add("adapter_traces")
        if any(_value(source, "rawModelOutput", "raw_model_output") for source in debug_sources):
            available.add("raw_model_output")
        if _value(extraction, "modelOutputPayload", "model_output_payload") or any(
            _value(source, "modelOutputPayload", "model_output_payload") for source in debug_sources
        ):
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
        for key in (
            "canonicalFields",
            "canonicalLineItems",
            "canonicalObservations",
            "userConfirmedFacts",
        )
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
        str(_value(row, "status") or "").lower()
        for row in [*_rows(document, "extractions"), *_rows(document, "semanticRegionExtractions")]
    }
    if any(status in OPERATIONAL_FAILURE_STATUSES for status in extraction_statuses):
        return "pipeline_failed"
    for job in _rows(document, "jobs"):
        queue_name = str(_value(job, "queueName", "queue_name", "queue") or "").lower()
        job_status = str(_value(job, "status") or "").lower()
        if queue_name in ANALYSIS_TARGET_JOB_QUEUES and job_status in OPERATIONAL_FAILURE_STATUSES:
            return "pipeline_failed"
    return "completed"


def _has_admitted_artifact(document: Mapping[str, Any]) -> bool:
    for event in _rows(document, "admissionEvents", "candidateAdmissionEvents"):
        decision = str(_value(event, "decision") or "")
        reasons = [str(reason) for reason in _list(_value(event, "reasons"))]
        if decision.startswith("admitted") and any(
            reason in ADMITTED_ARTIFACT_REASONS for reason in reasons
        ):
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
        refs.extend(
            _uncertain_evidence_ref(ref) for ref in _list(_value(item, "evidence", "evidenceRefs"))
        )
    return refs


def _planner_explanations(document: Mapping[str, Any]) -> list[dict[str, Any]]:
    explanations: list[dict[str, Any]] = []
    for extraction in _rows(document, "semanticRegionExtractions"):
        reason = _value(extraction, "reason")
        metadata = _mapping(_value(extraction, "metadata", "metadata_json"))
        planner_note = _value(metadata, "plannerNote", "planner_note", "must_extract_reason")
        if reason or planner_note:
            explanations.append(
                _surface_item(
                    {
                        "semanticType": _value(extraction, "semanticType", "semantic_type"),
                        "reason": reason or planner_note,
                    },
                    surface="review",
                    uncertainty_label="uncertain_planner_explanation",
                )
            )
    return explanations


def _quality_signals(document: Mapping[str, Any]) -> dict[str, Any]:
    page_signals = [
        _value(page, "qualitySignals", "quality_signals")
        for page in _rows(document, "pages")
        if _value(page, "qualitySignals", "quality_signals")
    ]
    return _surface_item(
        {
            "document": _value(document, "qualitySummary", "quality_summary") or {},
            "pages": page_signals,
        },
        surface="review",
        uncertainty_label="uncertain_quality_signal",
    )


def _uncertain_evidence_ref(ref: Any) -> Any:
    if isinstance(ref, Mapping):
        return _surface_item(
            ref,
            surface="review",
            uncertainty_label="uncertain_evidence_ref",
        )
    return {
        "value": ref,
        "surface": "review",
        "uncertaintyLabel": "uncertain_evidence_ref",
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
    return is_concrete_evidence_ref(dict(evidence))


def _review_required_rows(mapping: Mapping[str, Any], *keys: str) -> list[Mapping[str, Any]]:
    rows: list[Mapping[str, Any]] = []
    seen_ids: set[str] = set()
    for key in keys:
        for row in _rows(mapping, key):
            if not _is_review_required(row):
                continue
            row_id = _value(row, "id")
            if row_id not in (None, ""):
                row_id_text = str(row_id)
                if row_id_text in seen_ids:
                    continue
                seen_ids.add(row_id_text)
            rows.append(row)
    return rows


def _merged_rows(mapping: Mapping[str, Any], *keys: str) -> list[Mapping[str, Any]]:
    rows: list[Mapping[str, Any]] = []
    seen_ids: set[str] = set()
    for key in keys:
        for row in _rows(mapping, key):
            row_id = _value(row, "id")
            if row_id not in (None, ""):
                row_id_text = str(row_id)
                if row_id_text in seen_ids:
                    continue
                seen_ids.add(row_id_text)
            rows.append(row)
    return rows


def _dedupe_rows(rows: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    deduped: list[Mapping[str, Any]] = []
    seen_ids: set[str] = set()
    for row in rows:
        row_id = _value(row, "id")
        if row_id not in (None, ""):
            row_id_text = str(row_id)
            if row_id_text in seen_ids:
                continue
            seen_ids.add(row_id_text)
        deduped.append(row)
    return deduped


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
