import {expect, test} from "@playwright/test";
import {writeFile} from "node:fs/promises";
import {assertOriginalReceipt, assertViewerDownload, attachLiveUploadEvidence, livePdf, livePng, liveQueue, observeLiveUploads,
  openReceiptDocument, readLiveDocument, runName, selectLiveFiles, signIntoUploadStack, uploadLiveConfig, uploadLiveEnabled} from "./support/uploadLive";

// Pure guard coverage executes locally; no browser, credentials, or stack is used.
test("live upload guard requires explicit disposable configuration and refuses the historical stack", () => {
  const valid = {STRUCTURA_E2E_DISPOSABLE_STACK: "1", STRUCTURA_E2E_WEB_URL: "http://web:3000",
    STRUCTURA_E2E_EMAIL: "synthetic@example.invalid", STRUCTURA_E2E_PASSWORD: "synthetic-test-only"};
  expect(uploadLiveConfig(valid).webOrigin).toBe("http://web:3000");
  for (const key of Object.keys(valid)) expect(() => uploadLiveConfig({...valid, [key]: undefined})).toThrow();
  for (const url of ["http://10.25.0.50:13000", "http://web:3000/inbox", "https://name:secret@web:3000", "file:///tmp/fixture"])
    expect(() => uploadLiveConfig({...valid, STRUCTURA_E2E_WEB_URL: url})).toThrow();
});

