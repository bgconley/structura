export type ViewMode = "inbox" | "review" | "search" | "viewer" | "automation" | "relationships" | "timelines";

export type SessionInfo = {
  displayName?: string;
  email?: string;
  isAuthenticated: boolean;
  sessionCookieName?: string;
  csrfCookieName?: string;
};

export type DocumentSummary = {
  id: string;
  title: string;
  family: string;
  lifecycleState: string;
  reviewStatus: string;
  createdAt: string;
  documentDate?: string;
  amountTotal?: number;
  counterpartyDisplay?: string;
  thumbnailUrl?: string;
  folderPaths?: string[];
  tags?: string[];
  relatedCount?: number;
  qualitySummary?: {
    reasons?: string[];
    reviewRequired?: boolean;
    visualEmbeddingEligible?: boolean;
    qwenRouteEligible?: boolean;
    summary?: string;
  } | null;
};

export type DocumentAsset = {
  id: string;
  assetRole: string;
  pageNumber?: number;
  mimeType: string;
  assetUrl: string;
  sha256?: string;
};

export type DocumentPage = {
  pageNumber: number;
  width?: number;
  height?: number;
  imageUrl?: string;
  qualitySignals?: {
    reasons?: string[];
    reviewRequired?: boolean;
    visualEmbeddingEligible?: boolean;
    qwenRouteEligible?: boolean;
    summary?: string;
  } | null;
};

export type QualityOutcome =
  | "extracted_cleanly"
  | "needs_human_review"
  | "insufficient_signal"
  | "no_extraction_target"
  | "pipeline_failed";

export type ClaimResolutionDecision = {
  canonicalKey: string;
  decision: string;
  reasonCode: string;
  selectedClaimId?: string;
  rejectedClaimIds?: string[];
};

export type ExtractionSummary = {
  id: string;
  schemaName: string;
  schemaVersion: string;
  status: string;
  sourceEngine?: string;
  modelName?: string | null;
  modelVersion?: string | null;
  confidence?: number | null;
  reviewStatus?: string | null;
  extractionScope?: "document" | "aggregate" | "semantic_region";
  qualityOutcome?: QualityOutcome | null;
  claimResolutionDecisions?: ClaimResolutionDecision[];
  regionJobCoverage?: Record<string, unknown>;
  sourceFamilies?: string[];
  createdAt?: string;
};

export type SemanticRegionExtraction = ExtractionSummary & {
  semanticAnnotationId?: string | null;
  sourceSemanticRegionId?: string | null;
  semanticType?: string | null;
  graniteTask?: string | null;
  modelOutputSchemaName?: string | null;
  modelOutputSchemaVersion?: string | null;
  normalized?: Record<string, unknown>;
  normalization?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
};

export type ExtractionObservation = {
  id: string;
  extractionId?: string | null;
  semanticAnnotationId?: string | null;
  sourceSemanticRegionId?: string | null;
  semanticType?: string | null;
  sourceEngine?: string;
  modelOutputSchemaName?: string | null;
  observationFamily?: string | null;
  fieldName: string;
  valueType?: string;
  value?: unknown;
  confidence?: number | null;
  evidence: EvidenceRef[];
  validation?: Record<string, unknown>;
  status?: string;
  metadata?: Record<string, unknown>;
  createdAt?: string;
};

export type CanonicalFieldSummary = {
  id: string;
  fieldPath: string;
  ordinal?: number;
  valueType: string;
  value: unknown;
  currency?: string | null;
  sourceKind?: string;
  reviewStatus?: string;
  evidence?: EvidenceRef[];
  validation?: Record<string, unknown>;
  acceptedAt?: string | null;
};

export type CanonicalLineItemSummary = {
  id: string;
  lineItemType: string;
  ordinal?: number;
  description?: string | null;
  netAmount?: number | null;
  currency?: string | null;
  sourceKind?: string;
  reviewStatus?: string;
  evidence?: EvidenceRef[];
};

