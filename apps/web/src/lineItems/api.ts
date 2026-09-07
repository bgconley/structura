import {csrfToken, fetchJson} from "../api";
import {parseCandidateLines, parseCanonicalLines, parseLineResult} from "./authority";
import {parseLineHistory} from "./historyAuthority";
import type {HistorySelector, LineRequest} from "./types";

const base = (documentId: string) => `/api/v1/documents/${encodeURIComponent(documentId)}`;
export async function getCanonicalLines(documentId: string, signal?: AbortSignal) {
  return parseCanonicalLines(await fetchJson<unknown>(`${base(documentId)}/canonical-line-items`, {signal}), documentId);
}
export async function getLineCandidates(documentId: string, candidateId?: string, signal?: AbortSignal) {
  const query = candidateId ? `?${new URLSearchParams({candidateId})}` : "";
  return parseCandidateLines(await fetchJson<unknown>(`${base(documentId)}/line-item-candidates${query}`, {signal}), documentId, candidateId);
}
export async function postLineDecision(documentId: string, request: LineRequest) {
  const result = await fetchJson<unknown>(`${base(documentId)}/line-item-decisions`, {
    method: "POST", headers: {"Content-Type": "application/json", "X-CSRF-Token": csrfToken()}, body: JSON.stringify(request),
  });
  return parseLineResult(result, documentId, request);
}
export async function getLineHistory(documentId: string, selector: HistorySelector, cursor?: string, signal?: AbortSignal) {
  const query = new URLSearchParams(selector.canonicalLineItemId
    ? {canonicalLineItemId: selector.canonicalLineItemId} : {sourceCandidateId: selector.sourceCandidateId!});
  query.set("limit", "20");
  if (cursor) query.set("cursor", cursor);
  return parseLineHistory(await fetchJson<unknown>(`${base(documentId)}/line-item-history?${query}`, {signal}), documentId, selector);
}
