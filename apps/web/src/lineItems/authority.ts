import type {CandidateLines, CanonicalLine, CanonicalLines, ExtractionIdentity, LineAssignment, LineDecision, LineProjection, LineRequest, LineResult} from "./types";
import {digest, evidence, natural, nullableText, nullableUuid, object, requireValue, sameSlot, slot, slotKey, text, timestamp, unique, uuid, values} from "./validation";

export function projection(v: unknown, documentId: string): v is LineProjection {
  return object(v) && v.schemaVersion === "accepted_fact_projection.v1" && v.documentId === documentId
    && ["accepted_fields.v1", "accepted_fields_and_lines.v1"].includes(String(v.acceptedFactBasisSchemaVersion))
    && (v.state === "unestablished" ? v.acceptedFactRevision === 0 && v.projectionRevision === 0 && v.acceptedFactsSha256 === null && v.indexedMetadataSha256 === null
      : v.state === "current" && natural(v.acceptedFactRevision) && v.acceptedFactRevision > 0 && natural(v.projectionRevision)
        && v.projectionRevision >= v.acceptedFactRevision && digest(v.acceptedFactsSha256) && digest(v.indexedMetadataSha256));
}
export function canonical(v: unknown, documentId: string): v is CanonicalLine {
  return object(v) && uuid(v.id) && v.documentId === documentId && slot(v) && values(v)
    && nullableUuid(v.selectedCandidateId) && text(v.sourceKind) && text(v.reviewStatus) && evidence(v.evidence)
    && object(v.validation) && (v.acceptedAt === null || timestamp(v.acceptedAt)) && timestamp(v.updatedAt) && typeof v.selected === "boolean";
}
function decision(v: unknown, documentId: string): v is LineDecision {
  return object(v) && uuid(v.id) && v.documentId === documentId && slot(v) && uuid(v.canonicalLineItemId) && uuid(v.revision)
    && ["confirmed", "corrected", "rejected", "protected_legacy"].includes(String(v.disposition))
    && ["live_review", "legacy_current_line"].includes(String(v.origin)) && nullableUuid(v.actorUserId) && nullableUuid(v.reviewEventId)
    && nullableUuid(v.decisionEventId) && (v.decidedAt === null || timestamp(v.decidedAt)) && timestamp(v.recordedAt)
    && (v.origin !== "live_review" || (["confirmed", "rejected"].includes(String(v.disposition)) && uuid(v.decisionEventId) && timestamp(v.decidedAt)));
}
function assignment(v: unknown): v is LineAssignment {
  return object(v) && uuid(v.sourceCandidateId) && typeof v.currentlySelected === "boolean"
    && (v.state === "legacy_conflict" ? v.canonicalLineItemId === null && v.target === null && !v.currentlySelected
      : v.state === "assigned" && uuid(v.canonicalLineItemId) && object(v.target) && slot(v.target));
}
export function extraction(v: unknown, documentId: string): v is ExtractionIdentity | null {
  return v === null || (object(v) && uuid(v.id) && v.documentId === documentId
    && ["schemaName", "schemaVersion", "sourceEngine", "extractionScope"].every((key) => text(v[key]) && !!v[key])
    && ["modelName", "modelVersion", "promptVersion"].every((key) => nullableText(v[key]))
    && nullableUuid(v.semanticAnnotationId) && nullableUuid(v.sourceSemanticRegionId));
}
export function parseCanonicalLines(v: unknown, documentId: string): CanonicalLines {
  requireValue(object(v) && v.authorityVersion === "line_item_authority.v1" && v.documentId === documentId
    && Array.isArray(v.items) && v.items.every((item) => canonical(item, documentId))
    && Array.isArray(v.decisions) && v.decisions.every((item) => decision(item, documentId))
    && Array.isArray(v.sourceAssignments) && v.sourceAssignments.every(assignment) && projection(v.projection, documentId));
  const result = v as CanonicalLines;
  requireValue(unique(result.items, (item) => item.id) && unique(result.items, slotKey)
    && unique(result.decisions, (item) => item.id) && unique(result.decisions, slotKey)
    && unique(result.sourceAssignments, (item) => item.sourceCandidateId));
  for (const item of result.items) {
    const current = result.decisions.find((entry) => entry.canonicalLineItemId === item.id);
    const accepted = ["auto_accepted", "user_confirmed", "user_corrected"].includes(item.reviewStatus)
      && (!current || ["confirmed", "corrected"].includes(current.disposition));
    requireValue(item.selected === accepted);
  }
  for (const entry of result.decisions) requireValue(result.items.some((item) => item.id === entry.canonicalLineItemId && sameSlot(item, entry)));
  for (const entry of result.sourceAssignments) {
    if (entry.state === "legacy_conflict") continue;
    const item = result.items.find((line) => line.id === entry.canonicalLineItemId);
    requireValue(item && entry.target && sameSlot(item, entry.target)
      && entry.currentlySelected === (item.selected && item.selectedCandidateId === entry.sourceCandidateId));
  }
  // New selected candidates require a lifetime binding; legacy conflicts remain explicitly visible.
  for (const item of result.items) if (item.selectedCandidateId) {
    requireValue(result.sourceAssignments.some((entry) => entry.sourceCandidateId === item.selectedCandidateId
      && (entry.state === "legacy_conflict" || entry.canonicalLineItemId === item.id)));
  }
  return result;
}
export function parseCandidateLines(v: unknown, documentId: string, candidateId?: string): CandidateLines {
  requireValue(object(v) && v.authorityVersion === "line_item_authority.v1" && v.documentId === documentId && Array.isArray(v.items));
  const reasons = ["eligible", "source_missing", "source_superseded", "source_failed", "source_binding_invalid", "evidence_incomplete", "legacy_assignment_conflict", "unsupported_candidate_state"];
  for (const item of v.items) {
    requireValue(object(item) && uuid(item.id) && item.documentId === documentId && (!candidateId || item.id === candidateId)
      && slot(item) && values(item) && nullableUuid(item.extractionId) && nullableText(item.candidateGroup)
      && uuid(item.candidateVersion) && digest(item.sourceSnapshotSha256) && nullableUuid(item.candidateDecisionRevision)
      && text(item.sourceEngine) && text(item.status) && evidence(item.evidence) && extraction(item.extraction, documentId)
      && (!item.extraction || item.extraction.id === item.extractionId));
    const eligible = item.publicationEligibility, validation = item.validation;
    requireValue(object(eligible) && reasons.includes(String(eligible.reason)) && eligible.eligible === (eligible.reason === "eligible")
      && object(validation) && typeof validation.recorded === "boolean" && [true, false, null].includes(validation.needsReview as null)
      && natural(validation.unrepresentedCheckCount) && Array.isArray(validation.checks)
      && validation.checks.every((check) => object(check) && text(check.code) && /^[A-Za-z0-9_.:-]{1,100}$/.test(check.code)
        && ["passed", "failed", "warning", "not_applicable"].includes(String(check.status)))
      && (item.sourceAssignment === null || (assignment(item.sourceAssignment) && item.sourceAssignment.sourceCandidateId === item.id)));
    if (eligible.eligible) requireValue(item.extraction && (item.evidence as unknown[]).length > 0);
    const target = item.suggestedVacantTarget;
    requireValue(target === null || (object(target) && slot(target) && target.lineItemType === item.lineItemType
      && target.canonicalLineItemId === null && target.expectedCanonicalUpdatedAt === null && target.expectedLineDecisionRevision === null
      && eligible.eligible && item.sourceAssignment === null));
  }
  const result = v as CandidateLines;
  requireValue(unique(result.items, (item) => item.id));
  return result;
}
export function parseLineResult(v: unknown, documentId: string, request: LineRequest): LineResult {
  requireValue(object(v) && v.operation === request.operation && uuid(v.eventId) && projection(v.projection, documentId)
    && (v.canonicalItem === null || canonical(v.canonicalItem, documentId)) && (v.lineDecision === null || decision(v.lineDecision, documentId)));
  if (request.operation === "reject_candidate") requireValue(v.canonicalItem === null && v.lineDecision === null);
  else {
    requireValue(canonical(v.canonicalItem, documentId) && decision(v.lineDecision, documentId)
      && sameSlot(v.canonicalItem, request.target) && v.lineDecision.canonicalLineItemId === v.canonicalItem.id
      && sameSlot(v.lineDecision, request.target) && v.lineDecision.decisionEventId === v.eventId
      && v.lineDecision.disposition === (request.operation === "reject_selected" ? "rejected" : "confirmed")
      && (request.operation === "create" || v.canonicalItem.id === request.target.canonicalLineItemId)
      && v.canonicalItem.selected === (request.operation !== "reject_selected"));
    if (request.operation !== "reject_selected") requireValue(v.canonicalItem.selectedCandidateId === request.source.candidateId);
  }
  const c = v.candidateDecision;
  if (request.operation !== "reject_selected" || c !== null) {
    requireValue(object(c) && uuid(c.id) && c.documentId === documentId && uuid(c.sourceCandidateId) && uuid(c.revision)
      && c.disposition === (["create", "replace"].includes(request.operation) ? "accepted" : "rejected") && c.origin === "live_review" && digest(c.sourceSnapshotSha256)
      && nullableUuid(c.actorUserId) && nullableUuid(c.reviewEventId) && timestamp(c.decidedAt) && timestamp(c.recordedAt));
    if (request.operation !== "reject_selected") requireValue(c.sourceCandidateId === request.source.candidateId
      && c.sourceSnapshotSha256 === request.source.expectedSourceSnapshotSha256);
  }
  return v as LineResult;
}
