import {fetchJson} from "./api";
import {useKeyedRequest} from "./useKeyedRequest";
import type {DocumentListResponse} from "./types";

export function useDocumentList(query: string, folderId?: string) {
  const params = new URLSearchParams();
  if (query.trim()) params.set("q", query.trim());
  if (folderId) params.set("folderId", folderId);
  const path = `/api/v1/documents${params.size ? `?${params}` : ""}`;
  const request = useKeyedRequest(path, (signal) => fetchJson<DocumentListResponse>(path, {signal}));
  return {...request, documents: request.data?.items ?? [], total: request.data?.total ?? 0};
}
