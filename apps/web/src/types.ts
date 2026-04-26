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
};

export type DocumentDetail = DocumentSummary & {
  description?: string;
  pages: DocumentPage[];
  assets: DocumentAsset[];
  fields: unknown[];
  lineItems: unknown[];
  extractions: unknown[];
  relationships: unknown[];
  tags: string[];
  folderIds: string[];
  primaryFolderId?: string | null;
  filingNotes?: string | null;
};

export type DocumentListResponse = {
  items: DocumentSummary[];
  total: number;
};

export type EvidenceRef = {
  pageNumber: number;
  sourceEngine: string;
  sourceText?: string;
  elementId?: string;
  tableId?: string;
  rowIndex?: number;
  textSpan?: {start: number; end: number; basis?: string};
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
};

export type ReviewActionPayload = {
  schemaName: "review_action";
  schemaVersion: "v1";
  documentId: string;
  reviewTaskId?: string;
  actionType: "confirm_field" | "correct_field" | "reject_field" | "reclassify_document" | "rerun_extraction" | "mark_done";
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

export type ViewMode = "inbox" | "viewer" | "review";
