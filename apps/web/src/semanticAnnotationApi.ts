import {fetchJson} from "./api";
import type {SemanticAnnotationResponse} from "./types";

export function getCurrentSemanticAnnotation(
  documentId: string,
  qualityMode = "smart",
): Promise<SemanticAnnotationResponse> {
  const params = new URLSearchParams({qualityMode});
  return fetchJson(`/api/v1/documents/${documentId}/semantic-annotations/current?${params}`);
}
