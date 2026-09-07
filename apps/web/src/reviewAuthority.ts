import {canonicalFieldForCandidate} from "./reviewActions";
import type {CanonicalField, CanonicalFieldResponse, FieldCandidate, FieldDecisionPreconditions} from "./types";

const UUID = /^[\da-f]{8}-[\da-f]{4}-[\da-f]{4}-[\da-f]{4}-[\da-f]{12}$/i;
const unavailable = "Field decision history is unavailable or inconsistent. Refresh before making a field decision.";
const object = (value: unknown): value is Record<string, unknown> => !!value && typeof value === "object" && !Array.isArray(value);
const uuid = (value: unknown): value is string => typeof value === "string" && UUID.test(value);
const nullableUuid = (value: unknown) => value === null || uuid(value);
const ordinal = (value: unknown): value is number => Number.isInteger(value) && Number(value) > 0 && Number(value) <= 2147483647;
const timestamp = (value: unknown): value is string => typeof value === "string" && /^\d{4}-\d{2}-\d{2}T.*(?:Z|[+-]\d{2}:\d{2})$/.test(value) && Number.isFinite(Date.parse(value));
const digest = (value: unknown) => typeof value === "string" && /^[a-f\d]{64}$/.test(value);

// The versioned envelope proves that absent decisions/guards were actually read.
// Old items-only responses cannot mean "there was no previous human decision."
export function parseCanonicalFieldResponse(value: unknown, documentId: string): CanonicalFieldResponse {
  if (!object(value) || value.authorityVersion !== "human_authority.v1"
    || !Array.isArray(value.items) || !Array.isArray(value.decisions) || !Array.isArray(value.pathGuards)
    || !object(value.projection)) throw new Error(unavailable);
  const unique = (rows: unknown[], key: (row: Record<string, unknown>) => string,
    valid: (row: Record<string, unknown>) => boolean) => {
    const keys = new Set<string>();
    return rows.every((row) => {
      if (!object(row) || row.documentId !== documentId || typeof row.fieldPath !== "string" || !row.fieldPath || !valid(row)) return false;
      const identity = key(row);
      if (keys.has(identity)) return false;
      keys.add(identity); return true;
    });
  };
  const fieldKey = (row: Record<string, unknown>) => JSON.stringify([row.fieldPath, row.ordinal ?? 1]);
  const fieldsValid = unique(value.items, fieldKey, (row) => typeof row.id === "string"
    && ordinal(row.ordinal ?? 1) && typeof row.valueType === "string" && typeof row.reviewStatus === "string");
  const decisionsValid = unique(value.decisions, fieldKey, (row) => uuid(row.id) && uuid(row.revision)
    && ordinal(row.ordinal) && ["confirmed", "corrected", "rejected", "protected_legacy"].includes(String(row.disposition))
    && ["live_review", "legacy_current_field"].includes(String(row.origin))
    && nullableUuid(row.canonicalFieldId) && nullableUuid(row.reviewEventId) && nullableUuid(row.actorUserId)
    && (row.decidedAt === null || timestamp(row.decidedAt)) && timestamp(row.recordedAt)
    && (row.origin !== "live_review" || (row.disposition !== "protected_legacy" && row.decidedAt !== null)));
  const guardsValid = unique(value.pathGuards, (row) => String(row.fieldPath), (row) => uuid(row.id)
    && uuid(row.revision) && ["active", "resolved"].includes(String(row.status))
    && row.origin === "legacy_path_rejection" && nullableUuid(row.reviewEventId) && nullableUuid(row.actorUserId));
  const projection = value.projection;
  const projectionValid = projection.schemaVersion === "accepted_fact_projection.v1" && projection.documentId === documentId
    && (projection.state === "unestablished"
      ? projection.acceptedFactRevision === 0 && projection.projectionRevision === 0
        && projection.acceptedFactsSha256 === null && projection.indexedMetadataSha256 === null
      : projection.state === "current" && Number.isSafeInteger(projection.acceptedFactRevision)
        && Number(projection.acceptedFactRevision) > 0 && Number.isSafeInteger(projection.projectionRevision)
        && Number(projection.projectionRevision) >= Number(projection.acceptedFactRevision)
        && digest(projection.acceptedFactsSha256) && digest(projection.indexedMetadataSha256));
  if (!fieldsValid || !decisionsValid || !guardsValid || !projectionValid) throw new Error(unavailable);
  const response = value as CanonicalFieldResponse;
  if (response.decisions.some((decision) => decision.canonicalFieldId !== null
    && !response.items.some((field) => field.id === decision.canonicalFieldId
      && field.documentId === decision.documentId && field.fieldPath === decision.fieldPath
      && (field.ordinal ?? 1) === decision.ordinal))) throw new Error(unavailable);
  return response;
}

export function fieldDecisionPreconditions(authority: CanonicalFieldResponse | null,
  candidate: Pick<FieldCandidate, "documentId" | "fieldPath" | "ordinal">): FieldDecisionPreconditions | null {
  if (!authority || authority.projection.documentId !== candidate.documentId || !ordinal(candidate.ordinal ?? 1)) return null;
  const field = canonicalFieldForCandidate(authority.items, candidate);
  if (field && !timestamp(field.updatedAt)) return null;
  const decision = authority.decisions.find((item) => item.documentId === candidate.documentId
    && item.fieldPath === candidate.fieldPath && item.ordinal === (candidate.ordinal ?? 1));
  const guard = authority.pathGuards.find((item) => item.documentId === candidate.documentId
    && item.fieldPath === candidate.fieldPath && item.status === "active");
  return {expectedUpdatedAt: field?.updatedAt ?? null, expectedDecisionRevision: decision?.revision ?? null,
    expectedPathGuardRevision: guard?.revision ?? null};
}

export function recordedFieldStatus(authority: CanonicalFieldResponse, field: CanonicalField): string {
  const decision = authority.decisions.find((item) => item.documentId === field.documentId
    && item.fieldPath === field.fieldPath && item.ordinal === (field.ordinal ?? 1));
  if (decision?.disposition === "rejected" || field.reviewStatus === "rejected") return "Rejected; excluded from accepted facts";
  if (authority.projection.state === "unestablished") return "Recorded value; accepted facts not yet verified";
  const accepted = ["auto_accepted", "user_confirmed", "user_corrected"].includes(field.reviewStatus)
    && (decision ? ["confirmed", "corrected"].includes(decision.disposition) && decision.canonicalFieldId === field.id
      : !authority.pathGuards.some((guard) => guard.documentId === field.documentId
        && guard.fieldPath === field.fieldPath && guard.status === "active"));
  return accepted ? "Accepted value" : "Not selected as an accepted fact";
}
