import {inboxStates, type InboxState} from "../../../apps/web/src/documentBrowse";
import type {DocumentBrowseCounts} from "../../../apps/web/src/types";
import {summaryFromDetail, type DocumentDetail, type Folder} from "./structuraFixtures";

// Source-state facts are explicit test inputs. This mock does not infer model
// decisions from generic family/review state or pretend to implement DB policy.
export type BrowseFacts = Partial<Record<InboxState, boolean>>;
export function documentBrowseResponse(params: URLSearchParams, documents: DocumentDetail[],
  folders: Folder[] = [], facts: Record<string, BrowseFacts> = {}) {
  const q = params.get("q")?.toLowerCase() ?? "", folderId = params.get("folderId");
  const base = documents.filter((document) => (!q || document.title.toLowerCase().includes(q))
    && (!folderId || document.folderIds.includes(folderId))
    && (!params.get("family") || document.family === params.get("family"))
    && (!params.get("reviewStatus") || document.reviewStatus === params.get("reviewStatus")));
  const has = (document: DocumentDetail, state: InboxState): boolean => {
    const explicit = facts[document.id]?.[state];
    if (explicit !== undefined) return explicit;
    switch (state) {
      case "all": return true;
      case "needs_review": return document.reviewStatus === "needs_review";
      case "unfiled": return !document.folderIds.some((id) => folders.find((folder) => folder.id === id)?.folderKind === "manual");
      case "duplicates": return document.relationships.some((relation) => relation.relationshipType === "duplicate_of" && ["suggested", "confirmed"].includes(relation.status));
      case "has_extraction": return document.extractions.length > 0;
      default: return false;
    }
  };
  const counts = Object.fromEntries(inboxStates.map((state) => [state.count, base.filter((document) => has(document, state.value)).length])) as DocumentBrowseCounts;
  counts.previewReady = base.filter((document) => !!document.thumbnailUrl).length;
  counts.humanReviewed = base.filter((document) => ["user_confirmed", "user_corrected"].includes(document.reviewStatus)).length;
  const state = (params.get("inboxState") ?? "all") as InboxState;
  const selected = base.filter((document) => has(document, state));
  const sort = params.get("sort") ?? "uploaded_desc", desc = sort.endsWith("desc");
  selected.sort((left, right) => {
    const value = (document: DocumentDetail) => sort.startsWith("title") ? document.title.toLowerCase()
      : sort.startsWith("document_date") ? document.documentDate ?? null : document.createdAt;
    const a = value(left), b = value(right);
    if (a === null && b !== null) return 1;
    if (a !== null && b === null) return -1;
    const ordered = a === b ? left.id < right.id ? -1 : left.id > right.id ? 1 : 0 : a! < b! ? -1 : 1;
    return desc ? -ordered : ordered;
  });
  const limit = Number(params.get("limit") ?? 50), offset = Number(params.get("offset") ?? 0);
  return {items: selected.slice(offset, offset + limit).map(summaryFromDetail), total: selected.length,
    corpusTotal: documents.length, counts, limit, offset, observedAt: "2026-09-07T00:00:00Z"};
}