export type DocumentDetail = DocumentSummary & {
  description?: string;
  pages: DocumentPage[];
  assets: DocumentAsset[];
  fields: CanonicalFieldSummary[];
  lineItems: CanonicalLineItemSummary[];
  extractions: ExtractionSummary[];
  semanticRegionExtractions?: SemanticRegionExtraction[];
  observations?: ExtractionObservation[];
  relationships: DocumentRelationship[];
  tags: string[];
  folderIds: string[];
  primaryFolderId?: string | null;
  filingNotes?: string | null;
};

export type SemanticAnnotationManifest = {
  qualityMode: "smart";
  profileName: string;
  sourceEngine: string;
  modelName: string;
  modelVersion: string;
  promptVersion: string;
  reviewRequired: boolean;
  escalationReason?: string | null;
  confidence?: Record<string, unknown>;
  pages: Array<{
    pageId: string;
    pageNumber: number;
    pageRole: string;
    documentTypeHint?: string | null;
    extractionUsefulness?: string;
    isBoilerplate?: boolean;
    hasStructuredTargets?: boolean;
    ambiguous?: boolean;
    escalationRequired?: boolean;
    reason?: string | null;
    confidence?: number | null;
    metadata?: Record<string, unknown>;
  }>;
  regions: Array<{
    semanticType: string;
    priority: string;
    graniteTask?: string | null;
    targetSchema?: string | null;
    expectedFields: string[];
    reviewRequired?: boolean;
    reason?: string | null;
    confidence?: number | null;
    metadata?: Record<string, unknown>;
    grounding: {
      kind: string;
      pageId?: string | null;
      elementId?: string | null;
      tableId?: string | null;
    };
  }>;
};

export type SemanticAnnotationResponse = {
  documentId: string;
  qualityMode: string;
  current: SemanticAnnotationManifest | null;
};

export type DocumentListResponse = {
  items: DocumentSummary[];
  total: number;
};

export type EvidenceRef = {
  pageNumber: number;
  sourceEngine: string;
  sourceText?: string;
  bbox?: [number, number, number, number];
  elementId?: string;
  tableId?: string;
  rowIndex?: number;
  textSpan?: {start: number; end: number; basis?: string};
};

export type EvidenceTarget = {
  documentId: string;
  fieldPath?: string;
  pageNumber?: number;
  sourceText?: string;
  bbox?: [number, number, number, number];
  elementId?: string;
  tableId?: string;
  rowIndex?: number;
  textSpan?: {start: number; end: number; basis?: string};
};

export type SearchMode = "lexical" | "semantic" | "hybrid" | "visual";

export type SearchRequest = {
  query: string;
  mode?: SearchMode;
  families?: string[];
  folderIds?: string[];
  tags?: string[];
  reviewStatuses?: string[];
  reviewedOnly?: boolean;
  dateFrom?: string;
  dateTo?: string;
  amountMin?: number;
  amountMax?: number;
  sensitivity?: string[];
  relationshipTypes?: string[];
  relationshipStatuses?: string[];
  hasRelationships?: boolean;
  deadlineTypes?: string[];
  deadlineStatuses?: string[];
  hasOpenDeadlines?: boolean;
  primaryFolderOnly?: boolean;
  includeVisual?: boolean;
  limit?: number;
  includeDebug?: boolean;
};

export type DocumentRelationship = {
  id: string;
  documentId: string;
  relatedDocumentId: string;
  relatedTitle: string;
  relationshipType: string;
  status: "suggested" | "confirmed" | "rejected" | "superseded";
  direction: "from" | "to";
  confidence?: number;
  sourceEngine: string;
  evidence?: EvidenceRef[];
  comment?: string | null;
  reviewTaskId?: string | null;
  createdAt: string;
};

export type RelationshipWrite = {
  fromDocumentId: string;
  toDocumentId: string;
  relationshipType: string;
  confidence?: number;
  evidence?: EvidenceRef[];
  comment?: string;
};

export type DocumentDeadline = {
  id: string;
  documentId: string;
  documentTitle: string;
  deadlineType: string;
  dueOn: string;
  remindFrom?: string | null;
  status: string;
  confidence?: number;
  evidence?: EvidenceRef[];
  metadata?: Record<string, unknown>;
};

