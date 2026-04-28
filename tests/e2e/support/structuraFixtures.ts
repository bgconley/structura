export const apiOrigin = "http://localhost:8000";
export const webOrigin = "http://localhost:4173";
export const csrfToken = "phase-browser-csrf";

export type DocumentSummary = {
  id: string;
  title: string;
  family: string;
  lifecycleState: string;
  reviewStatus: string;
  createdAt: string;
  documentDate?: string | null;
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
  evidence?: Array<{
    pageNumber: number;
    sourceEngine: string;
    sourceText?: string;
    bbox?: [number, number, number, number];
  }>;
  comment?: string;
  reviewTaskId?: string | null;
  createdAt: string;
};

export type DocumentDetail = DocumentSummary & {
  pages: Array<{
    pageNumber: number;
    imageUrl?: string;
    qualitySignals?: {
      reasons?: string[];
      reviewRequired?: boolean;
      visualEmbeddingEligible?: boolean;
      qwenRouteEligible?: boolean;
      summary?: string;
    } | null;
  }>;
  assets: Array<{id: string; assetRole: string; mimeType: string; assetUrl: string; sha256?: string}>;
  fields: unknown[];
  lineItems: unknown[];
  extractions: unknown[];
  relationships: DocumentRelationship[];
  tags: string[];
  folderIds: string[];
  primaryFolderId?: string | null;
  filingNotes?: string | null;
};

export type ReviewTask = {
  id: string;
  documentId: string;
  taskType: string;
  status: string;
  priority: number;
  fieldPath?: string;
  rationale?: string;
};

export type FieldCandidate = {
  id: string;
  documentId: string;
  fieldPath: string;
  valueType: string;
  value: unknown;
  sourceEngine: string;
  evidence: Array<{
    pageNumber: number;
    sourceEngine: string;
    sourceText: string;
    bbox?: [number, number, number, number];
  }>;
  confidence?: number;
  status?: string;
};

export type CanonicalField = {
  id: string;
  documentId: string;
  fieldPath: string;
  valueType: string;
  value: unknown;
  sourceKind: string;
  reviewStatus: string;
  evidence: Array<{
    pageNumber: number;
    sourceEngine: string;
    sourceText: string;
    bbox?: [number, number, number, number];
  }>;
};

