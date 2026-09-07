import {uploadDigest, uploadUuid} from "./authority";
import {sha256} from "@noble/hashes/sha2.js";
import type {UploadActor, UploadCreate, UploadReference, UploadSource} from "./types";

const version = "structura.upload_references.v1";
const sources: UploadSource[] = ["web_upload", "api_upload", "mobile_scan", "bulk_import"];
const storageKey = (actor: UploadActor) => `${version}:${actor.userId}:${actor.householdId}`;
const isObject = (v: unknown): v is Record<string, unknown> => !!v && typeof v === "object" && !Array.isArray(v);
export function uploadRegistration(file: Pick<File, "name" | "size" | "type">, source: UploadSource,
  operationId: string, clientBatchId: string): UploadCreate {
  return {operationId, clientBatchId, filename: file.name, declaredBytes: file.size,
    declaredMimeType: file.type || null, source, title: file.name.replace(/\.[^.]+$/, "")};
}
export async function registrationDigest(registration: UploadCreate): Promise<string> {
  // Explicit property order makes a reselected File comparable without retaining its private metadata.
  const {operationId, clientBatchId, filename, declaredBytes, declaredMimeType, source, title} = registration;
  const bytes = new TextEncoder().encode(JSON.stringify({operationId, clientBatchId, filename, declaredBytes, declaredMimeType, source, title}));
  return [...sha256(bytes)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}
export function parseUploadReferences(raw: string | null, actor: UploadActor, limit: number): UploadReference[] {
  if (raw === null) return [];
  if (raw.length > 1024 * 1024) throw new Error("Stored upload recovery references are too large.");
  const value: unknown = JSON.parse(raw);
  if (!isObject(value) || value.schemaVersion !== version || !Array.isArray(value.items)
    || value.items.length > Math.min(limit, 1000)) throw new Error("Stored upload recovery references are invalid.");
  const keys = ["userId", "householdId", "localId", "operationId", "clientBatchId", "uploadId", "registrationSha256", "source"];
  for (const item of value.items) {
    if (!isObject(item) || Object.keys(item).some((key) => !keys.includes(key))
      || ["userId", "householdId", "localId", "operationId", "clientBatchId"].some((key) => !uploadUuid(item[key]))
      || (item.uploadId !== undefined && !uploadUuid(item.uploadId)) || !uploadDigest(item.registrationSha256)
      || !sources.includes(item.source as UploadSource) || item.userId !== actor.userId || item.householdId !== actor.householdId)
      throw new Error("Stored upload recovery references do not match this account.");
  }
  const result = value.items as UploadReference[];
  if (new Set(result.map((item) => item.localId)).size !== result.length
    || new Set(result.map((item) => item.operationId)).size !== result.length)
    throw new Error("Stored upload recovery references contain duplicate identities.");
  return result;
}
export function readUploadReferences(actor: UploadActor, limit: number, storage: Pick<Storage, "getItem"> = sessionStorage) {
  return parseUploadReferences(storage.getItem(storageKey(actor)), actor, limit);
}
export function writeUploadReferences(actor: UploadActor, references: UploadReference[], storage: Pick<Storage, "setItem" | "removeItem"> = sessionStorage) {
  // Whitelist fields even when a caller's object contains in-memory File/receipt state.
  const items = references.map(({userId, householdId, localId, operationId, clientBatchId, uploadId, registrationSha256, source}) =>
    ({userId, householdId, localId, operationId, clientBatchId, uploadId, registrationSha256, source}));
  const raw = JSON.stringify({schemaVersion: version, items});
  parseUploadReferences(raw, actor, 1000);
  if (items.length) storage.setItem(storageKey(actor), raw); else storage.removeItem(storageKey(actor));
}
