import {csrfToken, fetchJson} from "./api";
import type {
  CanonicalField,
  FieldCandidate,
  ReviewActionPayload,
  ReviewTask,
} from "./types";

export async function listReviewTasks(status?: string): Promise<ReviewTask[]> {
  const params = new URLSearchParams();
  if (status) {
    params.set("status", status);
  }
  const payload = await fetchJson<{items: ReviewTask[]}>(
    `/api/v1/review-tasks${params.size ? `?${params}` : ""}`,
  );
  return payload.items;
}

export async function listFieldCandidates(
  documentId: string,
  fieldPath?: string,
): Promise<FieldCandidate[]> {
  const params = new URLSearchParams();
  if (fieldPath) {
    params.set("fieldPath", fieldPath);
  }
  const payload = await fetchJson<{items: FieldCandidate[]}>(
    `/api/v1/documents/${documentId}/field-candidates${params.size ? `?${params}` : ""}`,
  );
  return payload.items;
}

export async function listCanonicalFields(documentId: string): Promise<CanonicalField[]> {
  const payload = await fetchJson<{items: CanonicalField[]}>(
    `/api/v1/documents/${documentId}/canonical-fields`,
  );
  return payload.items;
}

export async function postReviewAction(
  payload: ReviewActionPayload,
): Promise<{ok: boolean; reviewEventId?: string; jobId?: string}> {
  return fetchJson(`/api/v1/documents/${payload.documentId}/review-actions`, {
    method: "POST",
    headers: {"Content-Type": "application/json", "X-CSRF-Token": csrfToken()},
    body: JSON.stringify(payload),
  });
}
