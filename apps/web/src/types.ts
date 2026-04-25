export type SessionInfo = {
  displayName?: string;
  email?: string;
  isAuthenticated: boolean;
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

export type ViewMode = "inbox" | "viewer";
