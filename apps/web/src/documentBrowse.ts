import type {DocumentBrowseCounts} from "./types";

export const inboxStates = [
  {value: "all", label: "All", count: "all", detail: "All documents matching the other filters."},
  {value: "needs_review", label: "Needs Review", count: "needsReview", detail: "Review required or an open review task."},
  {value: "unfiled", label: "Unfiled", count: "unfiled", detail: "No manual-folder membership."},
  {value: "awaiting_classification", label: "Awaiting Classification", count: "awaitingClassification", detail: "No recorded classification decision or assigned family."},
  {value: "duplicates", label: "Duplicates", count: "duplicates", detail: "An accessible exact duplicate or duplicate suggestion exists."},
  {value: "low_confidence", label: "Low model confidence", count: "lowConfidence", detail: "Recorded family confidence below 70%, without human reclassification."},
  {value: "has_extraction", label: "Extraction results", count: "hasExtraction", detail: "Current extraction output exists; values may still need review."},
  {value: "text_searchable", label: "Text searchable", count: "textSearchable", detail: "Text is available for keyword search. Complete coverage and semantic search readiness may differ."},
] as const satisfies readonly {value: string; label: string; count: keyof DocumentBrowseCounts; detail: string}[];
export type InboxState = typeof inboxStates[number]["value"];

export const documentSorts = [
  {value: "uploaded_desc", label: "Newest uploads"},
  {value: "uploaded_asc", label: "Oldest uploads"},
  {value: "document_date_desc", label: "Document date: newest"},
  {value: "document_date_asc", label: "Document date: oldest"},
  {value: "title_asc", label: "Title: A to Z"},
  {value: "title_desc", label: "Title: Z to A"},
] as const;
export type DocumentSort = typeof documentSorts[number]["value"];
export type DocumentBrowseQuery = {
  query?: string; folderId?: string; inboxState?: InboxState; sort?: DocumentSort;
  offset?: number; limit?: number;
};

export function browseRequestPath(query: DocumentBrowseQuery): string {
  const params = new URLSearchParams();
  if (query.query?.trim()) params.set("q", query.query.trim());
  if (query.folderId) params.set("folderId", query.folderId);
  if (query.inboxState && query.inboxState !== "all") params.set("inboxState", query.inboxState);
  if (query.sort && query.sort !== "uploaded_desc") params.set("sort", query.sort);
  if (query.offset) params.set("offset", String(query.offset));
  if (query.limit && query.limit !== 50) params.set("limit", String(query.limit));
  return `/api/v1/documents${params.size ? `?${params}` : ""}`;
}

export function parseBrowseOptions(params: URLSearchParams): Pick<DocumentBrowseQuery, "inboxState" | "sort" | "offset" | "limit"> {
  const inboxState = params.get("state"), sort = params.get("sort");
  if (inboxState !== null && !inboxStates.some((item) => item.value === inboxState)) throw new Error("This Inbox link contains an unsupported state.");
  if (sort !== null && !documentSorts.some((item) => item.value === sort)) throw new Error("This Inbox link contains an unsupported sort order.");
  const integer = (key: string, min: number, max: number) => {
    const raw = params.get(key);
    if (raw === null) return undefined;
    if (!/^(0|[1-9]\d*)$/.test(raw) || !Number.isSafeInteger(Number(raw)) || Number(raw) < min || Number(raw) > max) {
      throw new Error("This Inbox link contains invalid pagination.");
    }
    return Number(raw);
  };
  return {inboxState: (inboxState ?? undefined) as InboxState | undefined,
    sort: (sort ?? undefined) as DocumentSort | undefined,
    offset: integer("offset", 0, Number.MAX_SAFE_INTEGER), limit: integer("limit", 1, 200)};
}

export function appendBrowseOptions(params: URLSearchParams, query: DocumentBrowseQuery) {
  if (query.inboxState && query.inboxState !== "all") params.set("state", query.inboxState);
  if (query.sort && query.sort !== "uploaded_desc") params.set("sort", query.sort);
  if (query.offset) params.set("offset", String(query.offset));
  if (query.limit && query.limit !== 50) params.set("limit", String(query.limit));
}
