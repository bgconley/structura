import {canonical, extraction} from "./authority";
import type {HistorySelector, LineHistory, SourceSnapshot} from "./types";
import {digest, evidence, nullableText, nullableUuid, object, requireValue, slot, text, timestamp, unique, uuid, values} from "./validation";

function source(v: unknown, documentId: string): v is SourceSnapshot {
  if (!object(v) || v.schemaVersion !== "line_item_source.v1" || !object(v.candidate)) return false;
  const c = v.candidate;
  return uuid(c.id) && c.documentId === documentId && slot(c) && values(c) && nullableUuid(c.extractionId)
    && text(c.sourceEngine) && nullableText(c.candidateGroup) && extraction(v.extraction, documentId)
    && (!v.extraction || v.extraction.id === c.extractionId) && evidence(v.evidence)
    && (v.original === null || (object(v.original) && uuid(v.original.id) && digest(v.original.sha256)))
    && digest(v.validationSha256) && digest(v.storedEvidenceSha256);
}
function historyValue(v: unknown, documentId: string, canonicalId: unknown) {
  return v === null || (object(v) && canonical(v.canonical, documentId) && v.canonical.id === canonicalId
    && (v.sourceCoverage === "recorded" ? source(v.source, documentId)
      && (v.canonical.selectedCandidateId === null || v.source.candidate.id === v.canonical.selectedCandidateId)
      : v.sourceCoverage === "legacy_unestablished" && v.source === null));
}
export function parseLineHistory(v: unknown, documentId: string, selector: HistorySelector): LineHistory {
  requireValue(object(v) && v.documentId === documentId && Array.isArray(v.items) && nullableText(v.nextCursor));
  for (const entry of v.items) {
    requireValue(object(entry) && uuid(entry.id) && entry.documentId === documentId && nullableUuid(entry.canonicalLineItemId)
      && nullableUuid(entry.sourceCandidateId) && text(entry.operation) && text(entry.actorLabel) && timestamp(entry.occurredAt)
      && nullableText(entry.comment) && (selector.canonicalLineItemId ? entry.canonicalLineItemId === selector.canonicalLineItemId
        : entry.sourceCandidateId === selector.sourceCandidateId));
    if (entry.coverage === "complete") {
      requireValue(["create", "replace", "reject_selected", "reject_candidate"].includes(entry.operation)
        && historyValue(entry.before, documentId, entry.canonicalLineItemId) && historyValue(entry.after, documentId, entry.canonicalLineItemId)
        && (entry.source === null || (source(entry.source, documentId) && entry.source.candidate.id === entry.sourceCandidateId)) && entry.legacySummary === null);
      if (entry.operation === "reject_candidate") requireValue(entry.canonicalLineItemId === null && entry.before === null && entry.after === null && entry.source);
      else {
        requireValue(uuid(entry.canonicalLineItemId) && entry.after && (entry.operation === "create" ? entry.before === null : entry.before));
        if (entry.operation === "reject_selected") requireValue(object(entry.before) && canonical(entry.before.canonical, documentId)
          && entry.before.canonical.selected && object(entry.after) && canonical(entry.after.canonical, documentId) && !entry.after.canonical.selected);
        if (entry.operation !== "reject_selected") requireValue(entry.source && object(entry.after)
          && canonical(entry.after.canonical, documentId) && entry.after.canonical.selected
          && (entry.after.canonical.selectedCandidateId === null || entry.after.canonical.selectedCandidateId === entry.sourceCandidateId));
      }
    }
    else requireValue(entry.coverage === "legacy_partial" && entry.before === null && entry.after === null && entry.source === null
      && object(entry.legacySummary) && entry.legacySummary.precision === "legacy_unestablished"
      && ["description", "status", "netAmount"].every((key) => nullableText(entry.legacySummary && (entry.legacySummary as Record<string, unknown>)[key])));
  }
  const result = v as LineHistory;
  requireValue(unique(result.items, (entry) => entry.id));
  return result;
}
