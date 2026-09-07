import {createHash, randomUUID} from "node:crypto";
import {mkdir, readFile, writeFile} from "node:fs/promises";
import {dirname} from "node:path";
import {deflateSync} from "node:zlib";
import {expect, type Page, type TestInfo} from "@playwright/test";
import type {UploadAttempt, UploadCreate} from "../../../apps/web/src/uploads/types";
import {writeSimplePdf} from "./pdf";

export const uploadLiveEnabled = process.env.STRUCTURA_E2E_LIVE === "1" && process.env.STRUCTURA_E2E_UPLOAD_LIVE === "1";
export function uploadLiveConfig(env: Record<string, string | undefined> = process.env) {
  for (const name of ["STRUCTURA_E2E_WEB_URL", "STRUCTURA_E2E_EMAIL", "STRUCTURA_E2E_PASSWORD"])
    if (!env[name]?.trim()) throw new Error(`${name} must be explicitly configured for the disposable upload stack.`);
  if (env.STRUCTURA_E2E_DISPOSABLE_STACK !== "1") throw new Error("Upload acceptance requires STRUCTURA_E2E_DISPOSABLE_STACK=1.");
  const web = new URL(env.STRUCTURA_E2E_WEB_URL!);
  if (!["http:", "https:"].includes(web.protocol) || web.username || web.password || web.search || web.hash || web.pathname !== "/"
    || (web.hostname === "10.25.0.50" && web.port === "13000"))
    throw new Error("Upload acceptance requires an explicit isolated web origin; the historical live stack is forbidden.");
  return {webOrigin: web.origin, email: env.STRUCTURA_E2E_EMAIL!.trim(), password: env.STRUCTURA_E2E_PASSWORD!};
}
export async function signIntoUploadStack(page: Page, info: TestInfo) {
  if (!uploadLiveEnabled) throw new Error("Live upload execution requires both explicit live flags.");
  const config = uploadLiveConfig();
  if (info.config.workers !== 1) throw new Error("Run disposable upload acceptance with --workers=1 to isolate per-actor admission.");
  await page.goto(`${config.webOrigin}/inbox`);
  await page.getByLabel("Email", {exact: true}).fill(config.email);
  await page.getByLabel("Password", {exact: true}).fill(config.password);
  await page.getByRole("button", {name: "Sign in", exact: true}).click();
  await expect(page.getByRole("heading", {name: "Document Operations", exact: true})).toBeVisible();
  const session = await page.request.get(`${config.webOrigin}/api/v1/auth/session`);
  expect(session.ok()).toBe(true);
  const actor = await session.json();
  expect(actor.email.toLowerCase()).toBe(config.email.toLowerCase());
  expect(actor.isAuthenticated).toBe(true);
  expect(actor.userId).toMatch(/^[a-f\d-]{36}$/i); expect(actor.householdId).toMatch(/^[a-f\d-]{36}$/i);
  return config;
}
export const liveQueue = (page: Page) => page.getByRole("dialog", {name: "Upload files"});
export const runName = (label: string) => `upload-live-${label}-${randomUUID()}`;
export const sha256 = (bytes: Buffer) => createHash("sha256").update(bytes).digest("hex");
export type LiveSource = {path: string; bytes: Buffer; sha256: string};
export async function livePdf(info: TestInfo, name: string, lines: string[]): Promise<LiveSource> {
  const path = info.outputPath(name); await mkdir(dirname(path), {recursive: true});
  await writeSimplePdf(path, lines); const bytes = await readFile(path);
  return {path, bytes, sha256: sha256(bytes)};
}
function pngChunk(type: string, bytes: Buffer): Buffer {
  const data = Buffer.concat([Buffer.from(type), bytes]); let crc = 0xffffffff;
  for (const byte of data) { crc ^= byte; for (let bit = 0; bit < 8; bit++) crc = (crc >>> 1) ^ ((crc & 1) ? 0xedb88320 : 0); }
  const length = Buffer.alloc(4), checksum = Buffer.alloc(4); length.writeUInt32BE(bytes.length); checksum.writeUInt32BE((crc ^ 0xffffffff) >>> 0);
  return Buffer.concat([length, data, checksum]);
}
export async function livePng(info: TestInfo, name: string, marker: string): Promise<LiveSource> {
  const path = info.outputPath(name), header = Buffer.alloc(13);
  header.writeUInt32BE(2, 0); header.writeUInt32BE(2, 4); header[8] = 8; header[9] = 2;
  const colors = createHash("sha256").update(marker).digest();
  const scanlines = Buffer.concat([Buffer.from([0]), colors.subarray(0, 6), Buffer.from([0]), colors.subarray(6, 12)]);
  const bytes = Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]), pngChunk("IHDR", header),
    pngChunk("tEXt", Buffer.from(`Comment\0${marker}`)), pngChunk("IDAT", deflateSync(scanlines)), pngChunk("IEND", Buffer.alloc(0))]);
  await mkdir(dirname(path), {recursive: true}); await writeFile(path, bytes);
  return {path, bytes, sha256: sha256(bytes)};
}
export async function selectLiveFiles(page: Page, paths: string[]) {
  const input = page.locator(".top-command input[type=file]");
  await expect(input).toBeEnabled(); await input.setInputFiles(paths);
}
const evidenceWriters = new WeakMap<Page, (info: TestInfo) => Promise<void>>();
export async function attachLiveUploadEvidence(page: Page, info: TestInfo) { await evidenceWriters.get(page)?.(info); }
export function observeLiveUploads(page: Page) {
  const requests: {method: string; path: string; registration?: UploadCreate}[] = [];
  const responses: {status: number; path: string; attempt?: UploadAttempt}[] = [];
  const reads = new Set<Promise<void>>();
  page.on("request", (request) => {
    const path = new URL(request.url()).pathname;
    if (!/^\/api\/v1\/uploads(?:\/|$)/.test(path)) return;
    requests.push({method: request.method(), path,
      ...(request.method() === "POST" && path === "/api/v1/uploads" ? {registration: request.postDataJSON() as UploadCreate} : {})});
  });
  page.on("response", (response) => {
    const path = new URL(response.url()).pathname;
    if (!/^\/api\/v1\/uploads(?:\/|$)/.test(path)) return;
    const read = (async () => {
      const entry: typeof responses[number] = {status: response.status(), path};
      if (response.ok()) { const body: unknown = await response.json(); if (body && typeof body === "object" && "uploadId" in body) entry.attempt = body as UploadAttempt; }
      responses.push(entry);
    })().catch(() => { responses.push({status: response.status(), path}); });
    reads.add(read); void read.finally(() => reads.delete(read));
  });
  const attach = async (info: TestInfo) => {
    await Promise.all([...reads]); await info.attach("synthetic-upload-http-evidence", {
      body: JSON.stringify({requests, responses}, null, 2), contentType: "application/json"});
  };
  evidenceWriters.set(page, attach);
  return {requests, responses,
    async waitFor(predicate: (attempt: UploadAttempt) => boolean) {
      await expect.poll(() => responses.some((entry) => entry.attempt && predicate(entry.attempt)), {timeout: 15000}).toBe(true);
      return responses.findLast((entry) => entry.attempt && predicate(entry.attempt))!.attempt!;
    },
    contentCount: () => requests.filter((entry) => entry.method === "PUT" && entry.path.endsWith("/content")).length,
  };
}
export async function assertOriginalReceipt(page: Page, attempt: UploadAttempt, source: LiveSource) {
  const config = uploadLiveConfig(), receipt = attempt.receipt;
  expect(["accepted", "reused"]).toContain(attempt.state);
  expect(receipt).not.toBeNull();
  expect(receipt!.outcome).toBe(attempt.state); expect(receipt!.sha256).toBe(source.sha256);
  expect(attempt.sha256).toBe(source.sha256); expect(attempt.declaredBytes).toBe(source.bytes.length);
  expect(receipt!.byteSize).toBe(source.bytes.length); expect(attempt.actualBytes).toBe(source.bytes.length);
  if (attempt.state === "accepted") { expect(receipt!.jobId).toMatch(/^[a-f\d-]{36}$/i); expect(receipt!.batchId).toMatch(/^[a-f\d-]{36}$/i); }
  else { expect(receipt!.jobId).toBeNull(); expect(receipt!.batchId).toBeNull(); }
  const response = await page.request.get(`${config.webOrigin}/api/v1/assets/${receipt!.assetId}`);
  expect(response.ok()).toBe(true); const bytes = await response.body();
  expect(bytes).toEqual(source.bytes); expect(sha256(bytes)).toBe(receipt!.sha256);
  return receipt!;
}
export async function readLiveDocument(page: Page, documentId: string): Promise<Record<string, unknown>> {
  const response = await page.request.get(`${uploadLiveConfig().webOrigin}/api/v1/documents/${documentId}`);
  expect(response.status()).toBe(200);
  const document = await response.json(); expect(document.id).toBe(documentId);
  return document as Record<string, unknown>;
}
export async function openReceiptDocument(page: Page, attempt: UploadAttempt) {
  const id = attempt.receipt!.documentId;
  const row = liveQueue(page).getByRole("article").filter({hasText: id});
  await expect(row).toHaveCount(1); await row.getByRole("button", {name: "Open document", exact: true}).click();
  await expect(page).toHaveURL((url) => url.pathname === "/inbox" && url.searchParams.get("document") === id);
}
export async function assertViewerDownload(page: Page, receipt: NonNullable<UploadAttempt["receipt"]>, source: LiveSource) {
  const open = page.locator(".page-heading").getByRole("button", {name: "Open Viewer", exact: true});
  await expect(open).toBeEnabled(); await open.click();
  await expect(page).toHaveURL((url) => url.pathname === `/documents/${receipt.documentId}`);
  await expect(page.getByRole("heading", {name: "Document Viewer", exact: true})).toBeVisible();
  const link = page.getByRole("link", {name: "Download original", exact: true});
  const href = new URL((await link.getAttribute("href"))!, page.url());
  expect(href.origin).toBe(uploadLiveConfig().webOrigin); expect(href.pathname).toBe(`/api/v1/assets/${receipt.assetId}`);
  const download = await page.request.get(href.href); expect(download.ok()).toBe(true);
  const bytes = await download.body(); expect(bytes).toEqual(source.bytes); expect(sha256(bytes)).toBe(source.sha256);
}
