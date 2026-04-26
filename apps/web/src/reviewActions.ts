import type {EvidenceRef, EvidenceTarget, FieldCandidate, ReviewTask} from "./types";

export function referenceCandidate(
  task: ReviewTask,
  candidates: FieldCandidate[],
): FieldCandidate | undefined {
  return candidates.find((candidate) => candidate.fieldPath === task.fieldPath) ?? candidates[0];
}

export function evidenceTargetFromCandidate(candidate: FieldCandidate): EvidenceTarget {
  const evidence = candidate.evidence[0] as EvidenceRef | undefined;
  return {
    documentId: candidate.documentId,
    fieldPath: candidate.fieldPath,
    pageNumber: evidence?.pageNumber,
    sourceText: evidence?.sourceText,
    bbox: evidence?.bbox,
    elementId: evidence?.elementId,
    tableId: evidence?.tableId,
    rowIndex: evidence?.rowIndex,
    textSpan: evidence?.textSpan,
  };
}

export function coerceCorrectionValue(
  rawValue: string,
  valueType: string,
  currency?: string,
): {value: unknown; metadata: Record<string, unknown>} {
  const trimmed = rawValue.trim();
  const metadata: Record<string, unknown> = {valueType};
  if (currency) {
    metadata.currency = currency;
  }
  if (valueType === "money") {
    const amount = Number.parseFloat(trimmed.replace(/[^0-9.-]/g, ""));
    return {
      value: {amount: Number.isFinite(amount) ? amount : 0, currency: currency ?? "USD"},
      metadata: {...metadata, currency: currency ?? "USD"},
    };
  }
  if (valueType === "number") {
    const value = Number.parseFloat(trimmed);
    return {value: Number.isFinite(value) ? value : 0, metadata};
  }
  if (valueType === "integer") {
    const value = Number.parseInt(trimmed, 10);
    return {value: Number.isFinite(value) ? value : 0, metadata};
  }
  if (valueType === "boolean") {
    return {value: ["1", "true", "yes"].includes(trimmed.toLowerCase()), metadata};
  }
  return {value: trimmed, metadata};
}

export function schemaFromReviewTask(task: ReviewTask): string {
  if (task.fieldPath?.startsWith("invoice.")) {
    return "invoice";
  }
  if (task.fieldPath?.startsWith("medical_eob.")) {
    return "medical_eob";
  }
  if (task.fieldPath?.startsWith("receipt.")) {
    return "receipt";
  }
  return "receipt";
}
