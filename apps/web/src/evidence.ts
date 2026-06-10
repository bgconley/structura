import type {EvidenceRef, EvidenceTarget} from "./types";

/**
 * Deterministic evidence locator selection.
 *
 * Mirrors lib/extraction/evidence_locator.py: prefer the richest anchor first
 * (table row > table > element > page), then break ties on specificity and a
 * stable serialization so reordered-but-equivalent provider evidence arrays
 * always select the same locator. Never read evidence[0] directly.
 */
export function selectEvidenceRef(evidence: EvidenceRef[] | undefined): EvidenceRef | undefined {
  if (!evidence?.length) {
    return undefined;
  }
  return [...evidence].sort(compareEvidenceRefs)[0];
}

export function evidenceTargetFromRef(
  documentId: string,
  ref: EvidenceRef | undefined,
  fieldPath?: string,
): EvidenceTarget {
  return {
    documentId,
    fieldPath,
    pageNumber: ref?.pageNumber,
    sourceText: ref?.sourceText,
    bbox: ref?.bbox,
    elementId: ref?.elementId,
    tableId: ref?.tableId,
    rowIndex: ref?.rowIndex,
    textSpan: ref?.textSpan,
  };
}

function compareEvidenceRefs(a: EvidenceRef, b: EvidenceRef): number {
  const bySpecificity = specificity(b) - specificity(a);
  if (bySpecificity !== 0) {
    return bySpecificity;
  }
  const byRank = locatorRank(a) - locatorRank(b);
  if (byRank !== 0) {
    return byRank;
  }
  const byPage = pageKey(a) - pageKey(b);
  if (byPage !== 0) {
    return byPage;
  }
  const byRow = rowKey(a) - rowKey(b);
  if (byRow !== 0) {
    return byRow;
  }
  return stableLocatorJson(a).localeCompare(stableLocatorJson(b));
}

function specificity(ref: EvidenceRef): number {
  return [
    ref.rowIndex !== undefined && ref.rowIndex !== null,
    Boolean(ref.tableId),
    Boolean(ref.elementId),
    Boolean(ref.bbox),
    Boolean(ref.textSpan),
    ref.pageNumber !== undefined && ref.pageNumber !== null,
  ].filter(Boolean).length;
}

function locatorRank(ref: EvidenceRef): number {
  if (ref.rowIndex !== undefined && ref.rowIndex !== null) {
    return 0;
  }
  if (ref.tableId) {
    return 1;
  }
  if (ref.elementId) {
    return 2;
  }
  if (ref.pageNumber !== undefined && ref.pageNumber !== null) {
    return 3;
  }
  return 4;
}

function pageKey(ref: EvidenceRef): number {
  return typeof ref.pageNumber === "number" ? ref.pageNumber : Number.MAX_SAFE_INTEGER;
}

function rowKey(ref: EvidenceRef): number {
  return typeof ref.rowIndex === "number" ? ref.rowIndex : Number.MAX_SAFE_INTEGER;
}

function stableLocatorJson(ref: EvidenceRef): string {
  return JSON.stringify({
    bbox: ref.bbox ?? null,
    elementId: normalizeText(ref.elementId),
    tableId: normalizeText(ref.tableId),
    textSpan: ref.textSpan ? {start: ref.textSpan.start, end: ref.textSpan.end, basis: ref.textSpan.basis ?? null} : null,
  });
}

function normalizeText(value: string | undefined): string {
  return (value ?? "").trim().toLowerCase().split(/\s+/).join(" ");
}
