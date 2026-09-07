import type {CanonicalLineItemSummary} from "./types";

// Decimal strings are the exact read representation; numbers support older responses.
export type RecordedLineItem = Omit<CanonicalLineItemSummary, "netAmount"> & {
  documentId?: string;
  selectedCandidateId?: string | null;
  code?: string | null;
  codeSystem?: string | null;
  serviceDate?: string | null;
  quantity?: string | number | null;
  unit?: string | null;
  unitPrice?: string | number | null;
  grossAmount?: string | number | null;
  discountAmount?: string | number | null;
  taxAmount?: string | number | null;
  netAmount?: string | number | null;
  categoryHint?: string | null;
  validation?: Record<string, unknown>;
  acceptedAt?: string | null;
  updatedAt?: string;
};

export function lineItemStatus(status?: string): string {
  if (["auto_accepted", "user_confirmed", "user_corrected"].includes(status ?? "")) return "Accepted under line-item policy";
  if (status === "rejected") return "Rejected; excluded from accepted facts";
  return "Recorded; needs review";
}
