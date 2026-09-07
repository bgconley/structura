import {familyLabel} from "./format";
import type {Folder, SearchMode, SearchRequest} from "./types";

export type SearchFilterState = {
  mode: SearchMode;
  family: string;
  folderId: string;
  tag: string;
  reviewStatus: string;
  sensitivity: string;
  relationshipType: string;
  hasRelationships: boolean;
  deadlineType: string;
  hasOpenDeadlines: boolean;
  includeVisual: boolean;
  reviewedOnly: boolean;
  dateFrom: string;
  dateTo: string;
  amountMin: string;
  amountMax: string;
};

export const defaultSearchFilterState: SearchFilterState = {
  mode: "hybrid",
  family: "",
  folderId: "",
  tag: "",
  reviewStatus: "",
  sensitivity: "",
  relationshipType: "",
  hasRelationships: false,
  deadlineType: "",
  hasOpenDeadlines: false,
  includeVisual: false,
  reviewedOnly: false,
  dateFrom: "",
  dateTo: "",
  amountMin: "",
  amountMax: "",
};

export function searchRequestFromFilters(
  query: string,
  filters: SearchFilterState,
): SearchRequest {
  return {
    query,
    mode: filters.mode,
    families: filters.family ? [filters.family] : [],
    folderIds: filters.folderId ? [filters.folderId] : [],
    tags: filters.tag ? [filters.tag] : [],
    reviewStatuses: filters.reviewStatus ? [filters.reviewStatus] : [],
    reviewedOnly: filters.reviewedOnly || undefined,
    dateFrom: filters.dateFrom || undefined,
    dateTo: filters.dateTo || undefined,
    amountMin: filters.amountMin ? Number(filters.amountMin) : undefined,
    amountMax: filters.amountMax ? Number(filters.amountMax) : undefined,
    sensitivity: filters.sensitivity ? [filters.sensitivity] : [],
    relationshipTypes: filters.relationshipType ? [filters.relationshipType] : [],
    hasRelationships: filters.hasRelationships || undefined,
    deadlineTypes: filters.deadlineType ? [filters.deadlineType] : [],
    hasOpenDeadlines: filters.hasOpenDeadlines || undefined,
    includeVisual: filters.includeVisual || filters.mode === "visual" || undefined,
    includeDebug: true,
  };
}

export function activeSearchFilters(
  filters: SearchFilterState,
  folders: Folder[],
): string[] {
  const selectedFolder = selectedSearchFolder(filters, folders);
  return [
    filters.family ? familyLabel(filters.family) : null,
    selectedFolder ? `folder ${selectedFolder.path ?? selectedFolder.name}` : null,
    filters.tag ? `tag ${filters.tag}` : null,
    filters.reviewStatus ? `review ${filters.reviewStatus}` : null,
    filters.sensitivity ? `sensitivity ${filters.sensitivity}` : null,
    filters.relationshipType ? `relationship ${filters.relationshipType}` : null,
    filters.hasRelationships ? "has relationships" : null,
    filters.deadlineType ? `deadline ${filters.deadlineType}` : null,
    filters.hasOpenDeadlines ? "open deadlines" : null,
    filters.includeVisual || filters.mode === "visual" ? "visual retrieval" : null,
    filters.reviewedOnly ? "reviewed only" : null,
    filters.dateFrom || filters.dateTo
      ? `${filters.dateFrom || "any"} to ${filters.dateTo || "any"}`
      : null,
    filters.amountMin || filters.amountMax
      ? `$${filters.amountMin || "0"} to ${filters.amountMax || "any"}`
      : null,
  ].filter((value): value is string => Boolean(value));
}

export function selectedSearchFolder(
  filters: SearchFilterState,
  folders: Folder[],
): Folder | undefined {
  return folders.find((folder) => folder.id === filters.folderId);
}


export const modeOptions: SearchMode[] = ["hybrid", "lexical", "semantic", "visual"];
export const familyOptions = [
  "",
  "medical_eob",
  "medical_bill",
  "insurance_denial",
  "invoice",
  "receipt",
  "retail_order",
  "service_record",
  "real_estate_title",
  "mortgage_escrow_statement",
  "financial_dispute_form",
  "warranty",
  "tax_document",
  "legal_contract",
];
export const reviewStatusOptions = [
  "",
  "unreviewed",
  "auto_accepted",
  "needs_review",
  "user_confirmed",
  "user_corrected",
  "rejected",
];
export const sensitivityOptions = ["", "normal", "pii", "financial", "medical", "legal", "highly_sensitive"];
export const relationshipTypeOptions = [
  "",
  "duplicate_of",
  "related_to",
  "invoice_for",
  "receipt_for",
  "eob_for",
  "bill_for",
  "warranty_for",
  "renewal_of",
];
export const deadlineTypeOptions = [
  "",
  "due_date",
  "renewal_date",
  "warranty_expiration",
  "response_deadline",
  "filing_deadline",
  "appointment_date",
];
