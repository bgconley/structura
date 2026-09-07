import {fetchJson} from "./api";
import {useKeyedRequest} from "./useKeyedRequest";
import type {DocumentListResponse} from "./types";
import {browseRequestPath, type DocumentBrowseQuery} from "./documentBrowse";

export function useDocumentList(query: DocumentBrowseQuery | null) {
  const path = query ? browseRequestPath(query) : null;
  const request = useKeyedRequest(path, (signal) => fetchJson<DocumentListResponse>(path!, {signal}));
  return {...request, documents: request.data?.items ?? [], total: request.data?.total ?? null,
    counts: request.data?.counts ?? null, corpusTotal: request.data?.corpusTotal ?? null};
}
