import type {Page} from "@playwright/test";
import type {CanonicalLine, CanonicalLines, LineCandidate, LineDecision, LineHistoryEntry, LineProjection, LineRequest, LineResult, LineValues, SourceSnapshot} from "../../../apps/web/src/lineItems/types";
import {existingDocument, seededReviewTasks} from "./structuraFixtures";

export const lineId = (number: number) => `abababab-abab-4bab-8bab-${String(number).padStart(12, "0")}`;
export const lineTime = "2026-09-07T10:11:12.123456Z";
export const lineValues: LineValues = {code: "99213", codeSystem: "CPT", serviceDate: "2026-01-26", description: "Office evaluation",
  quantity: "1.2345", unit: "visit", unitPrice: "0.0000", grossAmount: "99999999999999.9999", discountAmount: "-12.3400",
  taxAmount: null, netAmount: "120.0100", allowedAmount: "220.1234", planPaidAmount: "100.1134", currency: "EUR", categoryHint: null};
export function lineProjection(documentId: string): LineProjection {
  return {schemaVersion: "accepted_fact_projection.v1", documentId, state: "current", acceptedFactRevision: 1, projectionRevision: 1,
    acceptedFactsSha256: "a".repeat(64), indexedMetadataSha256: "b".repeat(64), acceptedFactBasisSchemaVersion: "accepted_fields_and_lines.v1"};
}
export function lineCandidate(documentId: string, number = 1): LineCandidate {
  const extractionId = lineId(100 + number);
  return {...lineValues, id: lineId(number), documentId, extractionId, lineItemType: "service_line", ordinal: 1,
    candidateGroup: "medical_eob", candidateVersion: lineId(200 + number), sourceSnapshotSha256: "c".repeat(64), candidateDecisionRevision: null,
    sourceEngine: "granite4_vision", status: "needs_review", evidence: [{pageNumber: 1, sourceEngine: "human", sourceText: "Office evaluation · evidence"}],
    extraction: {id: extractionId, documentId, schemaName: "medical_eob", schemaVersion: "v1", sourceEngine: "granite4_vision",
      modelName: "Recorded extraction model", modelVersion: "fixture", promptVersion: "fixture.v1", extractionScope: number === 1 ? "semantic_region" : "aggregate",
      semanticAnnotationId: lineId(110), sourceSemanticRegionId: number === 1 ? lineId(111) : null},
    validation: {recorded: true, needsReview: true, checks: [{code: "amount_reconciliation", status: "warning"}], unrepresentedCheckCount: 0},
    publicationEligibility: {eligible: true, reason: "eligible"}, sourceAssignment: null,
    suggestedVacantTarget: {lineItemType: "service_line", ordinal: 26, canonicalLineItemId: null, expectedCanonicalUpdatedAt: null, expectedLineDecisionRevision: null}};
}
export function canonicalLine(documentId: string, number = 1): CanonicalLine {
  return {...lineValues, id: lineId(300 + number), documentId, lineItemType: "service_line", ordinal: number,
    description: `Recorded service ${number}`, selectedCandidateId: null, sourceKind: "human", reviewStatus: "user_confirmed",
    evidence: [{pageNumber: 1, sourceEngine: "human", sourceText: `Evidence for recorded service ${number}`}],
    validation: {recorded: true}, acceptedAt: lineTime, updatedAt: lineTime, selected: true};
}
export function lineDecision(item: CanonicalLine): LineDecision {
  return {id: lineId(400 + item.ordinal), documentId: item.documentId, lineItemType: item.lineItemType, ordinal: item.ordinal,
    canonicalLineItemId: item.id, revision: lineId(500 + item.ordinal), disposition: item.selected ? "confirmed" : "rejected", origin: "live_review",
    actorUserId: lineId(900), reviewEventId: null, decisionEventId: lineId(600 + item.ordinal), decidedAt: lineTime, recordedAt: lineTime};
}
export function canonicalLines(documentId: string, items: CanonicalLine[] = []): CanonicalLines {
  return {authorityVersion: "line_item_authority.v1", documentId, items, decisions: items.map(lineDecision), sourceAssignments: [], projection: lineProjection(documentId)};
}
export function lineHistoryEntry(item: CanonicalLine): LineHistoryEntry {
  return {id: lineId(700 + item.ordinal), documentId: item.documentId, canonicalLineItemId: item.id, sourceCandidateId: null,
    operation: "reject_selected", coverage: "complete", before: {canonical: item, source: null, sourceCoverage: "legacy_unestablished"},
    after: {canonical: {...item, selected: false, reviewStatus: "rejected"}, source: null, sourceCoverage: "legacy_unestablished"},
    source: null, legacySummary: null, actorLabel: "Deleted reviewer", occurredAt: lineTime, comment: "Recorded decision"};
}

