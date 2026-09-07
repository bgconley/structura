import {fetchJson} from "./api";
import type {ParseDebugView} from "./types";

export function getParseDebug(documentId: string, signal?: AbortSignal): Promise<ParseDebugView> {
  return fetchJson<ParseDebugView>(`/api/v1/documents/${documentId}/parse-debug`, {signal});
}
