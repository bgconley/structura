import {csrfToken, fetchJson} from "./api";
import type {
  DocumentDeadline,
  DocumentRelationship,
  RelationshipWrite,
  SmartViewSummary,
  TimelineEvent,
} from "./types";

export async function listRelationships(params: {
  documentId?: string;
  status?: string;
} = {}): Promise<DocumentRelationship[]> {
  const query = new URLSearchParams();
  if (params.documentId) {
    query.set("documentId", params.documentId);
  }
  if (params.status) {
    query.set("status", params.status);
  }
  const payload = await fetchJson<{items: DocumentRelationship[]}>(
    `/api/v1/relationships${query.size ? `?${query}` : ""}`,
  );
  return payload.items;
}

export async function createRelationship(payload: RelationshipWrite): Promise<DocumentRelationship> {
  return fetchJson<DocumentRelationship>("/api/v1/relationships", {
    method: "POST",
    headers: {"Content-Type": "application/json", "X-CSRF-Token": csrfToken()},
    body: JSON.stringify(payload),
  });
}

export async function acceptRelationship(
  relationshipId: string,
  comment?: string,
): Promise<DocumentRelationship> {
  return relationshipDecision(relationshipId, "accept", comment);
}

export async function rejectRelationship(
  relationshipId: string,
  comment?: string,
): Promise<DocumentRelationship> {
  return relationshipDecision(relationshipId, "reject", comment);
}

export async function listDeadlines(params: {documentId?: string} = {}): Promise<DocumentDeadline[]> {
  const query = new URLSearchParams();
  if (params.documentId) {
    query.set("documentId", params.documentId);
  }
  const payload = await fetchJson<{items: DocumentDeadline[]}>(
    `/api/v1/deadlines${query.size ? `?${query}` : ""}`,
  );
  return payload.items;
}

export async function listTimeline(params: {
  documentId?: string;
  contactId?: string;
} = {}): Promise<TimelineEvent[]> {
  const query = new URLSearchParams();
  if (params.documentId) {
    query.set("documentId", params.documentId);
  }
  if (params.contactId) {
    query.set("contactId", params.contactId);
  }
  const payload = await fetchJson<{items: TimelineEvent[]}>(
    `/api/v1/timeline${query.size ? `?${query}` : ""}`,
  );
  return payload.items;
}

export async function listSmartViews(): Promise<SmartViewSummary[]> {
  const payload = await fetchJson<{items: SmartViewSummary[]}>("/api/v1/smart-views");
  return payload.items;
}

function relationshipDecision(
  relationshipId: string,
  action: "accept" | "reject",
  comment?: string,
): Promise<DocumentRelationship> {
  return fetchJson<DocumentRelationship>(`/api/v1/relationships/${relationshipId}/${action}`, {
    method: "POST",
    headers: {"Content-Type": "application/json", "X-CSRF-Token": csrfToken()},
    body: JSON.stringify({comment}),
  });
}
