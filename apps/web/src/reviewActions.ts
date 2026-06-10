import {evidenceTargetFromRef, selectEvidenceRef} from "./evidence";
import type {EvidenceTarget, FieldCandidate, ReviewTask} from "./types";

export function referenceCandidate(
  task: ReviewTask,
  candidates: FieldCandidate[],
): FieldCandidate | undefined {
  return candidates.find((candidate) => candidate.fieldPath === task.fieldPath) ?? candidates[0];
}

export function evidenceTargetFromCandidate(candidate: FieldCandidate): EvidenceTarget {
  // Deterministic richer-anchor-first selection; mirrors the backend
  // evidence locator instead of trusting provider evidence array order.
  const evidence = selectEvidenceRef(candidate.evidence);
  return evidenceTargetFromRef(candidate.documentId, evidence, candidate.fieldPath);
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