export type SearchResponse = {
  items: Array<{
    documentId: string;
    title: string;
    family: string;
    rank: number;
    score: number;
    snippet: string;
    matchedChunkId: string;
    pageNumber: number;
    explanation: string;
    counterpartyDisplay?: string;
    documentDate?: string | null;
    amountTotal?: number;
    folderPaths?: string[];
    tags?: string[];
    evidence: Array<{
      pageNumber: number;
      sourceEngine: string;
      sourceText: string;
      bbox?: [number, number, number, number];
    }>;
    sourceModalities?: string[];
  }>;
  facets: Record<string, Record<string, number>>;
  debug: Record<string, unknown>;
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

export type FilingRule = {
  id: string;
  name: string;
  enabled: boolean;
  priority: number;
  reviewRequired: boolean;
  conditions: Array<Record<string, unknown>>;
  actions: Array<Record<string, unknown>>;
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

export type Folder = {
  id: string;
  parentId?: string | null;
  folderKind: "manual" | "smart";
  name: string;
  path: string;
  savedQuery?: Record<string, unknown> | null;
  aclMode?: "private" | "household" | "custom";
};

export type Tag = {
  id: string;
  name: string;
  colorHex?: string | null;
  description?: string | null;
};

export type DocumentOrganizationWrite = {
  title?: string;
  documentDate?: string | null;
  folderIds?: string[];
  primaryFolderId?: string | null;
  tags?: string[];
  filingNotes?: string | null;
};

export const homeFolder: Folder = {
  id: "10101010-1010-4010-8010-101010101010",
  folderKind: "manual",
  name: "Home",
  path: "/Home",
  aclMode: "household",
};

export const needsReviewFolder: Folder = {
  id: "20202020-2020-4020-8020-202020202020",
  folderKind: "smart",
  name: "Needs Review",
  path: "/Needs Review",
  savedQuery: {review_status: ["needs_review"]},
  aclMode: "household",
};

export const uploadedDocument = summaryFromDetail(uploadedDetail());
export const existingDocument = summaryFromDetail(existingDetail());
export const receiptDocument = summaryFromDetail(receiptDetail());

export function seededDocuments(): Map<string, DocumentDetail> {
  const existing = existingDetail();
  const receipt = receiptDetail();
  return new Map([[existing.id, existing], [receipt.id, receipt]]);
}

export function seededFolders(): Folder[] {
  return [homeFolder, needsReviewFolder];
}

export function seededTags(): Tag[] {
  return [
    {id: "30303030-3030-4030-8030-303030303030", name: "Home", colorHex: "#2563EB"},
    {id: "40404040-4040-4040-8040-404040404040", name: "urgent", colorHex: "#F59E0B"},
    {id: "50505050-5050-4050-8050-505050505050", name: "tax-relevant", colorHex: "#0EA5E9"},
  ];
}

export function seededContacts(): Contact[] {
  return [
    {
      id: "12121212-1212-4212-8212-121212121212",
      contactType: "vendor",
      displayName: "Acme Repairs",
      normalizedName: "acme repairs",
      aliases: ["Acme Repair"],
      identifiers: {accountNumber: "ACME-100"},
      linkedDocumentCount: 1,
    },
    {
      id: "13131313-1313-4313-8313-131313131313",
      contactType: "insurer",
      displayName: "Aetna Health",
      normalizedName: "aetna health",
      aliases: ["Aetna"],
      identifiers: {payerId: "AETNA-01"},
      linkedDocumentCount: 2,
    },
  ];
}

export function seededFilingRules(): FilingRule[] {
  return [
    {
      id: "14141414-1414-4414-8414-141414141414",
      name: "File medical EOBs",
      enabled: true,
      priority: 80,
      reviewRequired: true,
      conditions: [{field: "document_family", op: "eq", value: "medical_eob"}],
      actions: [{type: "add_tag", tag: "insurance"}],
    },
  ];
}

export function seededFilingSuggestions(): FilingSuggestion[] {
  return [
    {
      runId: "15151515-1515-4515-8515-151515151515",
      ruleId: "14141414-1414-4414-8414-141414141414",
      ruleName: "File medical EOBs",
      documentId: existingDocument.id,
      documentTitle: "Anthem medical EOB",
      proposedActions: [{type: "add_tag", tag: "insurance"}],
      blockedActions: [],
      explanation: {
        conditions: [{field: "document_family", op: "eq", expected: "medical_eob", matched: true}],
      },
      createdAt: "2026-04-26T00:00:00Z",
    },
    {
      runId: "15151515-1515-4515-8515-151515151516",
      ruleId: "14141414-1414-4414-8414-141414141414",
      ruleName: "File medical EOBs",
      documentId: existingDocument.id,
      documentTitle: "Aetna duplicate EOB",
      proposedActions: [{type: "add_tag", tag: "insurance"}],
      blockedActions: [],
      explanation: {
        conditions: [{field: "document_family", op: "eq", expected: "medical_eob", matched: true}],
      },
      createdAt: "2026-04-26T00:05:00Z",
    },
    {
      runId: "15151515-1515-4515-8515-151515151517",
      ruleId: "14141414-1414-4414-8414-141414141414",
      ruleName: "File medical EOBs",
      documentId: existingDocument.id,
      documentTitle: "Deferred EOB follow-up",
      proposedActions: [{type: "add_tag", tag: "insurance"}],
      blockedActions: [],
      explanation: {
        conditions: [{field: "document_family", op: "eq", expected: "medical_eob", matched: true}],
      },
      createdAt: "2026-04-26T00:10:00Z",
    },
  ];
}

export function seededWatchedFolders(): WatchedFolder[] {
  return [
    {
      id: "16161616-1616-4616-8616-161616161616",
      path: "/srv/structura/imports/dropbox",
      enabled: true,
      policy: {allowedExtensions: [".pdf"], processedFilePolicy: "leave"},
      lastScanAt: "2026-04-26T00:00:00Z",
    },
  ];
}

export function createContact(payload: Partial<Contact>, count: number): Contact {
  const name = String(payload.displayName ?? "New Contact");
  return {
    id: `17171717-1717-4717-8717-${String(count + 1).padStart(12, "7")}`,
    contactType: String(payload.contactType ?? "organization"),
    displayName: name,
    normalizedName: name.toLowerCase(),
    aliases: payload.aliases ?? [],
    identifiers: payload.identifiers ?? {},
    linkedDocumentCount: 0,
  };
}

export function createFilingRule(payload: Partial<FilingRule>, count: number): FilingRule {
  return {
    id: `18181818-1818-4818-8818-${String(count + 1).padStart(12, "8")}`,
    name: String(payload.name ?? "New filing rule"),
    enabled: payload.enabled ?? true,
    priority: payload.priority ?? 70,
    reviewRequired: payload.reviewRequired ?? true,
    conditions: payload.conditions ?? [{field: "document_family", op: "eq", value: "generic"}],
    actions: payload.actions ?? [{type: "add_tag", tag: "filed"}],
  };
}

export function createWatchedFolder(payload: Partial<WatchedFolder>, count: number): WatchedFolder {
  return {
    id: `19191919-1919-4919-8919-${String(count + 1).padStart(12, "9")}`,
    path: String(payload.path ?? "/srv/structura/imports/incoming"),
    enabled: payload.enabled ?? true,
    policy: payload.policy ?? {allowedExtensions: [".pdf"]},
    lastScanAt: null,
  };
}

export function seededReviewTasks(): ReviewTask[] {
  return [
    {
      id: "90909090-9090-4090-8090-909090909090",
      documentId: existingDocument.id,
      taskType: "field_review",
      status: "open",
      priority: 82,
      fieldPath: "invoice.total_amount",
      rationale: "Total amount requires confirmation.",
    },
    {
      id: "93939393-9393-4393-8393-939393939393",
      documentId: receiptDocument.id,
      taskType: "document_quality",
      status: "open",
      priority: 88,
      rationale: "Difficult document requires review: handwriting detected, sparse text, degraded scan.",
    },
  ];
}

export function seededFieldCandidates(): FieldCandidate[] {
  return [
    {
      id: "91919191-9191-4191-8191-919191919191",
      documentId: existingDocument.id,
      fieldPath: "invoice.total_amount",
      valueType: "money",
      value: {amount: 1042.15, currency: "USD"},
      sourceEngine: "docling",
      confidence: 0.86,
      status: "needs_review",
      evidence: [{
        pageNumber: 1,
        sourceEngine: "docling",
        sourceText: "Total 1042.15",
        bbox: [0.18, 0.22, 0.72, 0.29],
      }],
    },
    {
      id: "94949494-9494-4494-8494-949494949494",
      documentId: receiptDocument.id,
      fieldPath: "receipt.transaction.total",
      valueType: "money",
      value: {amount: 104.15, currency: "USD"},
      sourceEngine: "docling",
      confidence: 0.68,
      status: "needs_review",
      evidence: [{
        pageNumber: 1,
        sourceEngine: "docling",
        sourceText: "Handwritten total 104.15",
        bbox: [0.16, 0.2, 0.78, 0.34],
      }],
    },
  ];
}

export function seededCanonicalFields(): CanonicalField[] {
  return [
    {
      id: "92929292-9292-4292-8292-929292929292",
      documentId: existingDocument.id,
      fieldPath: "invoice.vendor.display_name",
      valueType: "string",
      value: "Acme Repairs",
      sourceKind: "candidate",
      reviewStatus: "auto_accepted",
      evidence: [{pageNumber: 1, sourceEngine: "docling", sourceText: "Acme Repairs"}],
    },
  ];
}

export function seededRelationships(): DocumentRelationship[] {
  return [
    {
      id: "20272727-2727-4727-8727-272727272727",
      documentId: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
      relatedDocumentId: "edededed-eded-4ede-8ded-edededededed",
      relatedTitle: "Acme repair receipt",
      relationshipType: "warranty_for",
      status: "suggested",
      direction: "from",
      confidence: 0.88,
      sourceEngine: "system",
      comment: "Shared merchant and purchase date.",
      evidence: [{pageNumber: 1, sourceEngine: "system", sourceText: "Acme Repairs appears on both documents."}],
      reviewTaskId: "21272727-2727-4727-8727-272727272727",
      createdAt: "2026-04-26T12:00:00Z",
    },
  ];
}

export function seededDeadlines() {
  return [
    {
      id: "22272727-2727-4727-8727-272727272727",
      documentId: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
      documentTitle: "Existing Warranty",
      deadlineType: "warranty_expiration",
      dueOn: "2026-07-20",
      status: "open",
      confidence: 0.84,
      evidence: [{pageNumber: 1, sourceEngine: "system", sourceText: "Warranty expires July 20, 2026."}],
      metadata: {sourceFieldPath: "warranty.expiration_date"},
    },
  ];
}

export function seededTimeline() {
  return [
    {
      id: "deadline-22272727-2727-4727-8727-272727272727",
      eventType: "deadline",
      occurredOn: "2026-07-20",
      title: "warranty_expiration · Existing Warranty",
      documentId: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
      documentTitle: "Existing Warranty",
      deadlineId: "22272727-2727-4727-8727-272727272727",
      status: "open",
      metadata: {},
    },
    {
      id: "relationship-20272727-2727-4727-8727-272727272727",
      eventType: "relationship",
      occurredOn: "2026-04-26",
      title: "warranty_for · Existing Warranty ↔ Acme repair receipt",
      documentId: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
      documentTitle: "Existing Warranty",
      relationshipId: "20272727-2727-4727-8727-272727272727",
      status: "suggested",
      metadata: {},
    },
  ];
}

export function seededSmartViews() {
  return [
    {
      key: "relationship_suggestions",
      title: "Relationship suggestions",
      description: "Suggested links that need human confirmation.",
      count: 1,
      filters: {relationshipStatuses: ["suggested"]},
    },
    {
      key: "open_deadlines",
      title: "Open deadlines",
      description: "Documents with unresolved due dates.",
      count: 1,
      filters: {hasOpenDeadlines: true},
    },
  ];
}

export function seededSearchResponse(
  query: string,
  family?: string,
  includeVisual = false,
): SearchResponse {
  if (query.toLowerCase().includes("no matching") || family === "warranty") {
    return {
      items: [],
      facets: {
        families: {},
        folders: {},
        tags: {},
        reviewStatus: {},
        sensitivity: {},
        relationshipTypes: {},
        deadlineTypes: {},
        dateBuckets: {},
      },
      debug: {mode: "hybrid", candidateCounts: {lexical: 0, semantic: 0}, filtersApplied: family ? 1 : 0},
    };
  }
  if (includeVisual || query.toLowerCase().includes("handwritten")) {
    return {
      items: [
        {
          documentId: receiptDocument.id,
          title: "Handwritten repair intake",
          family: "receipt",
          rank: 1,
          score: 0.046,
          snippet: "handwriting detected, sparse text, degraded scan",
          matchedChunkId: "71717171-7171-4171-8171-717171717171",
          pageNumber: 1,
          explanation: "matched by visual rank 1 with rank fusion",
          counterpartyDisplay: "Acme Repairs",
          documentDate: "2026-04-18",
          amountTotal: 104.15,
          folderPaths: ["/Home"],
          tags: ["urgent"],
          sourceModalities: ["visual"],
          evidence: [{
            pageNumber: 1,
            sourceEngine: "docling",
            sourceText: "Handwritten intake form requires review.",
            bbox: [0.16, 0.2, 0.78, 0.34],
          }],
        },
      ],
      facets: {
        families: {receipt: 1},
        folders: {"/Home": 1},
        tags: {urgent: 1},
        reviewStatus: {needs_review: 1},
        sensitivity: {normal: 1},
        relationshipTypes: {},
        deadlineTypes: {},
        dateBuckets: {"2026-04": 1},
      },
      debug: {
        mode: "visual",
        candidateCounts: {lexical: 0, semantic: 0, visual: 1},
        filtersApplied: family ? 1 : 0,
      },
    };
  }
  return {
    items: [
      {
        documentId: existingDocument.id,
        title: "Anthem medical EOB",
        family: "medical_eob",
        rank: 1,
        score: 0.038,
        snippet: "Claim ABC123 · patient responsibility $62.00",
        matchedChunkId: "61616161-6161-4161-8161-616161616161",
        pageNumber: 1,
        explanation: "matched by lexical rank 1 and semantic rank 1",
        counterpartyDisplay: "Anthem",
        documentDate: "2026-04-20",
        amountTotal: 62,
        folderPaths: ["/Medical"],
        tags: ["medical", "urgent"],
        sourceModalities: ["lexical", "semantic"],
        evidence: [{
          pageNumber: 1,
          sourceEngine: "docling",
          sourceText: "Claim ABC123 patient responsibility $62.00",
          bbox: [0.18, 0.22, 0.72, 0.29],
        }],
      },
    ],
    facets: {
      families: {medical_eob: 1},
      folders: {"/Medical": 1},
      tags: {medical: 1, urgent: 1},
      reviewStatus: {user_confirmed: 1},
      sensitivity: {normal: 1},
      relationshipTypes: {warranty_for: 1},
      deadlineTypes: {warranty_expiration: 1},
      dateBuckets: {"2026-04": 1},
    },
    debug: {
      mode: "hybrid",
      candidateCounts: {lexical: 1, semantic: 1},
      filtersApplied: family ? 1 : 0,
    },
  };
}

export function ensureUploadedDocument(documents: Map<string, DocumentDetail>): void {
  const uploaded = uploadedDetail();
  if (!documents.has(uploaded.id)) {
    documents.set(uploaded.id, uploaded);
  }
}

export function createFolder(payload: Partial<Folder>, count: number): Folder {
  const name = String(payload.name ?? "Untitled folder");
  const folderKind = payload.folderKind === "smart" ? "smart" : "manual";
  return {
    id: `70707070-7070-4070-8070-${String(count + 1).padStart(12, "7")}`,
    parentId: payload.parentId ?? null,
    folderKind,
    name,
    path: `/${name}`,
    savedQuery: folderKind === "smart" ? payload.savedQuery ?? {review_status: ["needs_review"]} : null,
    aclMode: "household",
  };
}

export function createTag(payload: Partial<Tag>, count: number): Tag {
  return {
    id: `80808080-8080-4080-8080-${String(count + 1).padStart(12, "8")}`,
    name: String(payload.name ?? "new-tag"),
    colorHex: payload.colorHex?.toUpperCase() ?? "#2563EB",
    description: payload.description ?? null,
  };
}

export function updateDocumentOrganization(
  document: DocumentDetail,
  payload: DocumentOrganizationWrite,
  folders: Folder[],
  tags: Tag[],
):
  | {ok: true; document: DocumentDetail}
  | {ok: false; error: string} {
  const knownTags = new Set(tags.map((tag) => tag.name.toLowerCase()));
  const unknownTag = payload.tags?.find((tag) => !knownTags.has(tag.toLowerCase()));
  if (unknownTag) {
    return {ok: false, error: `Unknown tag: ${unknownTag}`};
  }

  const knownManualFolders = new Set(
    folders.filter((folder) => folder.folderKind === "manual").map((folder) => folder.id),
  );
  const folderIds = payload.folderIds ?? document.folderIds;
  const unknownFolder = folderIds.find((folderId) => !knownManualFolders.has(folderId));
  if (unknownFolder) {
    return {ok: false, error: `Unknown folder: ${unknownFolder}`};
  }

  let primaryFolderId = payload.primaryFolderId !== undefined
    ? payload.primaryFolderId
    : document.primaryFolderId ?? null;
  const targetFolderIds = [...folderIds];
  if (primaryFolderId && !targetFolderIds.includes(primaryFolderId)) {
    targetFolderIds.push(primaryFolderId);
  }
  if (targetFolderIds.length && !primaryFolderId) {
    primaryFolderId = targetFolderIds[0];
  }
  if (!targetFolderIds.length) {
    primaryFolderId = null;
  }

  return {
    ok: true,
    document: {
      ...document,
      title: payload.title ?? document.title,
      documentDate: payload.documentDate !== undefined ? payload.documentDate : document.documentDate,
      folderIds: primaryFolderId
        ? [primaryFolderId, ...targetFolderIds.filter((folderId) => folderId !== primaryFolderId)]
        : targetFolderIds,
      primaryFolderId,
      folderPaths: (primaryFolderId
        ? [primaryFolderId, ...targetFolderIds.filter((folderId) => folderId !== primaryFolderId)]
        : targetFolderIds)
        .map((folderId) => folders.find((folder) => folder.id === folderId)?.path)
        .filter((path): path is string => Boolean(path)),
      tags: payload.tags ?? document.tags,
      filingNotes: payload.filingNotes !== undefined ? payload.filingNotes : document.filingNotes,
    },
  };
}

export function summaryFromDetail(document: DocumentDetail): DocumentSummary {
  return {
    id: document.id,
    title: document.title,
    family: document.family,
    lifecycleState: document.lifecycleState,
    reviewStatus: document.reviewStatus,
    createdAt: document.createdAt,
    documentDate: document.documentDate,
    amountTotal: document.amountTotal,
    counterpartyDisplay: document.counterpartyDisplay,
    thumbnailUrl: document.thumbnailUrl,
    folderPaths: document.folderPaths,
    tags: document.tags,
    relatedCount: document.relationships?.filter((item) => item.status !== "rejected").length ?? 0,
    qualitySummary: document.qualitySummary,
  };
}

export function previewSvg(label: string): string {
  return `<svg xmlns="http://www.w3.org/2000/svg" width="960" height="1240" viewBox="0 0 960 1240">
    <rect width="960" height="1240" fill="#f7f9fc"/>
    <rect x="120" y="90" width="720" height="1060" rx="8" fill="#fff" stroke="#cbd5e1"/>
    <text x="180" y="220" font-family="Arial" font-size="38" fill="#182235">${label}</text>
  </svg>`;
}

function uploadedDetail(): DocumentDetail {
  return {
    id: "11111111-1111-4111-8111-111111111111",
    title: "phase1-browser-fixture",
    family: "uncategorized",
    lifecycleState: "active",
    reviewStatus: "needs_review",
    createdAt: "2026-04-25T12:00:00Z",
    thumbnailUrl: "/api/v1/assets/22222222-2222-4222-8222-222222222222",
    folderPaths: [],
    pages: [{pageNumber: 1, imageUrl: "/api/v1/assets/33333333-3333-4333-8333-333333333333"}],
    assets: [
      {
        id: "44444444-4444-4444-8444-444444444444",
        assetRole: "original",
        mimeType: "application/pdf",
        assetUrl: "/api/v1/assets/44444444-4444-4444-8444-444444444444",
        sha256: "d".repeat(64),
      },
      {
        id: "33333333-3333-4333-8333-333333333333",
        assetRole: "page_image",
        mimeType: "image/svg+xml",
        assetUrl: "/api/v1/assets/33333333-3333-4333-8333-333333333333",
      },
    ],
    fields: [],
    lineItems: [],
    extractions: [],
    relationships: [],
    tags: [],
    folderIds: [],
    primaryFolderId: null,
    filingNotes: null,
  };
}

function existingDetail(): DocumentDetail {
  return {
    id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    title: "Existing Warranty",
    family: "warranty",
    lifecycleState: "active",
    reviewStatus: "needs_review",
    createdAt: "2026-04-25T11:00:00Z",
    documentDate: "2026-04-20",
    thumbnailUrl: "/api/v1/assets/bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
    folderPaths: [homeFolder.path],
    pages: [{pageNumber: 1, imageUrl: "/api/v1/assets/cccccccc-cccc-4ccc-8ccc-cccccccccccc"}],
    assets: [
      {
        id: "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
        assetRole: "original",
        mimeType: "application/pdf",
        assetUrl: "/api/v1/assets/dddddddd-dddd-4ddd-8ddd-dddddddddddd",
        sha256: "a".repeat(64),
      },
    ],
    fields: [
      {
        id: "92929292-9292-4292-8292-929292929292",
        fieldPath: "invoice.vendor.display_name",
        value: "Acme Repairs",
        reviewStatus: "auto_accepted",
      },
    ],
    lineItems: [],
    extractions: [],
    relationships: seededRelationships(),
    tags: ["Home"],
    folderIds: [homeFolder.id],
    primaryFolderId: homeFolder.id,
    filingNotes: null,
  };
}

function receiptDetail(): DocumentDetail {
  return {
    id: "edededed-eded-4ede-8ded-edededededed",
    title: "Acme repair receipt",
    family: "receipt",
    lifecycleState: "active",
    reviewStatus: "user_confirmed",
    createdAt: "2026-04-25T10:00:00Z",
    documentDate: "2026-04-20",
    thumbnailUrl: "/api/v1/assets/eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
    folderPaths: [homeFolder.path],
    qualitySummary: {
      reasons: ["handwriting", "low_text_density", "degraded_scan"],
      reviewRequired: true,
      visualEmbeddingEligible: true,
      qwenRouteEligible: true,
      summary: "handwriting detected, sparse text, degraded scan",
    },
    pages: [{
      pageNumber: 1,
      imageUrl: "/api/v1/assets/efefefef-efef-4efe-8fef-efefefefefef",
      qualitySignals: {
        reasons: ["handwriting", "low_text_density", "degraded_scan"],
        reviewRequired: true,
        visualEmbeddingEligible: true,
        qwenRouteEligible: true,
        summary: "handwriting detected, sparse text, degraded scan",
      },
    }],
    assets: [
      {
        id: "eaeaeaea-eaea-4aea-8aea-eaeaeaeaeaea",
        assetRole: "original",
        mimeType: "application/pdf",
        assetUrl: "/api/v1/assets/eaeaeaea-eaea-4aea-8aea-eaeaeaeaeaea",
        sha256: "b".repeat(64),
      },
    ],
    fields: [],
    lineItems: [],
    extractions: [],
    relationships: [],
    tags: ["Home"],
    folderIds: [homeFolder.id],
    primaryFolderId: homeFolder.id,
    filingNotes: null,
  };
}
