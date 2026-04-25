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
};

export type DocumentListResponse = {
  items: DocumentSummary[];
  total: number;
};

export type ViewMode = "inbox" | "viewer";
