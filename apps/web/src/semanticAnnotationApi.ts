import {csrfToken, fetchJson} from "./api";
import type {SemanticAnnotationResponse} from "./types";

export function getCurrentSemanticAnnotation(
  documentId: string,
  qualityMode = "smart",
): Promise<SemanticAnnotationResponse> {
  const params = new URLSearchParams({qualityMode});
  return fetchJson(`/api/v1/documents/${documentId}/semantic-annotations/current?${params}`);
}

export function queueHighQualitySemanticAnnotation(
  documentId: string,
): Promise<{jobId: string; status: string}> {
  return fetchJson(`/api/v1/documents/${documentId}/semantic-annotations/high-quality`, {
    method: "POST",
    headers: {
      "X-CSRF-Token": csrfToken(),
    },
  });
}

export function queueAllow8bRescueSemanticAnnotation(
  documentId: string,
): Promise<{jobId: string; status: string}> {
  return fetchJson(`/api/v1/documents/${documentId}/semantic-annotations/allow-8b-rescue`, {
    method: "POST",
    headers: {
      "X-CSRF-Token": csrfToken(),
    },
  });
}
