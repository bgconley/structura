import type {UploadActor, UploadAttempt, UploadCreate, UploadPolicy, UploadReference} from "../../../apps/web/src/uploads/types";
export const uploadId = (n: number) => `bcbcbcbc-bcbc-4cbc-8cbc-${String(n).padStart(12, "0")}`;
export const uploadActor: UploadActor = {userId: uploadId(1), householdId: uploadId(2)};
export const uploadMetadata: UploadCreate = {operationId: uploadId(3), clientBatchId: uploadId(4), filename: "Private medical record.pdf",
  declaredBytes: 256, declaredMimeType: "application/pdf", source: "web_upload", title: "Private medical record"};
export function uploadPolicy(): UploadPolicy {
  return {protocol: "structura.upload_attempt.v1", available: true, maxFileBytes: 104857600, actorActiveLimit: 2, globalActiveLimit: 4,
    actorReservedBytes: 209715200, globalReservedBytes: 419430400, queueReferenceLimit: 100, absoluteSeconds: 600,
    idleSeconds: 30, heldSeconds: 1800, inactiveSeconds: 1800, controlBytes: 16384,
    mimeTypes: ["application/pdf", "image/png", "image/jpeg", "image/tiff", "image/webp"], validation: "recognized_signature_and_metadata_consistency"};
}
export function uploadAttempt(metadata = uploadMetadata): UploadAttempt {
  return {uploadId: uploadId(5), operationId: metadata.operationId, clientBatchId: metadata.clientBatchId, revision: uploadId(6),
    state: "awaiting_content", filename: metadata.filename, declaredBytes: metadata.declaredBytes, actualBytes: null, sha256: null,
    detectedMimeType: null, currentTransferId: null, createdAt: "2026-09-07T12:00:00.123456Z", updatedAt: "2026-09-07T12:00:00.123456Z",
    receipt: null, error: null, duplicates: []};
}
export function acceptedUpload(outcome: "accepted" | "reused" = "accepted"): UploadAttempt {
  const value = uploadAttempt();
  return {...value, state: outcome, actualBytes: value.declaredBytes, sha256: "a".repeat(64), detectedMimeType: "application/pdf", currentTransferId: uploadId(7),
    receipt: {outcome, documentId: uploadId(8), assetId: uploadId(9), batchId: outcome === "accepted" ? uploadId(10) : null,
      jobId: outcome === "accepted" ? uploadId(11) : null, sha256: "a".repeat(64), byteSize: value.declaredBytes, recordedAt: value.updatedAt}};
}
export function uploadReference(): UploadReference {
  return {...uploadActor, localId: uploadId(12), operationId: uploadMetadata.operationId, clientBatchId: uploadMetadata.clientBatchId,
    registrationSha256: "b".repeat(64), source: "web_upload"};
}