export type TimelineEvent = {
  id: string;
  eventType: string;
  occurredOn: string;
  title: string;
  documentId?: string;
  documentTitle?: string;
  relationshipId?: string;
  contactId?: string;
  contactName?: string;
  deadlineId?: string;
  status?: string;
  metadata?: Record<string, unknown>;
};

export type SmartViewSummary = {
  key: string;
  title: string;
  description: string;
  count: number;
  filters: Record<string, unknown>;
};

export type SearchResult = {
  documentId: string;
  title: string;
  family?: string;
  rank: number;
  score?: number;
  snippet?: string;
  matchedChunkId?: string;
  pageNumber?: number;
  evidence?: EvidenceRef[];
  explanation?: string;
  counterpartyDisplay?: string;
  documentDate?: string;
  amountTotal?: number;
  folderPaths?: string[];
  tags?: string[];
  sourceModalities?: string[];
};

export type SearchResponse = {
  items: SearchResult[];
  facets?: Record<string, Record<string, number>>;
  debug?: Record<string, unknown> | null;
};

export type SavedSearch = {
  id: string;
  name: string;
  queryText: string;
  filters: Record<string, unknown>;
  sort: Record<string, unknown>;
  createdAt: string;
};

export type Contact = {
  id: string;
  contactType: string;
  displayName: string;
  normalizedName?: string;
  aliases: string[];
  identifiers: Record<string, unknown>;
  linkedDocumentCount: number;
};

export type ContactWrite = {
  id?: string;
  contactType?: string;
  displayName: string;
  aliases?: string[];
  identifiers?: Record<string, unknown>;
};

export type ContactMergeSuggestion = {
  sourceContactId: string;
  targetContactId: string;
  reason: string;
  confidence: number;
};

export type FilingRule = {
  id: string;
  name: string;
  description?: string;
  enabled: boolean;
  priority?: number;
  reviewRequired?: boolean;
  conditions: Array<Record<string, unknown>>;
  actions: Array<Record<string, unknown>>;
  lastRunAt?: string | null;
};

export type FilingRuleWrite = {
  id?: string;
  name: string;
  description?: string;
  enabled?: boolean;
  priority?: number;
  reviewRequired?: boolean;
  conditions: Array<Record<string, unknown>>;
  actions: Array<Record<string, unknown>>;
};

export type FilingRuleEvaluation = {
  runId?: string;
  ruleId?: string;
  documentId: string;
  matched: boolean;
  conditions: Array<Record<string, unknown>>;
  proposedActions: Array<Record<string, unknown>>;
  blockedActions: Array<Record<string, unknown>>;
  appliedActions?: Array<Record<string, unknown>>;
  reviewRequired: boolean;
  safetyReasons: string[];
  explanation: Record<string, unknown>;
  status?: string;
};

export type FilingSuggestion = {
  runId: string;
  ruleId: string;
  ruleName: string;
  documentId: string;
  documentTitle: string;
  proposedActions: Array<Record<string, unknown>>;
  blockedActions: Array<Record<string, unknown>>;
  explanation: Record<string, unknown>;
  createdAt: string;
};

export type WatchedFolder = {
  id: string;
  path: string;
  enabled: boolean;
  policy: Record<string, unknown>;
  lastScanAt?: string | null;
};

export type WatchedFolderWrite = {
  id?: string;
  path: string;
  enabled?: boolean;
  policy?: Record<string, unknown>;
};

export type ImportStatus = {
  watchedFolderId?: string;
  path?: string;
  enabled?: boolean;
  lastScanAt?: string | null;
  acceptedCount: number;
  rejectedCount: number;
  skippedCount: number;
};

export type FieldCandidate = {
  id: string;
  documentId: string;
  extractionId?: string;
  fieldPath: string;
  ordinal?: number;
  valueType: string;
  value: unknown;
  normalizedValue?: unknown;
  currency?: string;
  confidence?: number;
  authorityWeight?: number;
  sourceEngine: string;
  evidence: EvidenceRef[];
  validation?: Record<string, unknown>;
  status?: string;
};