export const lineSourceSnapshot = (candidate: LineCandidate): SourceSnapshot => {
  const selected = Object.fromEntries(Object.keys(lineValues).map((key) => [key, candidate[key as keyof LineValues]])) as LineValues;
  return {schemaVersion: "line_item_source.v1", candidate: {...selected, id: candidate.id, documentId: candidate.documentId,
    extractionId: candidate.extractionId, sourceEngine: candidate.sourceEngine, lineItemType: candidate.lineItemType, candidateGroup: candidate.candidateGroup, ordinal: candidate.ordinal},
  extraction: candidate.extraction, original: {id: lineId(950), sha256: "d".repeat(64)}, evidence: candidate.evidence,
  validationSha256: "e".repeat(64), storedEvidenceSha256: "f".repeat(64)};
};
export async function installLineReviewMock(page: Page, count = 25) {
  const documentId = existingDocument.id;
  const candidates = [lineCandidate(documentId), {...lineCandidate(documentId, 2), description: "Aggregate alternative"}];
  const authority = canonicalLines(documentId, Array.from({length: count}, (_, index) => canonicalLine(documentId, index + 1)));
  const tasks = candidates.map((candidate, index) => ({...seededReviewTasks()[0], id: lineId(980 + index), documentId,
    taskType: "line_item_review", fieldPath: `line_items.service_line.${candidate.ordinal}`, rationale: candidate.description,
    metadata: {lineItemCandidateId: candidate.id, lineItemType: candidate.lineItemType, ordinal: candidate.ordinal}}));
  const state = {documentId, candidates, authority, tasks, requests: [] as LineRequest[], history: [] as LineHistoryEntry[],
    failRead: false, failSave: 0, loseResponse: false};
  await page.route("**/api/v1/review-tasks?*", (route) => route.fulfill({json: {items: tasks}}));
  await page.route("**/api/v1/review-tasks/*", (route) => {
    const task = tasks.find((item) => item.id === route.request().url().split("/").pop());
    return route.fulfill({status: task ? 200 : 404, json: task ?? {detail: "Not found"}});
  });
  await page.route(`**/api/v1/documents/${documentId}/*`, async (route) => {
    const url = new URL(route.request().url()), resource = url.pathname.split("/").pop();
    if (!["canonical-line-items", "line-item-candidates", "line-item-decisions", "line-item-history"].includes(resource!)) return route.fallback();
    if (resource === "canonical-line-items") return route.fulfill(state.failRead ? {status: 503, json: {detail: "Line read temporarily unavailable"}} : {json: authority});
    if (resource === "line-item-candidates") return route.fulfill({json: {authorityVersion: "line_item_authority.v1", documentId,
      items: candidates.filter((item) => !url.searchParams.has("candidateId") || item.id === url.searchParams.get("candidateId"))}});
    if (resource === "line-item-history") {
      const matching = state.history.filter((entry) => url.searchParams.has("canonicalLineItemId")
        ? entry.canonicalLineItemId === url.searchParams.get("canonicalLineItemId") : entry.sourceCandidateId === url.searchParams.get("sourceCandidateId"));
      const offset = url.searchParams.get("cursor") === "earlier-page" ? 20 : 0;
      return route.fulfill({json: {documentId, nextCursor: offset === 0 && matching.length > 20 ? "earlier-page" : null, items: matching.slice(offset, offset + 20)}});
    }
    const request = route.request().postDataJSON() as LineRequest;
    state.requests.push(request);
    if (state.failSave) return route.fulfill({status: state.failSave, json: {detail: "This line changed. Reload it before saving."}});
    const eventId = lineId(1000 + state.requests.length), revision = lineId(1100 + state.requests.length);
    let source = "source" in request ? candidates.find((item) => item.id === request.source.candidateId) : undefined;
    const old = "target" in request ? authority.items.find((item) => item.id === request.target.canonicalLineItemId) : undefined;
    const before = old ? structuredClone(old) : null;
    if (request.operation === "reject_selected") source = candidates.find((item) => item.id === old?.selectedCandidateId);
    let item: CanonicalLine | null = old ?? null;
    if (request.operation === "create" || request.operation === "replace") {
      const values = Object.fromEntries(Object.keys(lineValues).map((key) => [key, source![key as keyof LineValues]]));
      item = {...canonicalLine(documentId, request.target.ordinal), ...values, id: old?.id ?? lineId(300 + request.target.ordinal),
        selectedCandidateId: source!.id, sourceKind: "candidate", updatedAt: `2026-09-07T10:12:${String(state.requests.length).padStart(2, "0")}.123456Z`, evidence: source!.evidence};
      const index = authority.items.findIndex((entry) => entry.id === item!.id);
      if (index < 0) authority.items.push(item); else authority.items[index] = item;
      const assignment = {sourceCandidateId: source!.id, state: "assigned" as const, canonicalLineItemId: item.id,
        target: {lineItemType: item.lineItemType, ordinal: item.ordinal}, currentlySelected: true};
      if (!authority.sourceAssignments.some((entry) => entry.sourceCandidateId === source!.id)) authority.sourceAssignments.push(assignment);
      source!.sourceAssignment = assignment;
      source!.suggestedVacantTarget = null;
    } else if (request.operation === "reject_selected" && item) { item.reviewStatus = "rejected"; item.selected = false; item.updatedAt = `2026-09-07T10:13:${String(state.requests.length).padStart(2, "0")}.123456Z`; }
    for (const assignment of authority.sourceAssignments) {
      assignment.currentlySelected = authority.items.some((entry) => entry.id === assignment.canonicalLineItemId && entry.selected && entry.selectedCandidateId === assignment.sourceCandidateId);
      const candidate = candidates.find((entry) => entry.id === assignment.sourceCandidateId);
      if (candidate) candidate.sourceAssignment = assignment;
    }
    const selected = request.operation === "create" || request.operation === "replace";
    const candidateDecision = source ? {id: lineId(1200 + state.requests.length), documentId, sourceCandidateId: source.id, revision,
      disposition: selected ? "accepted" as const : "rejected" as const, origin: "live_review" as const, sourceSnapshotSha256: source.sourceSnapshotSha256,
      actorUserId: lineId(900), reviewEventId: null, decidedAt: lineTime, recordedAt: lineTime} : null;
    if (source) { source.status = selected ? "accepted" : "rejected"; source.candidateVersion = revision; source.candidateDecisionRevision = revision; }
    const decision = item ? {...lineDecision(item), revision, decisionEventId: eventId} : null;
    if (decision) authority.decisions = [...authority.decisions.filter((entry) => entry.canonicalLineItemId !== item!.id), decision];
    authority.projection.projectionRevision++; authority.projection.acceptedFactRevision++;
    const value = (row: CanonicalLine) => {
      const currentSource = candidates.find((entry) => entry.id === row.selectedCandidateId);
      return {canonical: row, source: currentSource ? lineSourceSnapshot(currentSource) : null,
        sourceCoverage: currentSource ? "recorded" as const : "legacy_unestablished" as const};
    };
    state.history.unshift({id: eventId, documentId, sourceCandidateId: source?.id ?? null, canonicalLineItemId: item?.id ?? null,
      operation: request.operation, coverage: "complete", before: before ? value(before) : null, after: item ? value(structuredClone(item)) : null,
      source: source ? lineSourceSnapshot(source) : null, legacySummary: null, actorLabel: "Phase Reviewer", occurredAt: lineTime, comment: request.comment ?? null});
    const response: LineResult = {operation: request.operation, eventId, canonicalItem: item, candidateDecision, lineDecision: decision, projection: authority.projection};
    if (state.loseResponse) return route.abort();
    return route.fulfill({json: response});
  });
  return state;
}
