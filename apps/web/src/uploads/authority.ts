import type {UploadAttempt, UploadIdentity, UploadPolicy, UploadReceipt} from "./types";

const object = (v: unknown): v is Record<string, unknown> => !!v && typeof v === "object" && !Array.isArray(v);
const text = (v: unknown): v is string => typeof v === "string";
const positive = (v: unknown): v is number => typeof v === "number" && Number.isSafeInteger(v) && v > 0;
export const uploadUuid = (v: unknown): v is string => text(v) && /^[a-f\d]{8}(?:-[a-f\d]{4}){3}-[a-f\d]{12}$/i.test(v);
export const uploadDigest = (v: unknown): v is string => text(v) && /^[a-f\d]{64}$/.test(v);
const timestamp = (v: unknown) => text(v) && /^\d{4}-\d{2}-\d{2}T.*(?:Z|[+-]\d{2}:\d{2})$/.test(v) && Number.isFinite(Date.parse(v));
function requireUpload(value: unknown): asserts value {
  if (!value) throw new Error("Upload details are unavailable or inconsistent. Check this upload before sending again.");
}
function receipt(v: unknown): v is UploadReceipt {
  return object(v) && uploadUuid(v.documentId) && uploadUuid(v.assetId) && uploadDigest(v.sha256)
    && positive(v.byteSize) && timestamp(v.recordedAt)
    && (v.outcome === "accepted" ? uploadUuid(v.batchId) && uploadUuid(v.jobId)
      : v.outcome === "reused" && v.batchId === null && v.jobId === null);
}
export function parseUploadAttempt(value: unknown, expected: UploadIdentity): UploadAttempt {
  requireUpload(object(value) && uploadUuid(value.uploadId) && uploadUuid(value.revision)
    && value.operationId === expected.operationId && value.clientBatchId === expected.clientBatchId
    && uploadUuid(value.operationId) && uploadUuid(value.clientBatchId)
    && (!expected.uploadId || value.uploadId === expected.uploadId)
    && text(value.filename) && !!value.filename && positive(value.declaredBytes)
    && (expected.filename === undefined || value.filename === expected.filename)
    && (expected.declaredBytes === undefined || value.declaredBytes === expected.declaredBytes)
    && timestamp(value.createdAt) && timestamp(value.updatedAt)
    && ["awaiting_content", "receiving", "awaiting_duplicate_decision", "accepted", "reused", "rejected", "cancelled", "expired"].includes(String(value.state))
    && (value.actualBytes === null || positive(value.actualBytes)) && (value.sha256 === null || uploadDigest(value.sha256))
    && (value.detectedMimeType === null || text(value.detectedMimeType))
    && (value.currentTransferId === null || uploadUuid(value.currentTransferId))
    && (value.receipt === null || receipt(value.receipt))
    && (value.error === null || (object(value.error) && text(value.error.code) && text(value.error.message)))
    && Array.isArray(value.duplicates) && value.duplicates.length <= 20
    && value.duplicates.every((match) => object(match) && uploadUuid(match.documentId) && text(match.title)));
  const result = value as UploadAttempt;
  requireUpload(new Set(result.duplicates.map((match) => match.documentId)).size === result.duplicates.length);
  const accepted = result.state === "accepted" || result.state === "reused";
  requireUpload(accepted === !!result.receipt);
  if (result.receipt) requireUpload(result.receipt.outcome === result.state && result.receipt.sha256 === result.sha256
    && result.receipt.byteSize === result.actualBytes && result.actualBytes === result.declaredBytes);
  if (result.state === "receiving" || result.state === "awaiting_duplicate_decision") requireUpload(result.currentTransferId);
  if (result.state === "awaiting_duplicate_decision") requireUpload(result.actualBytes === result.declaredBytes && result.sha256 && result.detectedMimeType);
  else requireUpload(result.duplicates.length === 0);
  return result;
}
export function parseUploadPolicy(value: unknown): UploadPolicy {
  requireUpload(object(value) && value.protocol === "structura.upload_attempt.v1" && typeof value.available === "boolean"
    && ["maxFileBytes", "actorActiveLimit", "globalActiveLimit", "actorReservedBytes", "globalReservedBytes", "queueReferenceLimit",
      "absoluteSeconds", "idleSeconds", "heldSeconds", "inactiveSeconds", "controlBytes"].every((key) => positive(value[key]))
    && Array.isArray(value.mimeTypes) && value.mimeTypes.length > 0 && value.mimeTypes.length <= 20
    && value.mimeTypes.every((mime) => text(mime) && /^[a-z0-9.+-]+\/[a-z0-9.+-]+$/i.test(mime)) && text(value.validation));
  requireUpload(Number(value.maxFileBytes) <= 100 * 1024 * 1024 && Number(value.queueReferenceLimit) <= 1000
    && Number(value.actorActiveLimit) <= 100 && Number(value.globalActiveLimit) <= 1000
    && Number(value.absoluteSeconds) <= 3600 && Number(value.idleSeconds) <= 300
    && Number(value.heldSeconds) <= 86400 && Number(value.inactiveSeconds) <= 86400 && Number(value.controlBytes) <= 16384);
  return value as UploadPolicy;
}
