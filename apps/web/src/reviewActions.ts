import {evidenceTargetFromRef, selectEvidenceRef} from "./evidence";
import type {EvidenceTarget, FieldCandidate, ReviewTask} from "./types";

export function referenceCandidate(
  task: ReviewTask,
  candidates: FieldCandidate[],
): FieldCandidate | undefined {
  return candidates.find((candidate) => candidate.documentId === task.documentId
    && candidate.fieldPath === task.fieldPath);
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
    if (!currency || !/^[A-Z]{3}$/.test(currency)) {
      throw new Error("Enter a three-letter uppercase currency code.");
    }
    const amount = parseDecimalCorrection(trimmed);
    return {
      value: {amount, currency},
      metadata,
    };
  }
  if (valueType === "number") {
    return {value: parseDecimalCorrection(trimmed), metadata};
  }
  if (valueType === "integer") {
    if (!/^[+-]?\d+$/.test(trimmed) || !Number.isSafeInteger(Number(trimmed))) {
      throw new Error("Enter a whole integer within the supported range.");
    }
    return {value: Number(trimmed), metadata};
  }
  if (valueType === "boolean") {
    const normalized = trimmed.toLowerCase();
    if (!["true", "false", "yes", "no", "1", "0"].includes(normalized)) {
      throw new Error("Enter true or false (yes/no and 1/0 are also supported).");
    }
    return {value: ["true", "yes", "1"].includes(normalized), metadata};
  }
  return {value: trimmed, metadata};
}

function parseDecimalCorrection(value: string): number {
  if (!/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$/.test(value)) {
    throw new Error("Enter a decimal amount such as 1234.56, without currency or separators.");
  }
  const fraction = (value.split(".")[1] ?? "").replace(/0+$/, "");
  const number = Number(value);
  if (fraction.length > 4) {
    throw new Error("Use at most four decimal places; values are not rounded.");
  }
  if (!Number.isFinite(number) || Math.abs(number) >= 100_000_000_000_000) {
    throw new Error("The amount exceeds the supported range.");
  }
  // Reject decimal text that JavaScript cannot carry to JSON without changing
  // the user's value, even when it fits the database's numeric(18,4) range.
  const units = (text: string) => {
    const negative = text.startsWith("-");
    const [whole, decimals = ""] = text.replace(/^[+-]/, "").split(".");
    return BigInt(`${whole || "0"}${decimals.padEnd(4, "0").slice(0, 4)}`) * (negative ? -1n : 1n);
  };
  if (units(value) !== units(number.toFixed(4))) {
    throw new Error("This amount cannot be represented exactly; use a smaller value.");
  }
  return number;
}
