import type {EvidenceRef} from "../types";

export type LineType = "generic" | "receipt_item" | "invoice_item" | "service_line" | "payment" | "tax" | "adjustment" | "fee";
export type LineValues = {
  code: string | null; codeSystem: string | null; serviceDate: string | null; description: string | null;
  quantity: string | null; unit: string | null; unitPrice: string | null; grossAmount: string | null;
  discountAmount: string | null; taxAmount: string | null; netAmount: string | null;
  allowedAmount: string | null; planPaidAmount: string | null; currency: string | null; categoryHint: string | null;
};
export type LineSlot = {lineItemType: LineType; ordinal: number};
export type VacantTarget = LineSlot & {canonicalLineItemId: null; expectedCanonicalUpdatedAt: null; expectedLineDecisionRevision: null};
export type ExistingTarget = LineSlot & {canonicalLineItemId: string; expectedCanonicalUpdatedAt: string; expectedLineDecisionRevision: string | null};
export type SourceExpectation = {candidateId: string; expectedCandidateVersion: string;
  expectedSourceSnapshotSha256: string; expectedCandidateDecisionRevision: string | null};
export type LineRequest = (
  {operation: "create"; source: SourceExpectation; target: VacantTarget}
  | {operation: "replace"; source: SourceExpectation; target: ExistingTarget}
  | {operation: "reject_candidate"; source: SourceExpectation}
  | {operation: "reject_selected"; target: ExistingTarget}
) & {comment?: string};
export type LineAssignment = {sourceCandidateId: string; state: "assigned" | "legacy_conflict";
  canonicalLineItemId: string | null; target: LineSlot | null; currentlySelected: boolean};
export type ExtractionIdentity = {id: string; documentId: string; schemaName: string; schemaVersion: string;
  sourceEngine: string; modelName: string | null; modelVersion: string | null; promptVersion: string | null;
  extractionScope: string; semanticAnnotationId: string | null; sourceSemanticRegionId: string | null};
export type LineCandidate = LineValues & LineSlot & {id: string; documentId: string; extractionId: string | null;
  candidateGroup: string | null; candidateVersion: string; sourceSnapshotSha256: string;
  candidateDecisionRevision: string | null; sourceEngine: string; status: string; evidence: EvidenceRef[];
  extraction: ExtractionIdentity | null;
  validation: {recorded: boolean; needsReview: boolean | null; checks: {code: string; status: string}[]; unrepresentedCheckCount: number};
  publicationEligibility: {eligible: boolean; reason: string}; sourceAssignment: LineAssignment | null;
  suggestedVacantTarget: VacantTarget | null};
export type CanonicalLine = LineValues & LineSlot & {id: string; documentId: string; selectedCandidateId: string | null;
  sourceKind: string; reviewStatus: string; evidence: EvidenceRef[]; validation: Record<string, unknown>;
  acceptedAt: string | null; updatedAt: string; selected: boolean};
export type LineDecision = LineSlot & {id: string; documentId: string; canonicalLineItemId: string; revision: string;
  disposition: "confirmed" | "corrected" | "rejected" | "protected_legacy"; origin: "live_review" | "legacy_current_line";
  actorUserId: string | null; reviewEventId: string | null; decisionEventId: string | null; decidedAt: string | null; recordedAt: string};
export type CandidateDecision = {id: string; documentId: string; sourceCandidateId: string; revision: string;
  disposition: "accepted" | "rejected" | "protected_legacy"; origin: "live_review" | "legacy_current_line";
  sourceSnapshotSha256: string; actorUserId: string | null; reviewEventId: string | null;
  decidedAt: string | null; recordedAt: string};
export type LineProjection = {schemaVersion: "accepted_fact_projection.v1"; documentId: string;
  state: "unestablished" | "current"; acceptedFactRevision: number; projectionRevision: number;
  acceptedFactsSha256: string | null; indexedMetadataSha256: string | null;
  acceptedFactBasisSchemaVersion: "accepted_fields.v1" | "accepted_fields_and_lines.v1"};
export type CanonicalLines = {authorityVersion: "line_item_authority.v1"; documentId: string;
  items: CanonicalLine[]; decisions: LineDecision[]; sourceAssignments: LineAssignment[]; projection: LineProjection};
export type CandidateLines = {authorityVersion: "line_item_authority.v1"; documentId: string; items: LineCandidate[]};
export type LineResult = {operation: LineRequest["operation"]; eventId: string; canonicalItem: CanonicalLine | null;
  candidateDecision: CandidateDecision | null; lineDecision: LineDecision | null; projection: LineProjection};
export type SourceSnapshot = {schemaVersion: "line_item_source.v1";
  candidate: LineValues & LineSlot & {id: string; documentId: string; extractionId: string | null;
    sourceEngine: string; candidateGroup: string | null};
  extraction: ExtractionIdentity | null; original: {id: string; sha256: string} | null;
  evidence: EvidenceRef[]; validationSha256: string; storedEvidenceSha256: string};
export type HistoryValue = {canonical: CanonicalLine; source: SourceSnapshot | null; sourceCoverage: "recorded" | "legacy_unestablished"};
export type LineHistoryEntry = {id: string; documentId: string; sourceCandidateId: string | null;
  canonicalLineItemId: string | null; operation: string; coverage: "complete" | "legacy_partial";
  before: HistoryValue | null; after: HistoryValue | null; source: SourceSnapshot | null;
  legacySummary: {description: string | null; status: string | null; netAmount: string | null; precision: "legacy_unestablished"} | null;
  actorLabel: string; occurredAt: string; comment: string | null};
export type LineHistory = {documentId: string; items: LineHistoryEntry[]; nextCursor: string | null};
export type HistorySelector = {canonicalLineItemId: string; sourceCandidateId?: never} | {sourceCandidateId: string; canonicalLineItemId?: never};
