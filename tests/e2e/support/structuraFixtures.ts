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
};

export type DocumentDetail = DocumentSummary & {
  pages: Array<{pageNumber: number; imageUrl?: string}>;
  assets: Array<{id: string; assetRole: string; mimeType: string; assetUrl: string; sha256?: string}>;
  fields: unknown[];
  lineItems: unknown[];
  extractions: unknown[];
  relationships: unknown[];
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

export function seededDocuments(): Map<string, DocumentDetail> {
  const existing = existingDetail();
  return new Map([[existing.id, existing]]);
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
    relationships: [],
    tags: ["Home"],
    folderIds: [homeFolder.id],
    primaryFolderId: homeFolder.id,
    filingNotes: null,
  };
}
