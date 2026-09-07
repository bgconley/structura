import {createHash} from "node:crypto";
import {expect, type Page, type Route} from "@playwright/test";
import type {UploadAttempt, UploadCreate, UploadDecision, UploadReceipt} from "../../../apps/web/src/uploads/types";
import {uploadAttempt, uploadId, uploadPolicy} from "./uploadAttemptFixture";

export function createUploadAttemptMock(options: {csrf?: string; documentId?: string;
  onAccepted?: (metadata: UploadCreate, receipt: UploadReceipt) => void} = {}) {
  const state = {policy: uploadPolicy(), attempts: new Map<string, UploadAttempt>(), metadata: new Map<string, UploadCreate>(),
    registrations: [] as UploadCreate[], contents: [] as {uploadId: string; body: Buffer; revision: string; replaced: string | undefined}[],
    decisions: [] as UploadDecision[], cancelled: [] as string[], duplicates: [] as {documentId: string; title: string}[],
    loseRegistrationResponse: false, loseContentResponse: false, failContent: 0, retryAfter: "1", acceptBeforeCancel: false,
    beforeContent: null as null | ((attempt: UploadAttempt) => Promise<void>), next: 100};
  function accept(attempt: UploadAttempt, reuseId?: string) {
    const receipt: UploadReceipt = {outcome: reuseId ? "reused" : "accepted", documentId: reuseId ?? options.documentId ?? uploadId(state.next++),
      assetId: uploadId(state.next++), batchId: reuseId ? null : uploadId(state.next++), jobId: reuseId ? null : uploadId(state.next++),
      sha256: attempt.sha256!, byteSize: attempt.actualBytes!, recordedAt: "2026-09-07T12:01:00.123456Z"};
    Object.assign(attempt, {state: receipt.outcome, receipt, duplicates: [], revision: uploadId(state.next++)});
    if (!reuseId) options.onAccepted?.(state.metadata.get(attempt.operationId)!, receipt);
    return attempt;
  }
  async function handle(route: Route, headers: Record<string, string> = {}): Promise<boolean> {
    const request = route.request(), url = new URL(request.url()), method = request.method();
    if (!/^\/api\/v1\/(upload-policy|uploads(?:\/[^/]+(?:\/content|\/decision)?)?)$/.test(url.pathname)) return false;
    const send = async (json: unknown, status = 200, extra: Record<string, string> = {}) => { await route.fulfill({status,
      headers: {"Access-Control-Expose-Headers": "Retry-After", ...headers, ...extra}, json}); return true; };
    if (method !== "GET" && options.csrf) expect(request.headers()["x-csrf-token"]).toBe(options.csrf);
    if (url.pathname === "/api/v1/upload-policy") return send(state.policy);
    if (url.pathname === "/api/v1/uploads" && method === "POST") {
      const metadata = request.postDataJSON() as UploadCreate; state.registrations.push(metadata);
      let attempt = [...state.attempts.values()].find((item) => item.operationId === metadata.operationId);
      if (attempt && JSON.stringify(state.metadata.get(metadata.operationId)) !== JSON.stringify(metadata)) return send({detail: "Upload revision or content conflicts."}, 409);
      if (!attempt) {
        attempt = {...uploadAttempt(metadata), uploadId: uploadId(state.next++), revision: uploadId(state.next++)};
        state.attempts.set(attempt.uploadId, attempt); state.metadata.set(metadata.operationId, metadata);
      }
      if (state.loseRegistrationResponse) { await route.abort(); return true; }
      return send(attempt);
    }
    const attempt = state.attempts.get(url.pathname.split("/")[4]);
    if (!attempt) return send({detail: "Upload unavailable."}, 404);
    if (method === "GET") return send(attempt);
    if (method === "DELETE") {
      state.cancelled.push(attempt.uploadId);
      if (state.acceptBeforeCancel && attempt.actualBytes && !attempt.receipt) accept(attempt);
      if (!attempt.receipt) Object.assign(attempt, {state: "cancelled", revision: uploadId(state.next++), duplicates: []});
      return send(attempt);
    }
    if (url.pathname.endsWith("/decision")) {
      const decision = request.postDataJSON() as UploadDecision; state.decisions.push(decision);
      if (decision.revision !== attempt.revision || attempt.state !== "awaiting_duplicate_decision") return send({detail: "Upload revision or content conflicts."}, 409);
      if (decision.decision === "use_existing" && !attempt.duplicates.some((match) => match.documentId === decision.documentId)) return send({detail: "Upload unavailable."}, 404);
      return send(accept(attempt, decision.decision === "use_existing" ? decision.documentId : undefined));
    }
    const body = request.postDataBuffer();
    if (!body) throw new Error("Controlled upload requests require inspectable raw bytes; use a buffer File fixture or the real HTTP transport test.");
    const revision = request.headers()["if-match"], replaced = request.headers()["x-replace-transfer-id"];
    state.contents.push({uploadId: attempt.uploadId, body, revision, replaced});
    expect(request.headers()["content-type"]).toBe("application/octet-stream");
    if (state.failContent) return send({detail: "Upload capacity is temporarily occupied."}, state.failContent, {"Retry-After": state.retryAfter});
    if (revision !== attempt.revision || (!attempt.receipt && attempt.currentTransferId && replaced !== attempt.currentTransferId)
      || ["expired", "cancelled", "rejected"].includes(attempt.state)) return send({detail: "Upload revision or content conflicts."}, 409);
    const hash = createHash("sha256").update(body).digest("hex");
    if (attempt.receipt) return hash === attempt.sha256 ? send(attempt) : send({detail: "Upload revision or content conflicts."}, 409);
    Object.assign(attempt, {state: "receiving", currentTransferId: uploadId(state.next++), revision: uploadId(state.next++),
      actualBytes: body.length, sha256: hash, detectedMimeType: "application/pdf"});
    await state.beforeContent?.(attempt);
    if (["cancelled", "rejected", "expired"].includes(attempt.state) || attempt.receipt) return send(attempt);
    if (state.duplicates.length) Object.assign(attempt, {state: "awaiting_duplicate_decision", duplicates: [...state.duplicates]});
    else accept(attempt);
    if (state.loseContentResponse) { await route.abort(); return true; }
    return send(attempt);
  }
  return {state, handle};
}
export async function installUploadAttemptMock(page: Page, options: Parameters<typeof createUploadAttemptMock>[0] = {}) {
  const mock = createUploadAttemptMock(options);
  await page.route("**/api/v1/upload**", async (route) => { if (!await mock.handle(route)) await route.fallback(); });
  return mock.state;
}
