import {expect, test} from "@playwright/test";
import {assertOriginalReceipt, assertViewerDownload, attachLiveUploadEvidence, livePdf, observeLiveUploads, openReceiptDocument,
  runName, selectLiveFiles, signIntoUploadStack, uploadLiveEnabled} from "./support/uploadLive";

test.describe("Phase 1 disposable live Compose stack", () => {
  test.skip(!uploadLiveEnabled, "Requires both live/upload opt-ins and explicit disposable stack configuration.");
  test.afterEach(async ({page}, info) => { await attachLiveUploadEvidence(page, info); });
  test("logs in, uploads a document, and opens the viewer through the real API", async ({page}, info) => {
    test.setTimeout(90000);
    await signIntoUploadStack(page, info);
    const title = runName("phase1"), observed = observeLiveUploads(page);
    const source = await livePdf(info, `${title}.pdf`, [title, "Phase 1 real original acceptance and Viewer proof."]);
    await selectLiveFiles(page, [source.path]);
    const accepted = await observed.waitFor((attempt) => attempt.state === "accepted");
    const receipt = await assertOriginalReceipt(page, accepted, source);
    await openReceiptDocument(page, accepted);
    await expect(page.getByRole("row").filter({hasText: title})).toBeVisible();
    await expect(page.locator(".inspector")).toContainText(title);
    await expect(page.locator(".inspector")).toContainText("SHA-256");
    await assertViewerDownload(page, receipt, source);
    expect(observed.contentCount()).toBe(1);
  });
});