test.describe("104 disposable real-stack uploads", () => {
  test.describe.configure({timeout: 90000});
  test.skip(!uploadLiveEnabled, "Requires STRUCTURA_E2E_LIVE=1 and STRUCTURA_E2E_UPLOAD_LIVE=1, with explicit disposable configuration.");
  test.beforeEach(async ({page}, info) => { await signIntoUploadStack(page, info); });
  test.afterEach(async ({page}, info) => { await attachLiveUploadEvidence(page, info); });

  test("same-name batch preserves selection and opens each exact accepted original", async ({page}, info) => {
    const run = runName("same-name"), observed = observeLiveUploads(page);
    const selected = await livePdf(info, `${run}-selected.pdf`, [run, "Selected source remains selected."]);
    await selectLiveFiles(page, [selected.path]);
    const initial = await observed.waitFor((attempt) => attempt.state === "accepted" && attempt.sha256 === selected.sha256);
    await assertOriginalReceipt(page, initial, selected); await openReceiptDocument(page, initial);
    const selectionUrl = page.url();
    const first = await livePdf(info, `first/${run}.pdf`, [run, "First same-name source."]);
    const second = await livePdf(info, `second/${run}.pdf`, [run, "Second same-name source, different original bytes."]);
    await selectLiveFiles(page, [first.path, second.path]);
    const a = await observed.waitFor((attempt) => attempt.state === "accepted" && attempt.sha256 === first.sha256);
    const b = await observed.waitFor((attempt) => attempt.state === "accepted" && attempt.sha256 === second.sha256);
    const ra = await assertOriginalReceipt(page, a, first), rb = await assertOriginalReceipt(page, b, second);
    expect(a.filename).toBe(b.filename); expect(a.clientBatchId).toBe(b.clientBatchId);
    expect(a.operationId).not.toBe(b.operationId); expect(ra.documentId).not.toBe(rb.documentId); expect(ra.jobId).not.toBe(rb.jobId);
    await expect(page).toHaveURL(selectionUrl); expect(observed.contentCount()).toBe(3);
    await openReceiptDocument(page, a); await expect(page.locator(".inspector")).toContainText(run);
    await page.locator(".upload-queue-trigger").click(); await openReceiptDocument(page, b);
    await assertViewerDownload(page, rb, second);
  });

  test("readable duplicate reuse and keep-separate produce the actual distinct receipts", async ({page}, info) => {
    const run = runName("duplicate"), observed = observeLiveUploads(page);
    const source = await livePdf(info, `${run}.pdf`, [run, "Exact duplicate acceptance source."]);
    await selectLiveFiles(page, [source.path]);
    const first = await observed.waitFor((attempt) => attempt.state === "accepted");
    const original = await assertOriginalReceipt(page, first, source);
    const before = await readLiveDocument(page, original.documentId);
    await liveQueue(page).getByRole("button", {name: "Clear finished rows", exact: true}).click();
    await liveQueue(page).getByRole("button", {name: "Close uploads", exact: true}).click();
    await selectLiveFiles(page, [source.path]);
    const held = await observed.waitFor((attempt) => attempt.state === "awaiting_duplicate_decision");
    expect(held.receipt).toBeNull(); expect(held.duplicates).toEqual([{documentId: original.documentId, title: run}]);
    await expect(liveQueue(page).getByRole("button", {name: "Use selected existing document", exact: true})).toBeDisabled();
    await liveQueue(page).getByRole("radio", {name: run, exact: true}).check();
    await liveQueue(page).getByRole("button", {name: "Use selected existing document", exact: true}).click();
    const reused = await observed.waitFor((attempt) => attempt.uploadId === held.uploadId && attempt.state === "reused");
    const reuseReceipt = await assertOriginalReceipt(page, reused, source);
    expect(reuseReceipt.documentId).toBe(original.documentId); expect(reuseReceipt.assetId).toBe(original.assetId);
    const after = await readLiveDocument(page, original.documentId);
    for (const key of ["title", "documentDate", "primaryFolderId", "folderIds", "tags", "reviewStatus", "fields", "lineItems"])
      expect(after[key]).toEqual(before[key]);
    await liveQueue(page).getByRole("button", {name: "Clear finished rows", exact: true}).click();
    await liveQueue(page).getByRole("button", {name: "Close uploads", exact: true}).click();
    await selectLiveFiles(page, [source.path]);
    const separateHeld = await observed.waitFor((attempt) => attempt.state === "awaiting_duplicate_decision" && attempt.uploadId !== held.uploadId);
    await liveQueue(page).getByRole("button", {name: "Keep as a separate document", exact: true}).click();
    const separate = await observed.waitFor((attempt) => attempt.uploadId === separateHeld.uploadId && attempt.state === "accepted");
    const separateReceipt = await assertOriginalReceipt(page, separate, source);
    expect(separateReceipt.documentId).not.toBe(original.documentId); expect(separateReceipt.jobId).not.toBe(original.jobId);
    expect(observed.contentCount()).toBe(3);
  });

  test("mobile keyboard PNG acceptance and refresh recover by GET without another PUT", async ({page}, info) => {
    await page.setViewportSize({width: 390, height: 844});
    const run = runName("png"), observed = observeLiveUploads(page), source = await livePng(info, `${run}.png`, run);
    const input = page.locator(".top-command input[type=file]"); await expect(input).toBeEnabled();
    const chooser = page.waitForEvent("filechooser"); await input.focus(); await page.keyboard.press("Enter");
    await (await chooser).setFiles(source.path);
    const first = await observed.waitFor((attempt) => attempt.state === "accepted");
    const receipt = await assertOriginalReceipt(page, first, source);
    await expect(liveQueue(page)).toContainText("Upload accepted");
    await page.keyboard.press("Escape"); await expect(liveQueue(page)).not.toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    const before = observed.contentCount(); await page.reload();
    const uploads = page.getByRole("button", {name: "Uploads (1 need attention)", exact: true});
    await expect(uploads).toBeVisible(); await uploads.focus(); await page.keyboard.press("Enter");
    await expect(liveQueue(page)).toContainText("Previous upload"); await expect(liveQueue(page)).not.toContainText(run);
    expect(observed.requests.filter((request) => request.method === "GET")).toHaveLength(0);
    await liveQueue(page).getByRole("button", {name: "Check upload outcome", exact: true}).click();
    await expect.poll(() => observed.responses.filter((response) => response.path === `/api/v1/uploads/${first.uploadId}` && response.attempt?.state === "accepted").length).toBe(1);
    const recovered = await observed.waitFor((attempt) => attempt.uploadId === first.uploadId && attempt.state === "accepted");
    expect(recovered.receipt).toEqual(receipt); expect(observed.contentCount()).toBe(before);
    expect(observed.requests.filter((request) => request.method === "POST" && request.path === "/api/v1/uploads")).toHaveLength(1);
    await openReceiptDocument(page, recovered); await assertViewerDownload(page, receipt, source);
    await page.getByRole("button", {name: "Back to Inbox", exact: true}).click();
    await expect(page).toHaveURL((url) => url.pathname === "/inbox" && url.searchParams.get("document") === receipt.documentId);
    await page.screenshot({path: info.outputPath("real-upload-mobile.png"), fullPage: true});
  });

  test("unsupported signature is rejected and a later valid source remains usable", async ({page}, info) => {
    const run = runName("rejected"), observed = observeLiveUploads(page), path = info.outputPath(`${run}.pdf`);
    await writeFile(path, `This is synthetic plain text, not a PDF. ${run}`);
    await selectLiveFiles(page, [path]);
    await expect.poll(() => observed.responses.some((response) => response.path.endsWith("/content") && response.status === 415)).toBe(true);
    await expect(liveQueue(page).getByRole("alert")).toContainText("File signature is unsupported");
    await liveQueue(page).getByRole("button", {name: "Check upload outcome", exact: true}).click();
    const rejected = await observed.waitFor((attempt) => attempt.state === "rejected");
    expect(rejected.receipt).toBeNull(); expect(rejected.error?.code).toBe("upload_signature_unsupported");
    await expect(liveQueue(page)).toContainText("File rejected");
    await expect(liveQueue(page).getByRole("button", {name: "Open document", exact: true})).toHaveCount(0);
    const valid = await livePdf(info, `${run}-valid.pdf`, [run, "A valid independent source after rejection."]);
    await liveQueue(page).getByRole("button", {name: "Close uploads", exact: true}).click(); await selectLiveFiles(page, [valid.path]);
    const accepted = await observed.waitFor((attempt) => attempt.state === "accepted");
    expect(accepted.operationId).not.toBe(rejected.operationId); await assertOriginalReceipt(page, accepted, valid);
    await expect(liveQueue(page)).toContainText("Upload accepted");
  });
});
