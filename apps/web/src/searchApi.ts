import {csrfToken, fetchJson} from "./api";
import type {SavedSearch, SearchRequest, SearchResponse} from "./types";

export async function runSearch(payload: SearchRequest): Promise<SearchResponse> {
  return fetchJson<SearchResponse>("/api/v1/search", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(payload),
  });
}

export async function createSavedSearch(payload: {
  name: string;
  queryText: string;
  filters?: Record<string, unknown>;
  sort?: Record<string, unknown>;
}): Promise<SavedSearch> {
  return fetchJson<SavedSearch>("/api/v1/saved-searches", {
    method: "POST",
    headers: {"Content-Type": "application/json", "X-CSRF-Token": csrfToken()},
    body: JSON.stringify(payload),
  });
}
