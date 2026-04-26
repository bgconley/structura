import {expect, test, type Page} from "@playwright/test";

import {writeSimplePdf} from "./support/pdf";

const liveStackEnabled = process.env.STRUCTURA_E2E_LIVE === "1";
const email = process.env.STRUCTURA_E2E_EMAIL ?? "phase1-live@example.com";
const password = process.env.STRUCTURA_E2E_PASSWORD ?? "Phase1LivePass!2026";

type ParseDebugView = {
  artifacts: Array<{assetRole?: string}>;
  pages: Array<{textPreview?: string}>;
  chunks: unknown[];
  jobs: Array<{jobType?: string; status?: string}>;
};

test.describe("Phase 3 live GPU stack", () => {
  test.skip(!liveStackEnabled, "Set STRUCTURA_E2E_LIVE=1 to run against the GPU stack.");

  test("uploads a PDF and loads live Docling parse diagnostics in the viewer", async ({
    page,
  }, testInfo) => {
    test.setTimeout(180_000);

    const unique = Date.now().toString();
    const title = `phase3-live-${unique}`;
    const marker = `Phase 3 live parse marker ${unique}`;
    const uploadPath = testInfo.outputPath(`${title}.pdf`);
    await writeSimplePdf(uploadPath, [
      marker,
      "Invoice Number LIVE-300",
      "Vendor Structura Test Vendor",
      "Total USD 42.17",
    ]);

    await page.goto("/");
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password").fill(password);
    await page.getByRole("button", {name: "Sign in"}).click();
    await expect(page.getByRole("heading", {name: "Document Operations"})).toBeVisible();

    await page.locator(".top-command input[type='file']").setInputFiles(uploadPath);
    await expect(page.getByRole("row", {name: new RegExp(title)})).toBeVisible();
    await page.getByRole("row", {name: new RegExp(title)}).click();

    const documentId = await findDocumentId(page, title);
    await expect.poll(
      async () => parseDebugReady(page, documentId, marker),
      {
        timeout: 150_000,
        intervals: [1000, 2000, 5000, 10000],
        message: "Docling worker should persist canonical parse diagnostics",
      },
    ).toMatchObject({ready: true});

    await page.locator(".page-heading").getByRole("button", {name: "Open Viewer"}).click();
    await expect(page.getByRole("heading", {name: "Document Viewer"})).toBeVisible();

    const debug = page.locator(".parse-debug-panel");
    await debug.getByRole("button", {name: "Load"}).click();
    await expect(debug).toContainText("Current artifact: docling_json");
    await expect(debug).toContainText("Pages 1");
    await expect(debug).toContainText("Chunks 1");
    await expect(debug).toContainText("docling_convert succeeded");
    await expect(debug).toContainText(marker);
    await page.screenshot({path: testInfo.outputPath("phase3-live-parse-debug.png"), fullPage: true});
  });
});

async function findDocumentId(page: Page, title: string): Promise<string> {
  const response = await page.request.get(`/api/v1/documents?q=${encodeURIComponent(title)}`);
  expect(response.ok()).toBeTruthy();
  const payload = await response.json() as {items?: Array<{id?: string; title?: string}>};
  const match = payload.items?.find((document) => document.title === title);
  expect(match?.id).toBeTruthy();
  return String(match?.id);
}

async function parseDebugReady(
  page: Page,
  documentId: string,
  marker: string,
): Promise<{
  ready: boolean;
  status?: number;
  artifactCount?: number;
  pageCount?: number;
  chunkCount?: number;
  doclingStatus?: string;
  textMatched?: boolean;
}> {
  const response = await page.request.get(`/api/v1/documents/${documentId}/parse-debug`);
  if (!response.ok()) {
    return {ready: false, status: response.status()};
  }
  const debug = await response.json() as ParseDebugView;
  const doclingStatus = debug.jobs.find((job) => job.jobType === "docling_convert")?.status;
  const textMatched = debug.pages.some((pageRow) => pageRow.textPreview?.includes(marker));
  const ready = debug.artifacts.some((asset) => asset.assetRole === "docling_json")
    && debug.pages.length >= 1
    && debug.chunks.length >= 1
    && doclingStatus === "succeeded"
    && textMatched;
  return {
    ready,
    artifactCount: debug.artifacts.length,
    pageCount: debug.pages.length,
    chunkCount: debug.chunks.length,
    doclingStatus,
    textMatched,
  };
}
