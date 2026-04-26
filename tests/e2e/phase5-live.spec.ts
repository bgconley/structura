import {expect, test, type Page} from "@playwright/test";

import {writeSimplePdf} from "./support/pdf";

const liveStackEnabled = process.env.STRUCTURA_E2E_LIVE === "1";
const email = process.env.STRUCTURA_E2E_EMAIL ?? "phase1-live@example.com";
const password = process.env.STRUCTURA_E2E_PASSWORD ?? "Phase1LivePass!2026";

test.describe("Phase 5 live GPU stack", () => {
  test.skip(!liveStackEnabled, "Set STRUCTURA_E2E_LIVE=1 to run against the GPU stack.");

  test("searches a parsed live document and opens the evidence target", async ({
    page,
  }, testInfo) => {
    test.setTimeout(180_000);

    const unique = Date.now().toString();
    const title = `phase5-live-${unique}`;
    const marker = `phase5-live-claim-${unique}`;
    const uploadPath = testInfo.outputPath(`${title}.pdf`);
    await writeSimplePdf(uploadPath, [
      `Anthem medical EOB ${marker}`,
      "Claim ABC123",
      "Patient responsibility amount due is 62.00",
    ]);

    await page.goto("/");
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password").fill(password);
    await page.getByRole("button", {name: "Sign in"}).click();
    await expect(page.getByRole("heading", {name: "Document Operations"})).toBeVisible();

    await page.locator(".top-command input[type='file']").setInputFiles(uploadPath);
    await expect(page.getByRole("row", {name: new RegExp(title)})).toBeVisible();

    const documentId = await findDocumentId(page, title);
    await expect.poll(
      async () => searchHasResult(page, marker, documentId),
      {
        timeout: 150_000,
        intervals: [1000, 2000, 5000, 10000],
        message: "Phase 5 lexical search should index parsed live text",
      },
    ).toBeTruthy();

    await page.getByRole("button", {name: /Search/}).click();
    await page.getByLabel("Corpus search query").fill(marker);
    await page.getByLabel("Search mode").selectOption("lexical");
    await page.getByRole("button", {name: "Search corpus"}).click();

    await expect(page.getByRole("button", {name: new RegExp(title)})).toBeVisible();
    await page
      .locator(".search-result-card")
      .filter({hasText: title})
      .getByRole("button", {name: "Jump to evidence"})
      .click();
    await expect(page.getByRole("heading", {name: "Document Viewer"})).toBeVisible();
    await expect(page.getByRole("status")).toContainText(marker);
    await page.screenshot({path: testInfo.outputPath("phase5-live-search.png"), fullPage: true});
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

async function searchHasResult(page: Page, marker: string, documentId: string): Promise<boolean> {
  const response = await page.request.post("/api/v1/search", {
    data: {query: marker, mode: "lexical", limit: 5},
  });
  if (!response.ok()) {
    return false;
  }
  const payload = await response.json() as {items?: Array<{documentId?: string}>};
  return Boolean(payload.items?.some((item) => item.documentId === documentId));
}
