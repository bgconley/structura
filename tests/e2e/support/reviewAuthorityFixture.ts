import type {CanonicalField, CanonicalFieldResponse, FieldDecision, FieldPathGuard} from "../../../apps/web/src/types";

export function reviewAuthorityFixture(documentId: string, items: CanonicalField[] = [],
  decisions: FieldDecision[] = [], pathGuards: FieldPathGuard[] = []): CanonicalFieldResponse {
  return {authorityVersion: "human_authority.v1", items, decisions, pathGuards,
    projection: {schemaVersion: "accepted_fact_projection.v1", documentId, state: "current",
      acceptedFactRevision: 1, projectionRevision: 1,
      acceptedFactsSha256: "a".repeat(64), indexedMetadataSha256: "b".repeat(64)}};
}
