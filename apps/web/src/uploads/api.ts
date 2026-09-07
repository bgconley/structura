import {apiBaseUrl, ApiError, csrfToken} from "../api";
import {sessionRequestScope} from "../sessionRequests";
import {parseUploadAttempt, parseUploadPolicy} from "./authority";
import type {UploadCreate, UploadDecision, UploadIdentity} from "./types";

export class UploadHttpError extends ApiError {
  constructor(status: number, message: string, public readonly retryAfterMs: number | null = null) {
    super(status, message); this.name = "UploadHttpError";
  }
}
export function uploadHttpError(status: number, body: unknown, retryAfter: string | null): UploadHttpError {
  const detail = body && typeof body === "object" && "detail" in body ? body.detail : null;
  return new UploadHttpError(status, typeof detail === "string" && detail ? detail : `Upload request failed (${status}).`,
    retryAfter && /^\d{1,5}$/.test(retryAfter) ? Math.max(1, Number(retryAfter)) * 1000 : null);
}
const path = (uploadId: string) => `/api/v1/uploads/${encodeURIComponent(uploadId)}`;
async function control(endpoint: string, method: "GET" | "POST" | "DELETE", body?: unknown, signal?: AbortSignal): Promise<unknown> {
  const scope = sessionRequestScope(signal);
  const response = await fetch(`${apiBaseUrl}${endpoint}`, {method, credentials: "include", signal: scope.signal,
    headers: {Accept: "application/json", ...(method === "GET" ? {} : {"X-CSRF-Token": csrfToken()}),
      ...(body === undefined ? {} : {"Content-Type": "application/json"})},
    ...(body === undefined ? {} : {body: JSON.stringify(body)})});
  scope.assertCurrent();
  let payload: unknown;
  try { payload = await response.json(); } catch { payload = null; }
  scope.assertCurrent();
  if (!response.ok) {
    if (response.status === 401) scope.unauthorized();
    throw uploadHttpError(response.status, payload, response.headers.get("Retry-After"));
  }
  return payload;
}
export async function getUploadPolicy(signal?: AbortSignal) {
  return parseUploadPolicy(await control("/api/v1/upload-policy", "GET", undefined, signal));
}
export async function registerUpload(metadata: UploadCreate, signal?: AbortSignal) {
  return parseUploadAttempt(await control("/api/v1/uploads", "POST", metadata, signal), metadata);
}
export async function getUpload(expected: UploadIdentity & {uploadId: string}, signal?: AbortSignal) {
  return parseUploadAttempt(await control(path(expected.uploadId), "GET", undefined, signal), expected);
}
export async function decideUpload(expected: UploadIdentity & {uploadId: string}, decision: UploadDecision, signal?: AbortSignal) {
  return parseUploadAttempt(await control(`${path(expected.uploadId)}/decision`, "POST", decision, signal), expected);
}
export async function cancelUpload(expected: UploadIdentity & {uploadId: string}, signal?: AbortSignal) {
  return parseUploadAttempt(await control(path(expected.uploadId), "DELETE", undefined, signal), expected);
}
