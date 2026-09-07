import type {UploadAttempt, UploadCreate, UploadPolicy, UploadReference} from "./types";

export type UploadPhase = "queued" | "registering" | "sending" | "saving" | "checking" | "cancelling"
  | "needs_file" | "ready_to_send" | "replacement_needed" | "duplicate_choice" | "unknown"
  | "retry_wait" | "unavailable" | "accepted" | "reused" | "rejected" | "cancelled" | "expired";
export type UploadEntry = {localId: string; reference: UploadReference; displayName: string;
  metadata: UploadCreate | null; file: File | null; attempt: UploadAttempt | null;
  phase: UploadPhase; sentBytes: number; error: string | null; retryAt: number | null};
export type UploadQueueSnapshot = {entries: UploadEntry[]; policy: UploadPolicy | null; policyError: string | null;
  storageError: string | null; open: boolean; online: boolean; admissionRetryAt: number | null};
export const activeUploadPhases: UploadPhase[] = ["registering", "sending", "saving", "checking", "cancelling"];
export const terminalUploadPhases: UploadPhase[] = ["accepted", "reused", "rejected", "cancelled", "expired"];
export const uploadFileByteLimit = (policy: UploadPolicy) => Math.min(policy.maxFileBytes, policy.actorReservedBytes, policy.globalReservedBytes);
export function observedUploadPhase(attempt: UploadAttempt, hasFile: boolean): UploadPhase {
  if (["accepted", "reused", "rejected", "cancelled", "expired"].includes(attempt.state)) return attempt.state as UploadPhase;
  if (attempt.state === "awaiting_duplicate_decision") return "duplicate_choice";
  if (!hasFile) return "needs_file";
  return attempt.currentTransferId ? "replacement_needed" : "ready_to_send";
}
export function applyUploadObservation(entry: UploadEntry, attempt: UploadAttempt): UploadEntry {
  const terminal = ["accepted", "reused", "rejected", "cancelled", "expired"].includes(attempt.state);
  return {...entry, reference: {...entry.reference, uploadId: attempt.uploadId}, displayName: attempt.filename,
    attempt, phase: observedUploadPhase(attempt, !!entry.file), file: terminal ? null : entry.file,
    sentBytes: 0, error: attempt.error?.message ?? null, retryAt: null};
}
export function canDispatchUpload(entries: UploadEntry[], entry: UploadEntry, policy: UploadPolicy): boolean {
  if (!policy.available || entry.phase !== "queued" || !entry.file || !entry.metadata) return false;
  const active = entries.filter((item) => activeUploadPhases.includes(item.phase));
  if (active.length >= policy.actorActiveLimit) return false;
  // This is a conservative local budget, never a claim about other tabs/global capacity.
  const reserved = entries.filter((item) => item.localId !== entry.localId &&
    (activeUploadPhases.includes(item.phase) || item.attempt?.state === "awaiting_duplicate_decision" || item.attempt?.state === "receiving"))
    .reduce((bytes, item) => bytes + (item.attempt?.actualBytes ?? item.metadata?.declaredBytes ?? item.attempt?.declaredBytes ?? 0), 0);
  return reserved + entry.metadata.declaredBytes <= policy.actorReservedBytes;
}
export function clearUploadPrivateState(entry: UploadEntry): UploadEntry {
  return {...entry, displayName: "Previous upload", metadata: null, file: null, attempt: null,
    phase: "unknown", sentBytes: 0, error: null, retryAt: null};
}