export type CanonicalField = {
  id: string;
  documentId: string;
  selectedCandidateId?: string;
  fieldPath: string;
  ordinal?: number;
  valueType: string;
  value: unknown;
  currency?: string;
  sourceKind: string;
  reviewStatus: string;
  evidence: EvidenceRef[];
  validation?: Record<string, unknown>;
  acceptedAt?: string;
};

export type ReviewTask = {
  id: string;
  documentId: string;
  taskType: string;
  status: string;
  priority: number;
  pageNumber?: number;
  fieldPath?: string;
  rationale?: string;
  metadata?: Record<string, unknown> | null;
};

export type ObservationCandidate = {
  id: string;
  documentId: string;
  extractionId?: string | null;
  observationFamily?: string | null;
  fieldName: string;
  valueType: string;
  value?: unknown;
  confidence?: number | null;
  sourceEngine: string;
  semanticType?: string | null;
  modelOutputSchemaName?: string | null;
  evidence: EvidenceRef[];
  validation?: Record<string, unknown>;
  status?: string;
};

export type LineItemCandidate = {
  id: string;
  documentId: string;
  extractionId?: string | null;
  lineItemType: string;
  ordinal: number;
  code?: string | null;
  serviceDate?: string | null;
  description?: string | null;
  quantity?: number | null;
  unit?: string | null;
  unitPrice?: number | null;
  netAmount?: number | null;
  currency?: string | null;
  categoryHint?: string | null;
  confidence?: number | null;
  sourceEngine: string;
  evidence: EvidenceRef[];
  validation?: Record<string, unknown>;
  status?: string;
};

export type ReviewActionType =
  | "confirm_field"
  | "correct_field"
  | "reject_field"
  | "reclassify_document"
  | "rerun_extraction"
  | "mark_done"
  | "accept_observation"
  | "reject_observation"
  | "accept_line_item"
  | "reject_line_item";

export type ReviewActionPayload = {
  schemaName: "review_action";
  schemaVersion: "v1";
  documentId: string;
  reviewTaskId?: string;
  actionType: ReviewActionType;
  actorType: "human";
  fieldPath?: string;
  newValue?: unknown;
  comment?: string;
  evidenceContext?: EvidenceRef[];
  metadata?: Record<string, unknown>;
  createdAt: string;
};

export type Folder = {
  id: string;
  parentId?: string | null;
  folderKind: "manual" | "smart";
  name: string;
  path?: string | null;
  savedQuery?: Record<string, unknown> | null;
  aclMode?: "private" | "household" | "custom";
};

export type FolderWrite = {
  parentId?: string;
  folderKind: "manual" | "smart";
  name: string;
  description?: string;
  savedQuery?: Record<string, unknown>;
  aclMode?: "private" | "household" | "custom";
};

export type Tag = {
  id: string;
  name: string;
  colorHex?: string | null;
  description?: string | null;
};

export type TagWrite = {
  name: string;
  colorHex?: string;
  description?: string;
};

export type DocumentOrganizationWrite = {
  title?: string;
  documentDate?: string | null;
  folderIds?: string[];
  primaryFolderId?: string | null;
  tags?: string[];
  filingNotes?: string | null;
};

export type ParseDebugAsset = {
  id: string;
  assetRole: string;
  assetUrl: string;
  byteSize?: number;
  modelName?: string | null;
  modelVersion?: string | null;
  sha256?: string;
};

export type ParseDebugPage = {
  pageNumber: number;
  textPreview?: string | null;
  imageUrl?: string | null;
};

export type ParseDebugJob = {
  jobId: string;
  jobType: string;
  status: string;
  attemptCount?: number;
  maxAttempts?: number;
};

export type ParseDebugView = {
  document: {
    id: string;
    title: string;
    pageCount?: number | null;
    metadata?: Record<string, unknown>;
  };
  artifacts: ParseDebugAsset[];
  pages: ParseDebugPage[];
  elements: unknown[];
  tables: unknown[];
  chunks: unknown[];
  jobs: ParseDebugJob[];
};
